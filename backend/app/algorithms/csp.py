"""Constraint-satisfaction problem model + the editing-plan CSP builder + independent plan validator."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

ASPECTS = {"9:16": [(1080, 1920), (720, 1280)], "16:9": [(1920, 1080), (1280, 720)], "1:1": [(1080, 1080), (720, 720)]}
SUBTITLE_Y = {"top": 0.15, "center": 0.50, "lower": 0.72, "bottom": 0.88}
SAFE_Y = {"9:16": (0.12, 0.78), "16:9": (0.05, 0.95), "1:1": (0.05, 0.95)}   # fraction of frame height
TRANSITION_DURATIONS = [0.0, 0.3, 0.5, 0.8]


@dataclass
class Constraint:
    name: str
    scope: tuple[str, ...]
    check: Callable[[dict], bool]                         # called when every scope variable is assigned
    partial: Optional[Callable[[dict, dict], bool]] = None  # (assignment, domains) -> False if surely unsatisfiable
    description: str = ""


@dataclass
class CSP:
    variables: dict[str, list]
    constraints: list[Constraint] = field(default_factory=list)
    priority: dict[str, float] = field(default_factory=dict)       # tie-break / importance for variable ordering
    value_key: dict[str, Callable[[Any], float]] = field(default_factory=dict)  # domain-ordering heuristic per variable

    def consistent(self, assignment: dict, var: str) -> tuple[bool, str | None]:
        for c in self.constraints:
            if var in c.scope and all(v in assignment for v in c.scope) and not c.check(assignment):
                return False, c.name
        return True, None


def build_editing_csp(candidates: list[dict], cfg: dict) -> tuple[CSP, dict]:
    """Variables: aspect, resolution, sub_pos, trans, dur_<scene> (seconds of effective content taken; 0 = dropped).

    candidates: [{scene_id, eff_duration, importance}] in the sequence chosen by A*.
    cfg keys   : target_duration, tolerance, min_scene_len, aspect_ratio, resolution(WxH), subtitles, subtitle_position,
                 transition_style, max_resolution_h (optional), step
    """
    target, tol = cfg["target_duration"], cfg["tolerance"]
    min_len, step = cfg["min_scene_len"], cfg.get("step", 0.5)
    ar = cfg["aspect_ratio"]
    res_dom = [f"{w}x{h}" for w, h in ASPECTS[ar]]
    if cfg.get("resolution") in res_dom:
        res_dom = [cfg["resolution"]]
    pos_pref = cfg.get("subtitle_position") or ("lower" if ar == "9:16" else "bottom")
    pos_dom = list(SUBTITLE_Y)
    trans_dom = [0.0] if cfg.get("transition_style") in ("none", "cut") else [t for t in TRANSITION_DURATIONS if t > 0]
    if cfg.get("transition_style") == "none":
        trans_dom = [0.0]
    variables: dict[str, list] = {"aspect": [ar], "resolution": res_dom, "sub_pos": pos_dom, "trans": trans_dom}
    ideal: dict[str, float] = {}
    total_imp = sum(max(c["importance"], 1.0) for c in candidates) or 1.0
    names = []
    for c in candidates:
        v = f"dur_{c['scene_id']}"
        names.append(v)
        eff = c["eff_duration"]
        dom = [0.0]
        t = min_len
        while t < eff - 1e-9:
            dom.append(round(t, 3))
            t += step
        if eff >= min_len - 1e-9:
            dom.append(round(eff, 3))
        variables[v] = sorted(set(dom))
        ideal[v] = target * max(c["importance"], 1.0) / total_imp
    cons: list[Constraint] = []
    hint = int(cfg.get("cut_hint", 0))   # boundaries already decided to be hard cuts (no overlap)

    def trans_overhead(a: dict, kept_max: int) -> float:
        return 0.0

    def kept(a: dict) -> list[float]:
        return [a[v] for v in names if a.get(v, 0) > 0]

    def total_ok(a: dict) -> bool:
        k = kept(a)
        tot = sum(k) - max(0, len(k) - 1 - hint) * a["trans"]
        return abs(tot - target) <= tol + 1e-9

    def total_partial(a: dict, doms: dict) -> bool:
        tr = a.get("trans", 0.0)
        lo = hi = 0.0
        max_kept = 0
        for v in names:
            if v in a:
                lo += a[v]; hi += a[v]; max_kept += a[v] > 0
            else:
                d = doms[v]
                lo += min(d); hi += max(d); max_kept += max(d) > 0
        lo_eff = lo - max(0, max_kept - 1 - hint) * tr
        return hi >= target - tol - 1e-9 and lo_eff <= target + tol + 1e-9

    cons.append(Constraint("target_duration", tuple(["trans"] + names), total_ok, total_partial,
                           f"final duration within {target}s ± {tol}s"))
    cons.append(Constraint("min_scene_duration", tuple(names), lambda a: all(a[v] == 0 or a[v] >= min_len - 1e-9 for v in names),
                           None, f"each kept scene >= {min_len}s"))
    cons.append(Constraint("within_source_bounds", tuple(names),
                           lambda a: all(a[f"dur_{c['scene_id']}"] <= c["eff_duration"] + 1e-9 for c in candidates), None,
                           "no clip longer than its source scene"))
    cons.append(Constraint("at_least_one_scene", tuple(names), lambda a: any(a[v] > 0 for v in names),
                           lambda a, d: any(v in a and a[v] > 0 or (v not in a and max(d[v]) > 0) for v in names), "at least one scene kept"))
    cons.append(Constraint("export_dimensions_match_aspect", ("aspect", "resolution"),
                           lambda a: tuple(map(int, a["resolution"].split("x"))) in ASPECTS[a["aspect"]], None,
                           "WxH must be a supported profile for the aspect ratio"))
    cons.append(Constraint("subtitle_in_safe_area", ("aspect", "sub_pos"),
                           lambda a: SAFE_Y[a["aspect"]][0] <= SUBTITLE_Y[a["sub_pos"]] <= SAFE_Y[a["aspect"]][1], None,
                           "subtitle baseline inside platform safe area"))
    cons.append(Constraint("transition_fits_clips", tuple(["trans"] + names),
                           lambda a: all(a[v] == 0 or a["trans"] <= a[v] / 2 + 1e-9 for v in names), None,
                           "transition <= half of every clip it touches"))
    pri = {v: c["importance"] for v, c in zip(names, candidates)}
    vkey: dict[str, Callable] = {v: (lambda x, i=ideal[v]: (x == 0, abs(x - i))) for v in names}   # prefer values near utility-share
    vkey["sub_pos"] = lambda x: (x != pos_pref, abs(SUBTITLE_Y[x] - SUBTITLE_Y[pos_pref]))
    vkey["trans"] = lambda x: -x
    return CSP(variables, cons, pri, vkey), {"ideal": ideal, "names": names}


def diagnose_failure(candidates: list[dict], cfg: dict) -> dict:
    """Explain WHY the CSP is infeasible and propose concrete alternatives."""
    target, tol, min_len = cfg["target_duration"], cfg["tolerance"], cfg["min_scene_len"]
    avail = sum(c["eff_duration"] for c in candidates if c["eff_duration"] >= min_len)
    sug = []
    if avail < target - tol:
        sug += [f"Selected scenes provide only {avail:.1f}s of usable content; lower the target to <= {avail + tol:.0f}s",
                "Allow more candidate scenes or disable silence removal to keep more footage"]
    if any(c["eff_duration"] < min_len for c in candidates):
        sug.append(f"Reduce the minimum scene length below {min_len}s")
    if tol < 1.0:
        sug.append("Increase the duration tolerance to at least 1.0 s")
    sug.append("Use shorter transitions or choose 'none'")
    return {"available_seconds": round(avail, 3), "target": target, "tolerance": tol, "suggestions": sug}


def validate_plan(plan: dict) -> dict:
    """Independent post-hoc validation of a finished plan (this gate guards rendering, regardless of the solver)."""
    v: list[dict] = []
    cfg, clips, out = plan["config"], plan["clips"], plan["output"]
    src = plan["source"]
    tol = cfg.get("duration_tolerance", cfg.get("tolerance", 1.0))

    def bad(name, msg):
        v.append({"constraint": name, "message": msg})
    if not clips:
        bad("at_least_one_scene", "plan contains no clips")
    prev_end = None
    for c in clips:
        for s in c["segments"]:
            if s["start"] < 0 or s["end"] < 0:
                bad("valid_timestamps", f"negative timestamp in scene {c['scene_id']}")
            if s["start"] >= s["end"]:
                bad("start_before_end", f"scene {c['scene_id']} segment {s['start']}-{s['end']}")
            if s["end"] > src["duration"] + 1e-3:
                bad("within_source_bounds", f"scene {c['scene_id']} ends at {s['end']} > source {src['duration']}")
        if abs(sum(s["end"] - s["start"] for s in c["segments"]) - c["duration"]) > 0.05:
            bad("clip_duration_consistent", f"scene {c['scene_id']} duration mismatch")
        if c["duration"] < cfg["min_scene_len"] - 1e-6:
            bad("min_scene_duration", f"scene {c['scene_id']} {c['duration']}s < {cfg['min_scene_len']}s")
        if prev_end is not None and c["transition_in"]["duration"] > min(c["duration"], prev_end) / 2 + 1e-6:
            bad("transition_fits_clips", f"transition before scene {c['scene_id']} too long")
        prev_end = c["duration"]
    ids = [c["scene_id"] for c in clips]
    if len(ids) != len(set(ids)):
        bad("no_unintended_overlap", "a scene is used more than once (unintentional timeline overlap)")
    total = out["duration"]
    if abs(total - cfg["target_duration"]) > tol + 1e-6:
        bad("target_duration", f"duration {total:.2f}s outside {cfg['target_duration']}±{tol}")
    if (out["width"], out["height"]) not in ASPECTS.get(cfg["aspect_ratio"], []) and not out.get("preview"):
        bad("export_dimensions_match_aspect", f"{out['width']}x{out['height']} invalid for {cfg['aspect_ratio']}")
    if plan.get("audio_duration") is not None and abs(plan["audio_duration"] - total) > 0.05:
        bad("audio_video_sync", f"audio {plan['audio_duration']}s vs video {total}s")
    y = SUBTITLE_Y.get(plan["subtitles"]["position"], 0.5)
    lo, hi = SAFE_Y[cfg["aspect_ratio"]]
    if plan["subtitles"]["enabled"] and not (lo <= y <= hi):
        bad("subtitle_in_safe_area", f"position {plan['subtitles']['position']} outside safe area")
    for cue in plan.get("subtitle_cues", []):
        if not (0 <= cue["start"] < cue["end"] <= total + 0.05):
            bad("subtitle_timestamps", f"cue {cue['start']}-{cue['end']} invalid")
            break
    return {"status": "valid" if not v else "invalid", "violations": v, "checked": 11}
