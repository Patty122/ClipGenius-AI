from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ...config import get_settings
from ...database.connection import get_db
from ...models import Project, RenderJob
from ...rendering.rendering_helpers import new_render_job
from ...schemas.project import RenderRequest, job_out
from ...services import jobs
from ...services.planning_service import generate_plan, latest_plan
from ...services.rendering_service import run_render_job
from ...utils.file_utils import ensure_within
from ..deps import get_project

router = APIRouter(prefix="/api", tags=["rendering"])


@router.post("/render/{project_id}", status_code=202)
def start_render(body: RenderRequest | None = None, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    row = latest_plan(db, p.project_id)
    if not row:
        raise HTTPException(409, "Create and review an editing plan first")
    ex = (body.export.model_dump(exclude_none=True) if body and body.export else {})
    overrides = {k: ex[k] for k in ("quality", "aspect_ratio", "subtitles", "music_enabled", "normalize_audio") if k in ex}
    changed = {k: v for k, v in overrides.items() if row.data["config"].get(k) != v}
    if changed:   # export option differs from the reviewed plan -> re-plan so the CSP validates the new configuration
        if "aspect_ratio" in changed and "quality" not in overrides:
            overrides["quality"] = row.data["config"]["quality"]
        overrides.setdefault("target_duration", row.data["config"]["target_duration"])
        overrides["resolution"] = None
        row = generate_plan(db, p.project_id, row.data["prompt"], {**row.data["config"], **overrides, "resolution": None, "duration_tolerance": row.data["config"]["duration_tolerance"]})
    if row.validation_status != "valid":
        raise HTTPException(409, {"message": "The editing plan failed validation and will not be rendered", "violations": row.data["validation"]["violations"],
                                  "suggestions": row.data["validation"].get("suggestions", [])})
    running = db.query(RenderJob).filter(RenderJob.project_id == p.project_id, RenderJob.kind == "final", RenderJob.status.in_(["queued", "running"])).first()
    if running:
        raise HTTPException(409, "A render is already in progress")
    job = new_render_job(db, p.project_id, row.plan_id, "final", ex)
    jobs.submit(run_render_job, job.job_id)
    db.refresh(job)
    return job_out(job)


@router.get("/render/{job_id}/status")
def render_status(job_id: str, db: Session = Depends(get_db)):
    j = db.get(RenderJob, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return job_out(j)


@router.get("/render/{job_id}/download")
def download(job_id: str, db: Session = Depends(get_db)):
    j = db.get(RenderJob, job_id)
    if not j or j.status != "completed" or not j.output_path:
        raise HTTPException(404, "Rendered file not available")
    s = get_settings()
    path = ensure_within(s.outputs_dir, s.outputs_dir / j.output_path)
    if not path.exists():
        raise HTTPException(410, "Rendered file was removed")
    return FileResponse(path, media_type="video/mp4", filename=f"clipgenius_{j.project_id}.mp4" if j.kind == "final" else "preview.mp4")


@router.get("/projects/{project_id}/jobs")
def project_jobs(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    return [job_out(j) for j in reversed(db.query(RenderJob).filter(RenderJob.project_id == p.project_id).order_by(RenderJob.created_at).all())]


@router.get("/report/{project_id}")
def execution_report(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    j = db.query(RenderJob).filter(RenderJob.project_id == p.project_id, RenderJob.kind == "final", RenderJob.status == "completed").order_by(RenderJob.created_at.desc()).first()
    if not j:
        raise HTTPException(404, "No completed final render yet")
    return {"job_id": j.job_id, **j.report}
