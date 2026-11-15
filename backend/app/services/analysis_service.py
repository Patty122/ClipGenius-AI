"""Perceive stage: metadata -> audio -> transcript -> scenes -> visuals -> scoring -> persistence."""
from __future__ import annotations
import time
from pathlib import Path
import numpy as np
from sqlalchemy.orm import Session
from ..ai.agent_controller import AgentContext, clear_decisions
from ..ai.scene_detector import detect_scenes
from ..ai.scene_scorer import ScoringWeights, score_scenes
from ..ai.speech_analyzer import analyze_audio_activity, transcribe_whisper
from ..ai.video_perception import analyze_scene_visuals
from ..config import get_settings
from ..core.audio_processor import load_audio_mono, rms_db
from ..core.video_metadata import extract_metadata
from ..models import Project, Scene
from ..utils.logger import get_logger
from ..utils.time_utils import overlap

log = get_logger("analysis")


def video_path(p: Project) -> Path:
    return get_settings().uploads_dir / p.original_video_path


def thumb_dir(project_id: str) -> Path:
    return get_settings().uploads_dir / project_id / "thumbs"


def _set(db: Session, p: Project, progress: float, stage: str, status: str = "analyzing"):
    p.progress, p.stage, p.status = progress, stage, status
    db.commit()


def _union_len(iv: list[tuple[float, float]], a: float, b: float) -> float:
    cl = sorted((max(a, x), min(b, y)) for x, y in iv if min(b, y) > max(a, x))
    tot, cur = 0.0, a
    for x, y in cl:
        x = max(x, cur)
        if y > x:
            tot += y - x
            cur = y
    return tot


