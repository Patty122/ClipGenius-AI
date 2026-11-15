"""Audio analysis: FFmpeg silencedetect, loudness measurement and silence-removal interval planning."""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
from ..config import get_settings
from .process import MediaError, run_media

_START = re.compile(r"silence_start:\s*(-?[\d.]+)")
_END = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silence(path: Path, duration: float, noise_db: float | None = None, min_dur: float | None = None) -> list[tuple[float, float]]:
    s = get_settings()
    noise_db = s.silence_db if noise_db is None else noise_db
    min_dur = s.silence_min_seconds if min_dur is None else min_dur
    r = run_media([s.ffmpeg_bin, "-hide_banner", "-nostdin", "-i", str(path), "-vn", "-af",
                   f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"], timeout=s.ffmpeg_timeout)
    if r.returncode != 0:
        raise MediaError(f"silencedetect failed: {r.stderr[-300:]}")
    out: list[tuple[float, float]] = []
    cur: float | None = None
    for line in r.stderr.splitlines():
        m = _START.search(line)
        if m:
            cur = max(0.0, float(m.group(1)))
            continue
        m = _END.search(line)
        if m and cur is not None:
            out.append((cur, min(duration, float(m.group(1)))))
            cur = None
    if cur is not None:  # silence runs to the end of the file
        out.append((cur, duration))
    return [(a, b) for a, b in out if b - a > 1e-3]


def invert_intervals(silences: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    """Audio-activity intervals = complement of silence."""
    res, t = [], 0.0
    for a, b in sorted(silences):
        if a > t + 1e-3:
            res.append((t, a))
        t = max(t, b)
    if duration > t + 1e-3:
        res.append((t, duration))
    return res


def load_audio_mono(path: Path, sr: int = 16000) -> np.ndarray:
    s = get_settings()
    r = run_media([s.ffmpeg_bin, "-hide_banner", "-nostdin", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr),
                   "-f", "f32le", "-"], timeout=s.ffmpeg_timeout, binary_out=True)
    if r.returncode != 0:
        raise MediaError(f"audio decode failed: {r.stderr[-300:]!r}")
    return np.frombuffer(r.stdout, dtype=np.float32)


def rms_db(samples: np.ndarray, sr: int, start: float, end: float) -> float:
    seg = samples[int(start * sr): int(end * sr)]
    if seg.size == 0:
        return -90.0
    rms = float(np.sqrt(np.mean(np.square(seg.astype(np.float64)))))
    return max(-90.0, 20 * np.log10(rms + 1e-9))


def merge_intervals(iv: list[tuple[float, float]], gap: float = 0.0) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def compute_keep_intervals(scene_start: float, scene_end: float, activity: list[tuple[float, float]],
                           speech_segments: list[tuple[float, float]], pad: float, min_piece: float = 0.2) -> list[tuple[float, float]]:
    """Intervals of a scene to KEEP when silence removal is on.

    Speech is never dropped for being quiet: transcript intervals are unioned with detected audio activity,
    then every kept interval is padded on both sides so word onsets/releases are not clipped.
    """
    pieces = []
    for a, b in list(activity) + list(speech_segments):
        lo, hi = max(a, scene_start), min(b, scene_end)
        if hi - lo > 1e-3:
            pieces.append((max(scene_start, lo - pad), min(scene_end, hi + pad)))
    merged = merge_intervals(pieces, gap=0.02)
    return [(a, b) for a, b in merged if b - a >= min_piece]
