"""Subtitle cue mapping (source time -> output timeline), SRT export, and ASS (libass) generation.

ASS is rendered by FFmpeg's libass, which handles Unicode/complex scripts (incl. Gujarati) provided a font that
contains the glyphs is installed. We look for 'Noto Sans Gujarati' (system or backend/assets/fonts) and report a
warning when Gujarati text is present but no suitable font is found.
"""
from __future__ import annotations
import re
import shutil
import subprocess
from functools import lru_cache
from ..config import get_settings
from ..utils.time_utils import ass_time, overlap, srt_time

GUJARATI = re.compile(r"[\u0A80-\u0AFF]")


def clip_timeline(clips: list[dict]) -> list[dict]:
    """Adds out_start/out_end to each clip, accounting for cross-fade overlap."""
    out, running = [], 0.0
    for i, c in enumerate(clips):
        d = c["transition_in"]["duration"] if i > 0 else 0.0
        start = max(0.0, running - d) if i > 0 else 0.0
        out.append({**c, "out_start": round(start, 4), "out_end": round(start + c["duration"], 4)})
        running = start + c["duration"]
    return out


def output_duration(clips: list[dict]) -> float:
    tl = clip_timeline(clips)
    return round(tl[-1]["out_end"], 4) if tl else 0.0


def build_cues(transcript_segments: list[dict], clips: list[dict], max_words: int = 4) -> list[dict]:
    tl = clip_timeline(clips)
    total = tl[-1]["out_end"] if tl else 0.0
    cues: list[dict] = []
    for c in tl:
        off = 0.0
        for seg in c["segments"]:
            a, b = seg["start"], seg["end"]
            for ts in transcript_segments:
                lo, hi = max(a, ts["start"]), min(b, ts["end"])
                if hi - lo < 0.15:
                    continue
                words = ts.get("words") or []
                if words:
                    ws = [w for w in words if lo - 1e-3 <= (w["start"] + w["end"]) / 2 <= hi + 1e-3]
                    ws = [{"w": w["w"], "start": max(w["start"], lo), "end": min(w["end"], hi)} for w in ws]
                else:  # proportional word timing inside the transcript segment
                    toks = ts["text"].split()
                    n = len(toks)
                    dur = max(ts["end"] - ts["start"], 1e-6)
                    ws = []
                    for k, tok in enumerate(toks):
                        w0, w1 = ts["start"] + dur * k / n, ts["start"] + dur * (k + 1) / n
                        if (w0 + w1) / 2 >= lo and (w0 + w1) / 2 <= hi:
                            ws.append({"w": tok, "start": max(w0, lo), "end": min(w1, hi)})
                for i in range(0, len(ws), max_words):
                    grp = ws[i:i + max_words]
                    s0, s1 = grp[0]["start"], grp[-1]["end"]
                    base = c["out_start"] + off - a
                    st, en = max(0.0, base + s0), min(total, base + s1)
                    if en - st < 0.12:
                        continue
                    cues.append({"start": round(st, 3), "end": round(en, 3), "text": " ".join(w["w"] for w in grp),
                                 "words": [{"w": w["w"], "start": round(base + w["start"], 3), "end": round(base + w["end"], 3)} for w in grp]})
            off += b - a
    cues.sort(key=lambda x: x["start"])
    for i in range(len(cues) - 1):          # avoid overlapping cue pairs
        if cues[i]["end"] > cues[i + 1]["start"]:
            cues[i]["end"] = max(cues[i]["start"] + 0.1, cues[i + 1]["start"])
    return cues