def analyze_project(db: Session, project_id: str, force: bool = False) -> None:
    p = db.get(Project, project_id)
    if p is None or not p.original_video_path:
        raise ValueError("Project has no uploaded video")
    if p.analysis and p.status in ("analyzed", "planned", "rendered") and not force:
        return  # cached
    ctx = AgentContext(db, project_id)
    clear_decisions(db, project_id, agents={"perception", "speech", "scene"})
    t_start = time.perf_counter()
    timings: dict = {}
    path = video_path(p)
    try:
        _set(db, p, 0.03, "Extracting metadata")
        t = time.perf_counter()
        meta = extract_metadata(path)
        p.video_metadata, p.duration = meta, meta["duration"]
        timings["metadata"] = time.perf_counter() - t
        ctx.log("perceive", "perception", f"Metadata: {meta['width']}x{meta['height']} @ {meta['fps']} fps, {meta['duration']:.1f}s, "
                f"video={meta['video_codec']}, audio={meta['audio_codec'] or 'none'}", "Read with FFprobe")
        dur = meta["duration"]

        silence, activity, samples, sr = [], [(0.0, dur)], None, 16000
        if meta["has_audio"]:
            _set(db, p, 0.10, "Analyzing audio")
            t = time.perf_counter()
            a = analyze_audio_activity(path, dur)
            silence, activity = [tuple(x) for x in a["silence"]], [tuple(x) for x in a["activity"]]
            samples = load_audio_mono(path, sr)
            timings["audio"] = time.perf_counter() - t
            ctx.log("perceive", "speech", f"Audio activity {a['activity_seconds']:.1f}s, silence {a['silence_seconds']:.1f}s "
                    f"({len(silence)} silent interval(s))", f"FFmpeg silencedetect noise={get_settings().silence_db}dB min={get_settings().silence_min_seconds}s")
        else:
            ctx.log("perceive", "speech", "Video has no audio stream", "Speech features will be reported as missing")

        _set(db, p, 0.25, "Transcribing speech")
        t = time.perf_counter()
        tr = p.transcript if (p.transcript and p.transcript.get("status") == "ok" and not force) else None
        if tr is None and p.transcript and p.transcript.get("source") == "imported":
            tr = p.transcript
        if tr is None and meta["has_audio"]:
            tr = transcribe_whisper(path)
        if tr is None:
            tr = {"source": "none", "status": "unavailable", "language": None, "segments": [], "message": "no audio"}
        p.transcript = tr
        timings["transcription"] = time.perf_counter() - t
        if tr["status"] == "ok":
            ctx.log("perceive", "speech", f"Transcript: {len(tr['segments'])} segment(s) from {tr['source']}", f"language={tr.get('language')}")
        else:
            ctx.log("perceive", "speech", "No transcript available", tr["message"] + " -- import an SRT via /api/projects/{id}/transcript or install the Whisper model")

        _set(db, p, 0.45, "Detecting scenes")
        t = time.perf_counter()
        det = detect_scenes(path, dur, silence)
        scenes = det["scenes"]
        timings["scene_detection"] = time.perf_counter() - t
        ctx.log("perceive", "perception", f"Detected {len(scenes)} scene(s)", "; ".join(det["notes"]))

        _set(db, p, 0.60, "Analyzing frames")
        t = time.perf_counter()
        import shutil
        shutil.rmtree(thumb_dir(project_id), ignore_errors=True)
        vis = {v["scene_id"]: v for v in analyze_scene_visuals(path, scenes, thumb_dir(project_id), meta["fps"])}
        timings["visual_features"] = time.perf_counter() - t

        _set(db, p, 0.85, "Scoring scenes")
        speech_iv = [(sg["start"], sg["end"]) for sg in tr["segments"]]
        for sc in scenes:
            a, b = sc["start"], sc["end"]
            d = b - a
            sc["duration"] = round(d, 3)
            txt = [sg["text"] for sg in tr["segments"] if a <= (sg["start"] + sg["end"]) / 2 < b]
            sc["transcript"] = " ".join(txt).strip()
            sc["word_count"] = len(sc["transcript"].split())
            act = _union_len(activity + speech_iv, a, b) if meta["has_audio"] else None
            sc["speech_density"] = round(act / d, 4) if act is not None else None
            sc["silence_pct"] = round(100 * (1 - act / d), 2) if act is not None else None
            sc["silence_seconds"] = round(d - act, 3) if act is not None else None
            sc["loudness_db"] = round(rms_db(samples, sr, a, b), 2) if samples is not None else None
            sc["activity_intervals"] = [[max(a, x), min(b, y)] for x, y in activity if min(b, y) > max(a, x)]
            sc["speech_intervals"] = [[max(a, x), min(b, y)] for x, y in speech_iv if min(b, y) > max(a, x)]
            sc.update({k: v for k, v in vis[sc["scene_id"]].items() if k != "scene_id"})
        score_scenes(scenes, topic=None, weights=ScoringWeights())
        ranked = sorted(scenes, key=lambda s: -s["importance"])
        ctx.log("perceive", "scene", f"Scored {len(scenes)} scene(s); top: " + ", ".join(f"#{s['scene_id']}={s['importance']:.0f}" for s in ranked[:3]),
                ranked[0]["score_detail"]["explanation"] if ranked else "")

        db.query(Scene).filter(Scene.project_id == project_id).delete()
        for sc in scenes:
            db.add(Scene(project_id=project_id, scene_id=sc["scene_id"], start_time=sc["start"], end_time=sc["end"],
                         importance_score=sc["importance"], transcript=sc["transcript"],
                         thumbnail_path=sc.get("thumbnail"), data=sc))
        timings["total"] = time.perf_counter() - t_start
        speech_total = sum(_union_len(activity + speech_iv, s["start"], s["end"]) for s in scenes) if meta["has_audio"] else None
        p.analysis = {
            "silence": [list(x) for x in silence], "activity": [list(x) for x in activity], "scene_notes": det["notes"],
            "timings": {k: round(v, 3) for k, v in timings.items()},
            "summary": {"duration": dur, "scene_count": len(scenes), "speech_duration": round(speech_total, 2) if speech_total is not None else None,
                        "silence_duration": round(sum(b - a for a, b in silence), 2) if meta["has_audio"] else None,
                        "important_scenes": sum(1 for s in scenes if s["importance"] >= 60),
                        "transcript_status": tr["status"], "transcript_source": tr["source"], "transcript_message": tr.get("message", "")},
        }
        p.status, p.stage, p.progress, p.error_message = "analyzed", "Analysis complete", 1.0, None
        db.commit()
        ctx.log("evaluate", "perception", f"Analysis finished in {timings['total']:.1f}s", "Results persisted")
    except Exception as e:
        db.rollback()
        p = db.get(Project, project_id)
        p.status, p.error_message, p.stage = "error", f"{type(e).__name__}: {e}", "Analysis failed"
        db.commit()
        log.exception("analysis failed")
        raise


def load_scenes(db: Session, project_id: str) -> list[dict]:
    return [s.data for s in db.query(Scene).filter(Scene.project_id == project_id).order_by(Scene.scene_id).all()]
