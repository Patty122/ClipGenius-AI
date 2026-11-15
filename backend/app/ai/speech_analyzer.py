"""Speech Analysis Agent: transcription (faster-whisper), SRT import, and audio-activity analysis.

Whisper is a THIRD-PARTY pretrained model. If its weights cannot be loaded (e.g. offline) we report
status="unavailable" with the real error and return NO transcript -- we never invent text.
"""
from __future__ import annotations
import re
from pathlib import Path
from ..config import get_settings
from ..core.audio_processor import detect_silence, invert_intervals
from ..utils.logger import get_logger
from ..utils.time_utils import parse_srt_time

log = get_logger("speech")
_MODEL_CACHE: dict = {}


def transcribe_whisper(path: Path, language: str | None = None) -> dict:
    s = get_settings()
    try:
        from faster_whisper import WhisperModel
        key = (s.whisper_model, s.whisper_device, s.whisper_compute_type)
        if key not in _MODEL_CACHE:
            _MODEL_CACHE[key] = WhisperModel(s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type)
        model = _MODEL_CACHE[key]
        kw = dict(word_timestamps=True, language=language, condition_on_previous_text=False)
        try:   # Silero VAD (bundled with faster-whisper) suppresses hallucinated text over silence/music
            segs, info = model.transcribe(str(path), vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, **kw)
            segs = list(segs)
        except Exception as ve:
            log.warning("VAD transcription failed (%s); retrying without VAD", type(ve).__name__)
            segs, info = model.transcribe(str(path), **kw)
            segs = list(segs)
        out = []
        for i, sg in enumerate(segs):
            words = [{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)} for w in (sg.words or []) if w.word.strip()]
            out.append({"id": i, "start": round(sg.start, 3), "end": round(sg.end, 3), "text": sg.text.strip(), "words": words})
        return {"source": f"whisper:{s.whisper_model}", "status": "ok", "language": info.language, "segments": out, "message": ""}
    except Exception as e:  # model missing / offline / unsupported audio
        log.warning("Whisper unavailable: %s", e)
        return {"source": f"whisper:{s.whisper_model}", "status": "unavailable", "language": None, "segments": [],
                "message": f"{type(e).__name__}: {str(e)[:240]}"}


_SRT_BLOCK = re.compile(r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})")


def parse_srt(text: str) -> list[dict]:
    """Parse SRT text into transcript segments (no word timing)."""
    segs, lines, i = [], text.replace("\r", "").split("\n"), 0
    while i < len(lines):
        m = _SRT_BLOCK.search(lines[i])
        if not m:
            i += 1
            continue
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip():
            buf.append(lines[i].strip())
            i += 1
        t0, t1 = parse_srt_time(m.group(1).ljust(12, "0")[:12] if "," in m.group(1) else m.group(1).replace(".", ",")), parse_srt_time(m.group(2).replace(".", ","))
        if buf and t1 > t0:
            segs.append({"id": len(segs), "start": round(t0, 3), "end": round(t1, 3), "text": " ".join(buf), "words": []})
    return segs


def imported_transcript(segments: list[dict], source: str = "imported") -> dict:
    return {"source": source, "status": "ok", "language": None, "segments": segments, "message": "Imported by user"}


def analyze_audio_activity(path: Path, duration: float) -> dict:
    """FFmpeg silencedetect -> silence + audio-activity intervals.

    NOTE: this measures *audio energy*, not whether the sound is speech. It is used as the speech-activity
    proxy only; transcript data (when available) refines it.
    """
    sil = detect_silence(path, duration)
    act = invert_intervals(sil, duration)
    return {"silence": [list(x) for x in sil], "activity": [list(x) for x in act],
            "silence_seconds": round(sum(b - a for a, b in sil), 3), "activity_seconds": round(sum(b - a for a, b in act), 3)}
