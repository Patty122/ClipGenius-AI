"""Scene boundary detection: PySceneDetect ContentDetector + pause-based refinement of long scenes."""
from __future__ import annotations
from pathlib import Path
from ..config import get_settings
from ..utils.logger import get_logger

log = get_logger("scenes")


def detect_cuts(path: Path, threshold: float) -> list[tuple[float, float]]:
    from scenedetect import ContentDetector, detect
    scenes = detect(str(path), ContentDetector(threshold=threshold), show_progress=False)
    return [(float(getattr(a, "seconds", None) if hasattr(a, "seconds") else a.get_seconds()), float(getattr(b, "seconds", None) if hasattr(b, "seconds") else b.get_seconds())) for a, b in scenes]


def _split_at_silences(a: float, b: float, silences: list[tuple[float, float]], max_len: float, min_len: float) -> list[tuple[float, float, str]]:
    """Split a long scene at the midpoint of its longest interior silence, recursively."""
    if b - a <= max_len:
        return [(a, b, "pause" if False else "cut")]
    inner = [(s0, s1) for s0, s1 in silences if s0 > a + min_len and s1 < b - min_len]
    if inner:
        s0, s1 = max(inner, key=lambda x: x[1] - x[0])
        mid = (s0 + s1) / 2
        return [(x0, x1, "pause") for x0, x1, _ in _split_at_silences(a, mid, silences, max_len, min_len)] + \
               [(x0, x1, "pause") for x0, x1, _ in _split_at_silences(mid, b, silences, max_len, min_len)]
    n = int((b - a) // max_len) + 1  # last resort: equal windows (flagged)
    step = (b - a) / n
    return [(a + i * step, a + (i + 1) * step, "window") for i in range(n)]


def detect_scenes(path: Path, duration: float, silences: list[tuple[float, float]]) -> dict:
    s = get_settings()
    method_notes = []
    try:
        cuts = detect_cuts(path, s.scene_threshold)
        method_notes.append(f"PySceneDetect ContentDetector(threshold={s.scene_threshold}) found {len(cuts)} visual scene(s)")
    except Exception as e:
        log.warning("scenedetect failed: %s", e)
        cuts = []
        method_notes.append(f"PySceneDetect failed ({type(e).__name__}); using pause/window segmentation")
    if not cuts:
        cuts = [(0.0, duration)]
    raw: list[tuple[float, float, str]] = []
    for a, b in cuts:
        if b - a > s.max_scene_seconds:
            parts = _split_at_silences(a, b, silences, s.max_scene_seconds, s.min_scene_seconds)
            if len(parts) > 1:
                method_notes.append(f"split {b-a:.1f}s scene [{a:.1f}-{b:.1f}] into {len(parts)} parts ({parts[0][2]}-based)")
            raw.extend(parts)
        else:
            raw.append((a, b, "visual-cut"))
    raw[0] = (0.0, raw[0][1], raw[0][2])
    raw[-1] = (raw[-1][0], duration, raw[-1][2])
    merged: list[list] = []  # merge scenes shorter than the minimum into the previous one
    for a, b, m in raw:
        if merged and (b - a) < s.min_scene_seconds:
            merged[-1][1] = b
        else:
            merged.append([a, b, m])
    if len(merged) > 1 and merged[0][1] - merged[0][0] < s.min_scene_seconds:
        merged[1][0] = merged[0][0]
        merged.pop(0)
    scenes = [{"scene_id": i, "start": round(a, 3), "end": round(b, 3), "boundary_method": m} for i, (a, b, m) in enumerate(merged)]
    return {"scenes": scenes, "notes": method_notes}
