from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from ...algorithms.csp import validate_plan
from ...database.connection import get_db
from ...models import Project
from ...rendering.rendering_helpers import new_render_job  # noqa
from ...rendering.subtitle_renderer import to_srt
from ...schemas.project import PlanRequest, job_out
from ...services import jobs
from ...services.planning_service import generate_plan, latest_plan
from ...services.rendering_service import run_render_job
from ..deps import get_project

router = APIRouter(prefix="/api/edit", tags=["editing"])


def plan_out(row) -> dict:
    d = dict(row.data)
    alg = dict(d["algorithms"])
    alg["astar"] = {k: v for k, v in alg["astar"].items() if k not in ("cost_components",)}
    return {"plan_id": row.plan_id, "project_id": row.project_id, "validation_status": row.validation_status, "created_at": row.created_at.isoformat(),
            **{k: d[k] for k in ("prompt", "config", "source", "clips", "removed_scenes", "operations", "output", "subtitles", "subtitle_cues", "validation",
                                 "warnings", "stats", "planning_seconds") if k in d}, "algorithms": alg, "renderable": row.validation_status == "valid"}


@router.post("/{project_id}/plan", status_code=201)
def create_plan(body: PlanRequest, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    if not p.analysis:
        raise HTTPException(409, "Analyze the project before planning")
    try:
        row = generate_plan(db, p.project_id, body.prompt, body.overrides)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        from pydantic import ValidationError
        if isinstance(e, ValidationError):
            raise HTTPException(422, "Invalid editing configuration: " + "; ".join(x["msg"] for x in e.errors()))
        raise
    return plan_out(row)


@router.get("/{project_id}/plan")
def get_plan(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    row = latest_plan(db, p.project_id)
    if not row:
        raise HTTPException(404, "No plan yet")
    return plan_out(row)


@router.post("/{project_id}/validate")
def validate(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    row = latest_plan(db, p.project_id)
    if not row:
        raise HTTPException(404, "No plan yet")
    if row.validation_status == "infeasible":
        return {"status": "infeasible", "violations": row.data["validation"]["violations"], "suggestions": row.data["validation"].get("suggestions", [])}
    res = validate_plan(row.data)
    row.validation_status = res["status"]; db.commit()
    return res


@router.post("/{project_id}/preview", status_code=202)
def preview(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    row = latest_plan(db, p.project_id)
    if not row or row.validation_status != "valid":
        raise HTTPException(409, "A valid plan is required before preview")
    job = new_render_job(db, p.project_id, row.plan_id, "preview", None)
    jobs.submit(run_render_job, job.job_id)
    db.refresh(job)
    return job_out(job)


@router.get("/{project_id}/subtitles.srt", response_class=PlainTextResponse)
def srt(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    row = latest_plan(db, p.project_id)
    if not row or not row.data.get("subtitle_cues"):
        raise HTTPException(404, "No subtitles in the current plan")
    return PlainTextResponse(to_srt(row.data["subtitle_cues"]), headers={"Content-Disposition": 'attachment; filename="subtitles.srt"'})
