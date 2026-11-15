from __future__ import annotations
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from .api.routes import agents, analysis, editing, projects, rendering
from .config import get_settings
from .core.process import MediaError
from .database.connection import init_db, session_scope
from .models import Project, RenderJob
from .utils.file_utils import rmtree_quiet
from .utils.logger import get_logger

log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    with session_scope() as db:   # interrupted jobs from a previous run are reported, never silently resumed
        for p in db.query(Project).filter(Project.status == "analyzing").all():
            p.status, p.error_message = "error", "Analysis was interrupted (server restarted). Re-run analysis."
        for j in db.query(RenderJob).filter(RenderJob.status.in_(["queued", "running"])).all():
            j.status, j.error_message = "failed", "Render was interrupted (server restarted)."
    for d in s.temp_dir.iterdir() if s.temp_dir.exists() else []:   # stale temp cleanup (>24h)
        if time.time() - d.stat().st_mtime > 86400:
            rmtree_quiet(d) if d.is_dir() else d.unlink(missing_ok=True)
    yield


app = FastAPI(title="ClipGenius AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=list(get_settings().cors_origins), allow_methods=["*"], allow_headers=["*"])
for r in (projects.router, analysis.router, editing.router, rendering.router, agents.router):
    app.include_router(r)


@app.exception_handler(MediaError)
async def media_err(_: Request, e: MediaError):
    return JSONResponse(status_code=422, content={"detail": f"Media processing error: {str(e)[:300]}"})


@app.exception_handler(Exception)
async def generic_err(_: Request, e: Exception):
    log.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})   # no paths / internals leaked


@app.get("/api/health")
def health():
    s = get_settings()
    from .rendering.subtitle_renderer import _installed_families
    fams = _installed_families()
    return {"status": "ok", "ffmpeg": bool(shutil.which(s.ffmpeg_bin)), "ffprobe": bool(shutil.which(s.ffprobe_bin)), "whisper_model": s.whisper_model,
            "llm_configured": bool(s.llm_api_key), "gujarati_font": any("gujarati" in f.lower() for f in fams)}


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
