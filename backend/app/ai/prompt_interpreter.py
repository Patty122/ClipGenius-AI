"""Natural-language instruction -> validated EditConfig.

Deterministic local parser (always available) + optional LLM (JSON only, validated by Pydantic).
LLM output is DATA: it is only ever parsed as JSON into EditConfig fields; nothing is executed.
"""
from __future__ import annotations
import json
import re
from pydantic import ValidationError
from ..config import get_settings
from ..schemas.editing import EditConfig
from ..utils.logger import get_logger

log = get_logger("prompt")
_NUM = r"(\d+(?:\.\d+)?)"


def parse_local(prompt: str, base: dict | None = None) -> tuple[dict, list[str]]:
    p = (prompt or "").lower()
    cfg: dict = dict(base or {})
    notes: list[str] = []

    def has(*words): return any(re.search(w, p) for w in words)

    if has(r"\breel", r"instagram", r"tiktok", r"\bshorts?\b", r"vertical", r"9:16", r"portrait", r"story"):
        cfg["aspect_ratio"] = "9:16"; notes.append("vertical platform keywords -> 9:16")
    if has(r"landscape", r"16:9", r"youtube video", r"widescreen", r"horizontal"):
        cfg["aspect_ratio"] = "16:9"; notes.append("landscape keywords -> 16:9")
    if has(r"square", r"1:1"):
        cfg["aspect_ratio"] = "1:1"; notes.append("square keyword -> 1:1")
    m = re.search(_NUM + r"\s*[- ]?\s*(?:seconds?|secs?|s)\b", p)
    m2 = re.search(_NUM + r"\s*[- ]?\s*(?:minutes?|mins?)\b", p)
    if "target_duration" not in cfg or m or m2:
        pass
    # take the duration that follows an output-ish cue if there are several (e.g. "5-minute video into 30-second reel")
    cands = [(mm.start(), float(mm.group(1))) for mm in re.finditer(_NUM + r"\s*[- ]?\s*(?:seconds?|secs?)\b", p)]
    cands += [(mm.start(), float(mm.group(1)) * 60) for mm in re.finditer(_NUM + r"\s*[- ]?\s*(?:minutes?|mins?)\b", p)]
    if cands:
        cfg["target_duration"] = sorted(cands)[-1][1] if len(cands) > 1 and re.search(r"\b(into|to)\b", p) else sorted(cands)[0][1]
        notes.append(f"duration {cfg['target_duration']}s from text")
    elif "target_duration" not in cfg and "aspect_ratio" in cfg and cfg["aspect_ratio"] == "9:16":
        cfg["target_duration"] = 30.0; notes.append("short-form default 30 s")
    if "youtube short" in p and "target_duration" in cfg:
        cfg["target_duration"] = min(cfg["target_duration"], 60.0)
    if has(r"remove (?:the )?(?:unnecessary |dead |long )?(?:silence|pauses?)", r"cut (?:the )?silence", r"trim silence", r"remove pauses"):
        cfg["remove_silence"] = True
    if has(r"keep (?:the )?silence", r"don.t remove (?:the )?silence", r"no silence removal"):
        cfg["remove_silence"] = False
    if has(r"subtitle", r"caption"):
        cfg["subtitles"] = not has(r"no subtitles?", r"without subtitles?", r"no captions?")
        if has(r"animated"): cfg["subtitle_style"] = "animated"
        elif has(r"karaoke", r"word.by.word", r"highlight"): cfg["subtitle_style"] = "karaoke"
        elif has(r"bold"): cfg["subtitle_style"] = "bold"
    if has(r"smooth transition", r"smooth"): cfg["transition_style"] = "smooth"
    if has(r"\bfade\b"): cfg["transition_style"] = "fade"
    if has(r"hard cuts?", r"no transitions?", r"jump cuts?"): cfg["transition_style"] = "none"
    if has(r"cinematic"):
        cfg["color_preset"] = "cinematic"
        if "transition_style" not in cfg: cfg["transition_style"] = "smooth"
    if has(r"vivid", r"vibrant"): cfg["color_preset"] = "vivid"
    if has(r"black and white", r"b&w", r"monochrome"): cfg["color_preset"] = "bw"
    if has(r"background music", r"add music", r"with music"): cfg["music_enabled"] = True
    if has(r"preserve (?:every |all )?(?:important )?(?:speech|sentence)", r"keep (?:every |all )?(?:important )?(?:speech|sentence)", r"retain (?:the )?(?:important|spoken)"):
        cfg["preserve_speech"] = True
    if has(r"chronolog", r"original order", r"in order", r"original meaning", r"story order"):
        cfg["sequencing"] = "chronological"; notes.append("meaning/order preservation -> chronological sequencing")
    if has(r"\b720p\b"): cfg["quality"] = "720p"
    if has(r"\b1080p?\b", r"1080x1920"): cfg["quality"] = "1080p"
    t = re.search(r"(?:about|on the topic of|focus(?:ing)? on|regarding)\s+([a-z0-9 ,'-]{3,60}?)(?:[.,;]|$| and | with )", p)
    if t: cfg["topic"] = t.group(1).strip(); notes.append(f"topic='{cfg['topic']}'")
    if not notes and not cfg:
        notes.append("no recognised keywords: using defaults")
    return cfg, notes


def _llm(prompt: str) -> dict | None:
    s = get_settings()
    if not s.llm_api_key:
        return None
    import httpx
    schema_hint = {k: v.annotation.__name__ if hasattr(v.annotation, "__name__") else str(v.annotation) for k, v in EditConfig.model_fields.items()}
    sys = ("You convert video-editing requests into a JSON object with ONLY these keys: " + ", ".join(schema_hint) +
           ". Output JSON only. Never include commands or code.")
    try:
        r = httpx.post(s.llm_base_url.rstrip("/") + "/chat/completions", timeout=20,
                       headers={"Authorization": f"Bearer {s.llm_api_key}"},
                       json={"model": s.llm_model, "response_format": {"type": "json_object"}, "temperature": 0,
                             "messages": [{"role": "system", "content": sys}, {"role": "user", "content": prompt[:2000]}]})
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
        return {k: v for k, v in data.items() if k in EditConfig.model_fields} if isinstance(data, dict) else None
    except Exception as e:
        log.warning("LLM interpretation failed (%s); using local parser", type(e).__name__)
        return None


def interpret(prompt: str, overrides: dict | None = None) -> dict:
    """Returns {config, source, notes}. Local parse first; LLM (if configured) may refine; Pydantic always validates."""
    local, notes = parse_local(prompt)
    source, merged = "local-parser", dict(local)
    llm = _llm(prompt)
    if llm:
        merged = {**llm, **local}  # explicit keyword matches win over LLM guesses
        source = "llm+local"
    merged.update({k: v for k, v in (overrides or {}).items() if v is not None})
    try:
        cfg = EditConfig(**merged)
    except ValidationError as e:
        if source == "llm+local":
            cfg = EditConfig(**{**local, **(overrides or {})}); source = "local-parser"; notes.append("LLM output rejected by validation")
        else:
            raise
    return {"config": cfg.model_dump(), "source": source, "notes": notes}
