"""Act + Evaluate stage: render a VALID plan with FFmpeg, verify with FFprobe, and build the execution report."""
from __future__ import annotations
import shutil
import time
from pathlib import Path
from ..ai.agent_controller import AgentContext
from ..algorithms.csp import validate_plan
from ..config import get_settings
from ..database.connection import session_scope
from ..models import EditingPlan, Project, RenderJob
from ..rendering.export_manager import verify_output
from ..rendering.ffmpeg_engine import render
from ..rendering.subtitle_renderer import build_ass, to_srt
from ..utils.file_utils import rmtree_quiet
from ..utils.logger import get_logger

log = get_logger("render")


def _even(x: float) -> int:
    return max(2, int(round(x / 2) * 2))


def preview_dims(W: int, H: int, short_side: int = 360) -> tuple[int, int]:
    f = short_side / min(W, H)
    return _even(W * f), _even(H * f)


def build_report(project: Project, plan: dict, job: RenderJob, verification: dict, render_seconds: float) -> dict:
    a = plan["algorithms"]
    astar, csp, exp = a.get("astar", {}), a.get("csp", {}), a.get("expert", {})
    fired = sorted({r["rule_id"] for r in exp.get("rules", []) if r["fired"]})
    total_scenes = project.analysis["summary"]["scene_count"]
    meta = verification.get("metadata") or {}
    return {
        "original_duration": project.duration, "final_duration_measured": meta.get("duration"), "final_duration_planned": plan["output"]["duration"],
        "target_duration": plan["config"]["target_duration"], "duration_tolerance": plan["config"]["duration_tolerance"],
        "scenes_detected": total_scenes, "scenes_selected": len(plan["clips"]),
        "removed_segments": {"scenes_removed": len(plan["removed_scenes"]), "silence_intervals_trimmed": plan.get("stats", {}).get("silence_intervals_removed", 0),
                             "silence_seconds_trimmed": plan.get("stats", {}).get("silence_seconds_removed", 0)},
        "astar": {"algorithm": astar.get("algorithm"), "optimal": astar.get("optimal"), "nodes_expanded": astar.get("expanded"), "nodes_generated": astar.get("generated"),
                  "states_explored": astar.get("explored_states"), "path_cost": astar.get("cost"), "chronological_cost": astar.get("chronological_cost"),
                  "applied_order": [c["scene_id"] for c in plan["clips"]], "search_seconds": astar.get("seconds")},
        "csp": {"status": csp.get("status"), "nodes": csp.get("nodes"), "backtracks": csp.get("backtracks"), "independent_validation": plan["validation"]["status"],
                "violations": plan["validation"]["violations"]},
        "expert_rules_triggered": fired, "backward_chaining_vertical_reel_ready": (exp.get("backward") or {}).get("proved"),
        "subtitle_cues": plan["subtitles"]["cue_count"],
        "processing_seconds": {"analysis": (project.analysis or {}).get("timings", {}).get("total"), "planning": plan.get("planning_seconds"), "render": round(render_seconds, 2)},
        "output_verification": {"ok": verification["ok"], "checks": verification["checks"]}, "job_kind": job.kind,
        "warnings": plan.get("warnings", []),
    }


def run_render_job(job_id: str) -> None:
    s = get_settings()
    with session_scope() as db:
        job = db.get(RenderJob, job_id)
        project = db.get(Project, job.project_id)
        plan_row = db.get(EditingPlan, job.plan_id)
        ctx = AgentContext(db, project.project_id)
        work = s.temp_dir / job_id
        t0 = time.perf_counter()
        try:
            plan = plan_row.data
            job.status, job.stage, job.progress = "running", "Validating plan", 0.02
            db.commit()
            # hard gate: never render an invalid plan
            val = validate_plan(plan)
            if plan_row.validation_status != "valid" or val["status"] != "valid":
                raise ValueError("Plan failed validation and cannot be rendered: " + "; ".join(v["message"] for v in val["violations"]))
            ctx.log("validate", "constraint", f"Pre-render validation passed ({val['checked']} checks)", "Render gate")
            W, H = plan["output"]["width"], plan["output"]["height"]
            preview = job.kind == "preview"
            if preview:
                W, H = preview_dims(W, H)
            out_dir = s.outputs_dir / job_id
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"clipgenius_{project.project_id}_{job_id}.mp4"
            ass_text, warn = None, None
            cues = plan["subtitle_cues"]
            opts = job.export_options or {}
            if plan["subtitles"]["enabled"] and cues:
                from ..algorithms.csp import SUBTITLE_Y
                ass_text, warn = build_ass(cues, W, H, plan["config"]["subtitle_style"], plan["config"]["subtitle_size"],
                                           plan["config"]["subtitle_color"], SUBTITLE_Y[plan["subtitles"]["position"]])
                if not preview:
                    (out_dir / "subtitles.srt").write_text(to_srt(cues), encoding="utf-8")
                if warn:
                    plan.setdefault("warnings", []).append(warn)
                if opts.get("burn_subtitles") is False:
                    ass_text = None
            music = (s.uploads_dir / project.music_path) if (plan["config"]["music_enabled"] and project.music_path) else None
            job.stage = "Rendering"
            db.commit()
            ctx.log("act", "render", f"Rendering {'preview' if preview else 'final'} {W}x{H}, {len(plan['clips'])} clip(s), expected {plan['output']['duration']:.1f}s", "FFmpeg filter_complex")

            last = {"t": 0.0}

            def prog(x: float):
                if time.time() - last["t"] > 0.4 or x >= 1.0:
                    last["t"] = time.time()
                    with session_scope() as d2:
                        j = d2.get(RenderJob, job_id)
                        j.progress = round(0.05 + 0.9 * x, 4)
            info = render(plan, s.uploads_dir / project.original_video_path, out, work, W, H, preview, ass_text, music, prog)
            job.stage, job.progress = "Verifying output", 0.96
            db.commit()
            ver = verify_output(out, W, H, info["expected_duration"], bool(plan["source"]["has_audio"]))
            if not ver["ok"]:
                failed = [c for c in ver["checks"] if not c["ok"]]
                raise RuntimeError("Output verification failed: " + "; ".join(f"{c['check']} ({c['detail']})" for c in failed))
            job.report = build_report(project, plan, job, ver, time.perf_counter() - t0)
            job.output_path = str(out.relative_to(s.outputs_dir))
            job.status, job.progress, job.stage = "completed", 1.0, "Done"
            project.status = "rendered" if not preview else project.status
            db.commit()
            ctx.log("evaluate", "render", f"Output verified: {ver['metadata']['duration']:.2f}s {ver['metadata']['width']}x{ver['metadata']['height']} {ver['metadata']['video_codec']}",
                    f"{len(ver['checks'])} FFprobe/decode checks passed")
        except Exception as e:
            db.rollback()
            job = db.get(RenderJob, job_id)
            job.status, job.error_message, job.stage = "failed", f"{type(e).__name__}: {e}"[:1500], "Failed"
            db.commit()
            log.exception("render failed")
            try:
                ctx.log("evaluate", "render", "Render failed", job.error_message)
            except Exception:
                pass
        finally:
            rmtree_quiet(work)
