from __future__ import annotations
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from ...ai.speech_analyzer import imported_transcript, parse_srt
from ...config import get_settings
from ...core.file_validation import ValidationError, save_upload, validate_name_and_mime, validate_video_content
from ...database.connection import get_db
from ...models import Project, Scene
from ...schemas.project import ProjectCreate, TranscriptImport, project_out
from ...utils.file_utils import ensure_within, new_id, rmtree_quiet
from ..deps import get_project

router = APIRouter(prefix="/api", tags=["projects"])


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(project_id=new_id(), project_name=body.project_name.strip())
    db.add(p); db.commit()
    return project_out(p)


@router.get("/projects")
def list_projects(db: Session = Depends(get_db)):
    return [project_out(p) for p in db.query(Project).order_by(Project.created_at.desc()).all()]


@router.get("/projects/{project_id}")
def project_detail(p: Project = Depends(get_project)):
    return project_out(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(p: Project = Depends(get_project), db: Session = Depends(get_db)):
    s = get_settings()
    for j in p.jobs:
        rmtree_quiet(s.outputs_dir / j.job_id)
    rmtree_quiet(s.uploads_dir / p.project_id)
    db.delete(p); db.commit()


@router.post("/upload", status_code=201)
async def upload_video(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    s = get_settings()
    try:
        name = validate_name_and_mime(file)
        dest = s.uploads_dir / p.project_id / ("original_" + name)
        ensure_within(s.uploads_dir, dest)
        await save_upload(file, dest)
        try:
            meta = validate_video_content(dest)
        except ValidationError:
            dest.unlink(missing_ok=True)
            raise
    except ValidationError as e:
        raise HTTPException(400, str(e))
    p.original_video_path = str(dest.relative_to(s.uploads_dir))
    p.original_filename, p.video_metadata, p.duration = name, meta, meta["duration"]
    p.status, p.analysis, p.error_message, p.progress, p.stage = "uploaded", None, None, 0.0, "Uploaded"
    db.query(Scene).filter(Scene.project_id == p.project_id).delete()
    db.commit()
    return project_out(p)


@router.post("/projects/{project_id}/music", status_code=201)
async def upload_music(file: UploadFile = File(...), p: Project = Depends(get_project), db: Session = Depends(get_db)):
    s = get_settings()
    try:
        name = validate_name_and_mime(file, audio=True)
        dest = s.uploads_dir / p.project_id / ("music_" + name)
        await save_upload(file, dest)
    except ValidationError as e:
        raise HTTPException(400, str(e))
    p.music_path = str(dest.relative_to(s.uploads_dir)); db.commit()
    return project_out(p)


@router.post("/projects/{project_id}/transcript")
def import_transcript(body: TranscriptImport, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    segs = parse_srt(body.srt)
    if not segs:
        raise HTTPException(400, "No valid SRT cues found")
    p.transcript = imported_transcript(segs); db.commit()
    return {"segments": len(segs), "note": "Re-run analysis (force=true) to apply the imported transcript to scene scoring."}


@router.get("/projects/{project_id}/video")
def stream_video(p: Project = Depends(get_project)):
    if not p.original_video_path:
        raise HTTPException(404, "No video")
    path = ensure_within(get_settings().uploads_dir, get_settings().uploads_dir / p.original_video_path)
    return FileResponse(path, media_type="video/mp4" if path.suffix.lower() in (".mp4", ".m4v") else None, filename=None)


@router.get("/projects/{project_id}/thumbnails/{scene_id}")
def thumbnail(scene_id: int, p: Project = Depends(get_project), db: Session = Depends(get_db)):
    sc = db.query(Scene).filter(Scene.project_id == p.project_id, Scene.scene_id == scene_id).first()
    if not sc or not sc.thumbnail_path:
        raise HTTPException(404, "No thumbnail")
    s = get_settings()
    path = ensure_within(s.uploads_dir, s.uploads_dir / p.project_id / "thumbs" / sc.thumbnail_path)
    return FileResponse(path, media_type="image/jpeg")