def to_srt(cues: list[dict]) -> str:
    return "".join(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n\n" for i, c in enumerate(cues, 1))


def _fc(args: list[str]) -> str:
    exe = shutil.which(args[0])
    if not exe:
        return ""
    try:
        return subprocess.run([exe, *args[1:]], capture_output=True, text=True, timeout=15, shell=False).stdout
    except Exception:
        return ""


@lru_cache(maxsize=1)
def _installed_families() -> set[str]:
    fams: set[str] = set()
    for line in _fc(["fc-list", ":", "family"]).splitlines():
        for f in line.split(","):
            fams.add(f.strip())
    d = get_settings().fonts_dir
    if d.exists():
        for f in d.iterdir():
            if f.suffix.lower() in (".ttf", ".otf"):
                out = _fc(["fc-scan", "--format", "%{family}\\n", str(f)]).strip().splitlines()
                if out:
                    fams.update(x.strip() for x in out[0].split(","))
                else:
                    fams.add(f.stem.split("-")[0])
    return fams


@lru_cache(maxsize=8)
def _family_for_lang(lang: str) -> str | None:
    out = _fc(["fc-list", f":lang={lang}", "family"]).splitlines()
    return out[0].split(",")[0].strip() if out else None


GUJARATI_FONTS = ("Noto Sans Gujarati", "Noto Serif Gujarati", "Nirmala UI", "Shruti", "Gujarati Sangam MN", "Lohit Gujarati", "Samyak Gujarati", "FreeSerif")


def resolve_font(text: str) -> tuple[str, str | None]:
    fams = _installed_families()
    if GUJARATI.search(text):
        for cand in GUJARATI_FONTS:
            if cand in fams:
                return cand, None
        fb = _family_for_lang("gu")
        if fb:
            return fb, None
        return "Noto Sans", ("Gujarati text detected but no Gujarati-capable font was found; add NotoSansGujarati-Regular.ttf to "
                             "backend/assets/fonts (it is bundled by default) or install a Gujarati font")
    for cand in ("Noto Sans", "DejaVu Sans", "Liberation Sans", "Arial", "Helvetica", "Segoe UI"):
        if cand in fams:
            return cand, None
    return "Sans", None


def _ass_color(hex_rgb: str, alpha: int = 0) -> str:
    r, g, b = hex_rgb[1:3], hex_rgb[3:5], hex_rgb[5:7]
    return f"&H{alpha:02X}{b}{g}{r}".upper().replace("&H", "&H")


def build_ass(cues: list[dict], width: int, height: int, style: str, size: int, color: str, position_y: float, text_for_font: str = "") -> tuple[str, str | None]:
    font, warn = resolve_font(text_for_font or " ".join(c["text"] for c in cues))
    fs = max(14, int(size * min(width, height) / 1080 * (1.0 if width <= height else 1.1)))
    bold = -1 if style in ("bold", "animated", "karaoke") else 0
    primary = _ass_color(color if style != "bold" else "#FFE600")
    outline = max(2, int(fs * 0.09))
    hdr = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
           f"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
           f"ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: Default,{font},{fs},{primary},{_ass_color('#FFD400')},&H00000000,&H80000000,{bold},0,0,0,100,100,0,0,1,{outline},1,5,{int(width*0.06)},{int(width*0.06)},10,1\n\n"
           f"[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    x, y = width // 2, int(height * position_y)
    lines = []
    for c in cues:
        txt = c["text"].replace("\\", "").replace("{", "(").replace("}", ")")
        tag = f"{{\\an5\\pos({x},{y})"
        if style == "animated":
            tag += "\\fad(120,100)\\fscx85\\fscy85\\t(0,150,\\fscx100\\fscy100)}"
        elif style == "karaoke" and c.get("words"):
            tag += "}"
            parts, t = [], c["start"]
            for w in c["words"]:
                cs = max(1, int(round((w["end"] - t) * 100)))
                parts.append(f"{{\\kf{cs}}}{w['w'].replace('{','(').replace('}',')')}")
                t = w["end"]
            txt = " ".join(parts)
        else:
            tag += "}"
        lines.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Default,,0,0,0,,{tag}{txt}")
    return hdr + "\n".join(lines) + "\n", warn
