"""Plan stage (Understand -> Plan -> Decide -> Validate): produces an explainable, validated editing plan.

Pipeline: interpret prompt -> rescore (topic) -> silence-removal intervals -> expert rules (scene scope) -> candidate
selection -> A* sequencing -> CSP (durations, transitions, subtitle position) -> expert rules (transition/global) ->
forward/backward chaining report -> subtitle cues -> independent validation. A plan that fails validation is stored but
flagged invalid and can NOT be rendered.
"""
from __future__ import annotations
import time
from sqlalchemy.orm import Session
import numpy as np
from ..ai.agent_controller import AgentContext, clear_decisions
from ..ai.prompt_interpreter import interpret
from ..ai.scene_scorer import ScoringWeights, score_scenes
from ..algorithms.astar import sequence_scenes
from ..algorithms.backtracking import solve
from ..algorithms.backward_chaining import prove, unmet
from ..algorithms.csp import SUBTITLE_Y, build_editing_csp, diagnose_failure, validate_plan
from ..algorithms.expert_system import default_rules
from ..algorithms.forward_chaining import forward_chain
from ..algorithms.heuristic import build_cost_matrix
from ..config import get_settings
from ..core.audio_processor import compute_keep_intervals
from ..models import EditingPlan, Project
from ..rendering.subtitle_renderer import build_cues, output_duration
from ..rendering.transition_engine import transition_type
from ..schemas.editing import EditConfig
from ..utils.file_utils import new_id
from .analysis_service import load_scenes

HIGH_RELEVANCE, LOW_IMPORTANCE, CONTINUITY_THRESHOLD = 0.7, 35.0, 0.25


def take_effective(intervals: list[tuple[float, float]], dur: float) -> list[dict]:
    """First `dur` seconds of the kept (silence-removed) content of a scene."""
    out, left = [], dur
    for a, b in intervals:
        if left <= 1e-6:
            break
        use = min(b - a, left)
        if use >= 0.04:
            out.append({"start": round(a, 3), "end": round(a + use, 3)})
        left -= use
    return out


def _semantic_sim(texts: list[str]):
    if not any(t.strip() for t in texts):
        return None
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    try:
        m = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b").fit_transform([t or " " for t in texts])
    except ValueError:
        return None
    return cosine_similarity(m)


