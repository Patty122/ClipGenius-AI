from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...database.connection import get_db, session_scope
from ...models import Project
from ...services import jobs
from ...services.analysis_service import analyze_project, load_scenes
from ..deps import get_project

router = APIRouter(prefix="/api", tags=["analysis"])
HIDE = {"sig_start", "sig_end", "sig_mean", "keep"}


def _run(project_id: str, force: bool):
    with session_scope() as db:
        analyze_project(db, project_id, force)


@router.post("/analyze/{project_id}", status_code=202)
def start_analysis(project_id: str, force: bool = False, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    if not p.original_video_path:
        raise HTTPException(400, "Upload a video first")
    if p.status == "analyzing":
        raise HTTPException(409, "Analysis already running")
    if not (p.analysis and not force):
        p.status, p.progress, p.stage = "analyzing", 0.0, "Queued"
        db.commit()
    jobs.submit(_run, project_id, force)
    return {"project_id": project_id, "status": p.status}


@router.get("/analysis/{project_id}")
def get_analysis(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    if not p.analysis:
        raise HTTPException(404 if p.status != "analyzing" else 202, "Analysis not available yet")
    scenes = [{k: v for k, v in s.items() if k not in HIDE} for s in load_scenes(db, p.project_id)]
    tr = p.transcript or {}
    return {"project_id": p.project_id, "metadata": p.video_metadata, **{k: p.analysis[k] for k in ("summary", "silence", "activity", "timings", "scene_notes")},
            "scenes": scenes, "transcript": {"status": tr.get("status"), "source": tr.get("source"), "message": tr.get("message"), "language": tr.get("language"),
                                             "segments": [{"start": x["start"], "end": x["end"], "text": x["text"]} for x in tr.get("segments", [])]}}
