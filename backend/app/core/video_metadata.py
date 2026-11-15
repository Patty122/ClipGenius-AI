"""FFprobe-based metadata extraction."""
from __future__ import annotations
import json
from pathlib import Path
from ..config import get_settings
from .process import MediaError, run_media


def _fps(rate: str | None) -> float:
    try:
        n, d = (rate or "0/1").split("/")
        return round(float(n) / float(d), 3) if float(d) else 0.0
    except Exception:
        return 0.0


def probe(path: Path) -> dict:
    s = get_settings()
    r = run_media([s.ffprobe_bin, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                  timeout=s.ffprobe_timeout)
    if r.returncode != 0:
        raise MediaError(f"ffprobe could not read file: {r.stderr.strip()[:300]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError as e:
        raise MediaError("ffprobe returned invalid JSON") from e


def extract_metadata(path: Path) -> dict:
    data = probe(path)
    streams = data.get("streams", [])
    v = next((x for x in streams if x.get("codec_type") == "video" and x.get("disposition", {}).get("attached_pic", 0) != 1), None)
    a = next((x for x in streams if x.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    if v is None:
        raise MediaError("No video stream found")
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    rotation = int(v.get("tags", {}).get("rotate", rotation) or rotation)
    if abs(rotation) % 180 == 90:
        w, h = h, w
    duration = float(fmt.get("duration") or v.get("duration") or 0)
    return {
        "duration": round(duration, 3), "width": w, "height": h, "fps": _fps(v.get("avg_frame_rate") or v.get("r_frame_rate")),
        "video_codec": v.get("codec_name"), "pixel_format": v.get("pix_fmt"),
        "audio_codec": a.get("codec_name") if a else None, "has_audio": a is not None,
        "sample_rate": int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        "channels": a.get("channels") if a else None,
        "bit_rate": int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
        "format_name": fmt.get("format_name"), "size_bytes": int(fmt.get("size", 0)),
        "rotation": rotation, "audio_stream_count": sum(1 for x in streams if x.get("codec_type") == "audio"),
    }
