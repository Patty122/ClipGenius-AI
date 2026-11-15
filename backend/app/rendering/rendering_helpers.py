from sqlalchemy.orm import Session
from ..models import RenderJob
from ..utils.file_utils import new_id


def new_render_job(db: Session, project_id: str, plan_id: str, kind: str, options: dict | None) -> RenderJob:
    job = RenderJob(job_id=new_id("job_"), project_id=project_id, plan_id=plan_id, kind=kind, status="queued", progress=0.0,
                    stage="Queued", export_options=options)
    db.add(job); db.commit()
    return job
