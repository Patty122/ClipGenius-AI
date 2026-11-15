"""Output verification with FFprobe + a full decode test. 'Success' is only declared if every check passes."""
from __future__ import annotations
from pathlib import Path
from ..config import get_settings
from ..core.process import run_media
from ..core.video_metadata import extract_metadata


def verify_output(path: Path, expected_w: int, expected_h: int, expected_duration: float, expect_audio: bool, tol: float = 0.6) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
    exists = path.exists() and path.stat().st_size > 1024
    add("file_exists", exists, f"{path.stat().st_size if path.exists() else 0} bytes")
    meta = None
    if exists:
        try:
            meta = extract_metadata(path)
        except Exception as e:
            add("ffprobe_readable", False, str(e)[:200])
    if meta:
        add("ffprobe_readable", True, f"{meta['format_name']}")
        add("container_mp4", "mp4" in (meta["format_name"] or ""), meta["format_name"] or "")
        add("video_codec_h264", meta["video_codec"] == "h264", str(meta["video_codec"]))
        add("pixel_format_yuv420p", meta["pixel_format"] == "yuv420p", str(meta["pixel_format"]))
        add("dimensions", (meta["width"], meta["height"]) == (expected_w, expected_h), f"{meta['width']}x{meta['height']} (expected {expected_w}x{expected_h})")
        add("duration", abs(meta["duration"] - expected_duration) <= tol, f"{meta['duration']:.2f}s (expected {expected_duration:.2f}s ±{tol})")
        add("audio_stream", meta["has_audio"] == expect_audio, f"has_audio={meta['has_audio']}")
        s = get_settings()
        r = run_media([s.ffmpeg_bin, "-v", "error", "-nostdin", "-i", str(path), "-f", "null", "-"], timeout=s.ffmpeg_timeout)
        add("full_decode_no_errors", r.returncode == 0 and not r.stderr.strip(), (r.stderr.strip()[:200] or "decoded cleanly"))
    return {"ok": all(c["ok"] for c in checks) and bool(checks), "checks": checks, "metadata": meta}