def generate_plan(db: Session, project_id: str, prompt: str, overrides: dict | None = None) -> EditingPlan:
    t0 = time.perf_counter()
    s = get_settings()
    p = db.get(Project, project_id)
    if p is None or not p.analysis:
        raise ValueError("Analyze the project before planning")
    ctx = AgentContext(db, project_id)
    clear_decisions(db, project_id, phases={"understand", "plan", "decide", "validate"})
    meta, transcript = p.video_metadata, (p.transcript or {"segments": [], "status": "unavailable"})
    has_tr = transcript.get("status") == "ok" and len(transcript.get("segments", [])) > 0

    # UNDERSTAND
    it = interpret(prompt, overrides)
    cfg = EditConfig(**it["config"])
    ctx.log("understand", "planner", f"Interpreted instruction via {it['source']}: {cfg.target_duration:.0f}s, {cfg.aspect_ratio}, {cfg.resolution}, "
            f"silence_removal={cfg.remove_silence}, subtitles={cfg.subtitles}, transitions={cfg.transition_style}", "; ".join(it["notes"]))
    W, H = map(int, cfg.resolution.split("x"))
    scenes = [dict(x) for x in load_scenes(db, project_id)]
    score_scenes(scenes, topic=cfg.topic, weights=ScoringWeights())
    by_id = {sc["scene_id"]: sc for sc in scenes}
    rules = default_rules()
    rule_log: list[dict] = []

    # keep intervals (silence removal that never drops speech)
    removed_silence_intervals = 0
    for sc in scenes:
        if cfg.remove_silence and meta["has_audio"]:
            keep = compute_keep_intervals(sc["start"], sc["end"], [tuple(x) for x in sc["activity_intervals"]],
                                          [tuple(x) for x in sc["speech_intervals"]] if cfg.preserve_speech else [], s.silence_pad_seconds)
        else:
            keep = [(sc["start"], sc["end"])]
        sc["keep"] = keep
        sc["eff_duration"] = round(sum(b - a for a, b in keep), 3)

    # DECIDE (1): expert rules at scene scope
    excluded, retained, reasons = set(), set(), {}
    for sc in scenes:
        facts = {"remove_silence": cfg.remove_silence and meta["has_audio"], "silence_duration": (sc["duration"] - sc["eff_duration"]) if cfg.remove_silence else 0.0,
                 "silence_threshold": s.silence_min_seconds, "speech_relevance_norm": sc["features"]["speech_relevance"]["normalized"],
                 "high_relevance": HIGH_RELEVANCE, "scene_duration": sc["eff_duration"], "min_scene_len": cfg.min_scene_len,
                 "importance": sc["importance"], "low_importance": LOW_IMPORTANCE}
        wm, recs = forward_chain(rules, facts, "scene", f"scene {sc['scene_id']}")
        rule_log += [r.to_dict() for r in recs]
        if wm.get("exclude_candidate"):
            excluded.add(sc["scene_id"]); reasons[sc["scene_id"]] = "R3: short and low importance"
        if sc["eff_duration"] < cfg.min_scene_len and sc["scene_id"] not in excluded:
            excluded.add(sc["scene_id"]); reasons[sc["scene_id"]] = "shorter than minimum length after silence removal" if sc["eff_duration"] > 0 else "entirely silent"
        if wm.get("priority_retain"):
            retained.add(sc["scene_id"])
    ctx.log("decide", "planner", f"Expert system (scene scope): {len(retained)} scene(s) prioritised, {len(excluded)} excluded",
            "; ".join(f"scene {k}: {v}" for k, v in reasons.items()) or "no exclusions")

    # DECIDE (2): candidate selection (utility = importance, boosted by R2)
    elig = [sc for sc in scenes if sc["scene_id"] not in excluded]
    elig.sort(key=lambda x: -(x["importance"] + (15 if x["scene_id"] in retained else 0)))
    chosen, acc = [], 0.0
    for sc in elig:
        if len(chosen) >= cfg.max_candidates or acc >= cfg.target_duration * 1.5:
            break
        chosen.append(sc); acc += sc["eff_duration"]
    chosen.sort(key=lambda x: x["start"])
    ctx.log("decide", "scene", f"Selected {len(chosen)} candidate scene(s) totalling {acc:.1f}s usable content (target {cfg.target_duration:.0f}s)",
            "Highest importance first until 1.5x target duration or candidate limit reached")

    # DECIDE (3): A* sequencing
    astar_out: dict = {"candidates": [c["scene_id"] for c in chosen]}
    order_ids = [c["scene_id"] for c in chosen]
    if len(chosen) >= 1:
        sim = _semantic_sim([c["transcript"] for c in chosen])
        cm = build_cost_matrix(chosen, p.duration, semantic_sim=sim)
        res = sequence_scenes(cm.cost, [c["start"] for c in chosen], max_exact=9)
        use_astar = cfg.sequencing == "astar"
        idx_order = res["order"] if use_astar else res["chronological_order"]
        order_ids = [chosen[i]["scene_id"] for i in idx_order]
        res["order_scene_ids"] = [chosen[i]["scene_id"] for i in res["order"]]
        res["chronological_scene_ids"] = [chosen[i]["scene_id"] for i in res["chronological_order"]]
        res["applied"] = "astar" if use_astar else "chronological"
        res["cost_notes"] = cm.notes
        res["cost_components"] = {f"{chosen[i]['scene_id']}->{chosen[j]['scene_id']}": v for (i, j), v in cm.components.items()}
        res["trace"] = [{**t, "path": [chosen[i]["scene_id"] for i in t["path"]]} for t in res["trace"]]
        res["candidate_ids"] = [c["scene_id"] for c in chosen]
        astar_out = res
        ctx.log("decide", "planner", f"Sequencing {'A*' if use_astar else 'chronological'}: order {order_ids}; A* cost {res['cost']:.3f} vs chronological {res['chronological_cost']:.3f} "
                f"({res['expanded']} expanded, {res['explored_states']} states, {'optimal' if res['optimal'] else 'NOT guaranteed optimal'})", res["note"])
        idx_of = {c["scene_id"]: i for i, c in enumerate(chosen)}
    ordered = [by_id[i] for i in order_ids]

    # VALIDATE: CSP, iterating the number of hard-cut boundaries decided by the transition rules
    csp_cfg = {"target_duration": cfg.target_duration, "tolerance": cfg.duration_tolerance, "min_scene_len": cfg.min_scene_len,
               "aspect_ratio": cfg.aspect_ratio, "resolution": cfg.resolution, "subtitle_position": cfg.subtitle_position,
               "transition_style": cfg.transition_style, "cut_hint": 0}
    cands = [{"scene_id": c["scene_id"], "eff_duration": c["eff_duration"], "importance": c["importance"]} for c in ordered]
    sol, csp_res, kept, boundary_recs = None, None, [], []
    for attempt in range(3):
        csp, _ = build_editing_csp(cands, csp_cfg)
        csp_res = solve(csp)
        sol = csp_res.solution
        if sol is None:
            break
        kept = [c for c in ordered if sol[f"dur_{c['scene_id']}"] > 0]
        trans_on = sol["trans"] > 0 and cfg.transition_style not in ("none", "cut")
        boundary_recs, cuts = [], 0
        for a, b in zip(kept, kept[1:]):
            disc = cm.components[(idx_of[a["scene_id"]], idx_of[b["scene_id"]])]["visual"]
            wm, recs = forward_chain(rules, {"visual_discontinuity": disc, "continuity_threshold": CONTINUITY_THRESHOLD, "transitions_enabled": trans_on},
                                     "transition", f"{a['scene_id']}->{b['scene_id']}")
            applies = bool(wm.get("transition_needed") or wm.get("transition_soft"))   # explicit style request => every boundary transitions
            boundary_recs.append((a["scene_id"], b["scene_id"], disc, applies, recs, bool(wm.get("transition_soft"))))
            cuts += 0 if (applies and trans_on) else 1
        if cuts == csp_cfg["cut_hint"] or not trans_on:
            break
        csp_cfg["cut_hint"] = cuts
    csp_summary = {"status": "satisfied" if sol else "unsatisfiable", "assignment": sol, "nodes": csp_res.nodes, "backtracks": csp_res.backtracks,
                   "pruned_values": csp_res.pruned_values, "seconds": round(csp_res.seconds, 5), "exhausted": csp_res.exhausted,
                   "failed_constraints": csp_res.failed_constraints, "trace": csp_res.trace, "cut_hint": csp_cfg["cut_hint"],
                   "constraints": [{"name": c.name, "description": c.description, "scope": list(c.scope)} for c in build_editing_csp(cands, csp_cfg)[0].constraints] if cands else []}
    base_plan = {"config": cfg.model_dump(), "source": {"duration": p.duration, "width": meta["width"], "height": meta["height"], "fps": meta["fps"], "has_audio": meta["has_audio"]}}
    sel_scene_ids = [c["scene_id"] for c in chosen]
    if sol is None:
        diag = diagnose_failure(cands, csp_cfg) if cands else {"suggestions": ["No usable scenes were found; check analysis"], "available_seconds": 0}
        csp_summary["diagnosis"] = diag
        ctx.log("validate", "constraint", "CSP UNSATISFIABLE -- plan will not be rendered", "; ".join(diag["suggestions"]))
        plan = {**base_plan, "clips": [], "removed_scenes": [], "operations": [], "output": {"width": W, "height": H, "fps": 30, "duration": 0, "aspect": cfg.aspect_ratio},
                "subtitles": {"enabled": cfg.subtitles, "position": "lower", "style": cfg.subtitle_style, "cue_count": 0}, "subtitle_cues": [],
                "validation": {"status": "infeasible", "violations": [{"constraint": k, "message": f"failed {v} time(s) during search"} for k, v in csp_res.failed_constraints.items()],
                               "suggestions": diag["suggestions"]},
                "algorithms": {"astar": astar_out, "csp": csp_summary, "expert": {"rules": rule_log, "backward": None}}, "warnings": []}
        return _save(db, p, plan, "infeasible", prompt, ctx, t0)

    # ACT-prep: build clips from CSP solution
    trans_val = sol["trans"]
    clips, ops = [], []
    removed_seconds_silence = 0.0
    for k, sc in enumerate(kept):
        dur = sol[f"dur_{sc['scene_id']}"]
        segs = take_effective([tuple(x) for x in sc["keep"]], dur)
        needed = k > 0 and boundary_recs[k - 1][3] and trans_val > 0 and cfg.transition_style not in ("none", "cut")
        disc = boundary_recs[k - 1][2] if k > 0 else 0.0
        soft = k > 0 and boundary_recs[k - 1][5]
        ttype = ("dissolve" if soft else transition_type(cfg.transition_style, disc)) if needed else "cut"
        used_end = segs[-1]["end"] if segs else sc["start"]
        if cfg.remove_silence and meta["has_audio"]:   # silence removed INSIDE the used span [scene.start, used_end] (leading + interior gaps)
            removed_seconds_silence += max(0.0, (used_end - sc["start"]) - sum(x["end"] - x["start"] for x in segs))
            kp = [k for k in sc["keep"] if k[0] < used_end]
            removed_silence_intervals += (1 if kp and kp[0][0] > sc["start"] + 0.05 else 0)
            removed_silence_intervals += sum(1 for x, y in zip(kp, kp[1:]) if y[0] - x[1] > 0.05)
        clips.append({"scene_id": sc["scene_id"], "order": k, "duration": round(sum(x["end"] - x["start"] for x in segs), 3), "segments": segs,
                      "importance": sc["importance"], "focus_x": sc.get("focus_x", 0.5), "thumbnail": sc.get("thumbnail"),
                      "transition_in": {"type": ttype if k > 0 else "none", "duration": trans_val if needed else 0.0,
                                        "discontinuity": round(disc, 4) if k > 0 else None},
                      "rationale": f"importance {sc['importance']:.0f}; {'R2 priority; ' if sc['scene_id'] in retained else ''}{sc['score_detail']['explanation'].split('. ')[1] if '. ' in sc['score_detail']['explanation'] else ''}"})
    # recompute exact duration; allow tiny drift from segment rounding
    total = output_duration(clips)
    sub_pos = sol["sub_pos"]
    cues = build_cues(transcript["segments"], clips) if (cfg.subtitles and has_tr) else []
    warnings = []
    if cfg.subtitles and not has_tr:
        warnings.append("Subtitles requested but no transcript is available (Whisper model unavailable/no speech). Import an SRT or install the Whisper model. Subtitles will be skipped.")
    if cues:
        from ..rendering.subtitle_renderer import resolve_font
        _font, _fwarn = resolve_font(" ".join(c["text"] for c in cues))
        if _fwarn:
            warnings.append(_fwarn)
    if cfg.music_enabled and not p.music_path:
        warnings.append("Music enabled but no music file uploaded; music will be skipped.")

    # DECIDE (4): global expert rules + chaining
    gfacts = {"aspect_ratio": cfg.aspect_ratio, "target_duration": cfg.target_duration, "subtitles_enabled": cfg.subtitles, "has_transcript": has_tr,
              "music_enabled": cfg.music_enabled and bool(p.music_path), "normalize_audio": cfg.normalize_audio, "out_width": W, "out_height": H,
              "source_wider_than_target": meta["width"] / meta["height"] > W / H}
    wm, grecs = forward_chain(rules, gfacts, "global", "project")
    rule_log += [r.to_dict() for r in grecs]
    for a, b, disc, need, recs, _soft in boundary_recs:
        rule_log += [r.to_dict() for r in recs]
    backward = prove("vertical_reel_ready", rules, {**gfacts, **wm}) if cfg.aspect_ratio == "9:16" else None
    if backward:
        backward["unmet_requirements"] = unmet(backward)
    fired_ids = sorted({r["rule_id"] for r in rule_log if r["fired"]})
    ctx.log("decide", "planner", f"Expert system fired rules: {', '.join(fired_ids)}", "Forward chaining to fixed point per scope"
            + (f"; backward chaining: vertical_reel_ready = {backward['proved']}" if backward else ""))

    removed = [{"scene_id": sc["scene_id"], "reason": reasons.get(sc["scene_id"], "dropped by CSP duration assignment" if sc["scene_id"] in sel_scene_ids else "not selected: lower importance than chosen scenes")}
               for sc in scenes if sc["scene_id"] not in {c["scene_id"] for c in clips}]
    ops.append({"op": "select_scenes", "detail": f"Kept {len(clips)} of {len(scenes)} scenes"})
    ops.append({"op": "sequence", "detail": f"{astar_out.get('applied', 'chronological')} order {[c['scene_id'] for c in clips]}"})
    if cfg.remove_silence and meta["has_audio"]:
        ops.append({"op": "trim_silence", "detail": f"Removed ~{removed_seconds_silence:.1f}s of silence in {removed_silence_intervals} interval(s); {s.silence_pad_seconds}s padding kept around speech"})
    if wm.get("reframe_scheduled"):
        ops.append({"op": "reframe", "detail": f"{'Focus-aware crop' if wm.get('focus_crop') else 'Centre crop'} to {W}x{H}"})
    else:
        ops.append({"op": "reframe", "detail": f"Scale/crop to {W}x{H}"})
    if cues:
        ops.append({"op": "subtitles", "detail": f"{len(cues)} cues, style={cfg.subtitle_style}, position={sub_pos}"})
    if any(c["transition_in"]["duration"] > 0 for c in clips):
        ops.append({"op": "transitions", "detail": f"{sum(1 for c in clips if c['transition_in']['duration']>0)} {cfg.transition_style} transition(s) of {trans_val}s"})
    if wm.get("loudnorm"):
        ops.append({"op": "audio", "detail": "EBU R128 loudness normalisation, 0.3s fade-in / 0.5s fade-out"})
    if wm.get("music_ducking"):
        ops.append({"op": "music", "detail": "Mix music with sidechain ducking under speech"})
    if cfg.color_preset != "none":
        ops.append({"op": "color", "detail": f"Colour preset: {cfg.color_preset}"})

    plan = {**base_plan, "clips": clips, "removed_scenes": removed, "operations": ops,
            "output": {"width": W, "height": H, "fps": 30, "duration": total, "aspect": cfg.aspect_ratio},
            "audio_duration": total if meta["has_audio"] else None,
            "subtitles": {"enabled": bool(cues), "requested": cfg.subtitles, "position": sub_pos, "style": cfg.subtitle_style, "cue_count": len(cues)},
            "subtitle_cues": cues, "warnings": warnings,
            "algorithms": {"astar": astar_out, "csp": csp_summary, "expert": {"rules": rule_log, "facts": {k: v for k, v in wm.items()}, "backward": backward}},
            "stats": {"silence_intervals_removed": removed_silence_intervals, "silence_seconds_removed": round(removed_seconds_silence, 2)}}
    val = validate_plan(plan)
    plan["validation"] = val
    ctx.log("validate", "constraint", f"CSP satisfied in {csp_res.nodes} nodes / {csp_res.backtracks} backtracks; independent validation: {val['status']}",
            "; ".join(v["message"] for v in val["violations"]) or f"All {val['checked']} checks passed; final duration {total:.2f}s")
    return _save(db, p, plan, val["status"], prompt, ctx, t0)


def _save(db: Session, p: Project, plan: dict, status: str, prompt: str, ctx: AgentContext, t0: float) -> EditingPlan:
    plan["prompt"] = prompt
    plan["planning_seconds"] = round(time.perf_counter() - t0, 3)
    row = EditingPlan(plan_id=new_id("pl_"), project_id=p.project_id, configuration=plan["config"],
                      selected_scenes=[c["scene_id"] for c in plan["clips"]], editing_operations=plan["operations"],
                      validation_status=status, data=plan)
    db.add(row)
    p.status = "planned" if status == "valid" else p.status
    db.commit()
    ctx.log("plan", "planner", f"Plan {row.plan_id} {status}: {len(plan['clips'])} clip(s), {plan['output']['duration']:.1f}s",
            "; ".join(o["detail"] for o in plan["operations"]))
    return row


def latest_plan(db: Session, project_id: str) -> EditingPlan | None:
    return db.query(EditingPlan).filter(EditingPlan.project_id == project_id).order_by(EditingPlan.created_at.desc()).first()
