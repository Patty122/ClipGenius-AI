"""Upload validation: extension, MIME hint, size limit, and real content probing."""
from __future__ import annotations
from pathlib import Path
from fastapi import UploadFile
from ..config import get_settings
from ..utils.file_utils import safe_filename
from .video_metadata import extract_metadata
from .process import MediaError

CHUNK = 1024 * 1024
VIDEO_MIME_PREFIXES = ("video/",)
GENERIC_MIME = {"application/octet-stream", "binary/octet-stream"}


class ValidationError(ValueError):
    pass


def validate_name_and_mime(upload: UploadFile, audio: bool = False) -> str:
    s = get_settings()
    name = safe_filename(upload.filename or "upload")
    ext = Path(name).suffix.lower()
    allowed = s.allowed_audio_extensions if audio else s.allowed_extensions
    if ext not in allowed:
        raise ValidationError(f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed)}")
    ct = (upload.content_type or "").lower()
    ok_prefix = "audio/" if audio else "video/"
    if ct and not (ct.startswith(ok_prefix) or ct in GENERIC_MIME or (not audio and ct == "application/x-matroska")):
        raise ValidationError(f"Unexpected content type '{ct}'")
    return name


async def save_upload(upload: UploadFile, dest: Path) -> int:
    """Stream to disk enforcing the configured size limit; removes the partial file on failure."""
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    total = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await upload.read(CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValidationError(f"File exceeds the {s.max_upload_mb} MB limit")
                f.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if total == 0:
        dest.unlink(missing_ok=True)
        raise ValidationError("Empty file")
    return total


def validate_video_content(path: Path) -> dict:
    """Probe the real content (not just the extension) and enforce duration limits."""
    s = get_settings()
    try:
        meta = extract_metadata(path)
    except MediaError as e:
        raise ValidationError(f"Not a readable video: {e}") from e
    if meta["duration"] <= 0.5:
        raise ValidationError("Video is too short or has no duration")
    if meta["duration"] > s.max_video_seconds:
        raise ValidationError(f"Video longer than {s.max_video_seconds}s limit")
    if meta["width"] <= 0 or meta["height"] <= 0:
        raise ValidationError("Invalid video dimensions")
    return meta
