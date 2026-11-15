from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field
from ..schemas.editing import ExportOptions


class ProjectCreate(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=200)


class PlanRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    overrides: Optional[dict[str, Any]] = None


class RenderRequest(BaseModel):
    export: Optional[ExportOptions] = None


class TranscriptImport(BaseModel):
    srt: str = Field(..., min_length=10, max_length=2_000_000)


def project_out(p) -> dict:
    return {"project_id": p.project_id, "project_name": p.project_name, "original_filename": p.original_filename, "duration": p.duration,
            "status": p.status, "stage": p.stage, "progress": p.progress, "error_message": p.error_message, "created_at": p.created_at.isoformat() if p.created_at else None,
            "has_video": bool(p.original_video_path), "has_music": bool(p.music_path), "metadata": p.video_metadata,
            "analysis_summary": (p.analysis or {}).get("summary"), "transcript_status": (p.transcript or {}).get("status")}


def job_out(j) -> dict:
    return {"job_id": j.job_id, "project_id": j.project_id, "kind": j.kind, "status": j.status, "progress": j.progress, "stage": j.stage,
            "error_message": j.error_message, "created_at": j.created_at.isoformat(), "report": j.report,
            "download_url": f"/api/render/{j.job_id}/download" if j.status == "completed" else None}
