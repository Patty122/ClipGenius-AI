"""Knowledge base: IF-THEN rules over a working memory of facts (shared by forward & backward chaining)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

OPS = {
    "==": lambda a, b: a == b, "!=": lambda a, b: a != b, ">": lambda a, b: a is not None and b is not None and a > b,
    ">=": lambda a, b: a is not None and b is not None and a >= b, "<": lambda a, b: a is not None and b is not None and a < b,
    "<=": lambda a, b: a is not None and b is not None and a <= b, "truthy": lambda a, b: bool(a), "falsy": lambda a, b: not a,
}


@dataclass(frozen=True)
class Ref:
    """A reference to another fact, so thresholds (e.g. silence_threshold) stay configurable."""
    fact: str


@dataclass
class Cond:
    fact: str
    op: str = "truthy"
    value: Any = None

    def resolve(self, wm: dict):
        return wm.get(self.value.fact) if isinstance(self.value, Ref) else self.value

    def holds(self, wm: dict) -> bool:
        return self.fact in wm and OPS[self.op](wm[self.fact], self.resolve(wm)) if self.op not in ("falsy",) else not wm.get(self.fact)

    def text(self) -> str:
        if self.op == "truthy":
            return self.fact
        if self.op == "falsy":
            return f"NOT {self.fact}"
        v = f"<{self.value.fact}>" if isinstance(self.value, Ref) else repr(self.value)
        return f"{self.fact} {self.op} {v}"


@dataclass
class Rule:
    id: str
    name: str
    premises: list[Cond]
    conclusion: tuple[str, Any]        # fact asserted when the rule fires
    recommendation: str
    explanation: str
    scope: str = "global"              # global | scene | transition

    def condition_text(self) -> str:
        return "IF " + " AND ".join(c.text() for c in self.premises) + f" THEN {self.conclusion[0]} = {self.conclusion[1]}"


@dataclass
class FiringRecord:
    rule_id: str
    name: str
    scope: str
    target: str
    condition: str
    facts_evaluated: dict
    fired: bool
    recommendation: str
    explanation: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def default_rules() -> list[Rule]:
    return [
        Rule("R1", "Trim silent intervals", [Cond("remove_silence"), Cond("silence_duration", ">", Ref("silence_threshold"))],
             ("trim_silence", True), "Trim the silent interval(s), keeping speech padding.",
             "Silence longer than the configured threshold was detected and silence removal is enabled.", "scene"),
        Rule("R2", "Retain high-relevance speech", [Cond("speech_relevance_norm", ">=", Ref("high_relevance"))],
             ("priority_retain", True), "Prioritise retaining this scene.", "Speech relevance is high, so the scene carries core content.", "scene"),
        Rule("R3", "Drop short, low-value scene", [Cond("scene_duration", "<", Ref("min_scene_len")), Cond("importance", "<", Ref("low_importance"))],
             ("exclude_candidate", True), "Exclude this scene from the candidate set.",
             "Scene is shorter than the minimum length and its importance is low.", "scene"),
        Rule("R4", "Vertical reframing", [Cond("aspect_ratio", "==", "9:16")],
             ("reframe_scheduled", True), "Apply vertical (9:16) reframing.", "Target aspect ratio is 9:16.", "global"),
        Rule("R5", "Generate subtitles from transcript", [Cond("subtitles_enabled"), Cond("has_transcript")],
             ("subtitles_scheduled", True), "Generate subtitles from transcript timestamps.", "Subtitles requested and transcript available.", "global"),
        Rule("R5b", "Subtitles requested without transcript", [Cond("subtitles_enabled"), Cond("has_transcript", "falsy")],
             ("subtitles_blocked", True), "Subtitles cannot be generated: no transcript. Import an SRT or enable Whisper.",
             "Subtitles requested but no transcript is available (Whisper unavailable and none imported).", "global"),
        Rule("R6", "Transition at poor continuity", [Cond("visual_discontinuity", ">", Ref("continuity_threshold")), Cond("transitions_enabled")],
             ("transition_needed", True), "Insert a transition between these scenes.", "Consecutive scenes differ strongly in appearance.", "transition"),
        Rule("R6b", "Soft dissolve for jump cuts", [Cond("visual_discontinuity", "<=", Ref("continuity_threshold")), Cond("transitions_enabled")],
             ("transition_soft", True), "Use a gentle dissolve to smooth this jump cut.",
             "Scenes are visually continuous (typical for talking heads after silence removal), so a soft dissolve hides the cut.", "transition"),
        Rule("R7", "Mix background music with ducking", [Cond("music_enabled")],
             ("music_ducking", True), "Mix music under speech with sidechain ducking.", "Music enabled; speech intelligibility must be preserved.", "global"),
        Rule("R8", "Focus-aware crop", [Cond("reframe_scheduled"), Cond("source_wider_than_target")],
             ("focus_crop", True), "Crop around the detected motion focus instead of the frame centre.",
             "Vertical reframing is scheduled and the source is wider than the target.", "global"),
        Rule("R9", "Short-form profile", [Cond("reframe_scheduled"), Cond("target_duration", "<=", 60)],
             ("short_form_profile", True), "Treat as short-form content (fast pacing, burned-in captions).",
             "Vertical output of 60 s or less matches short-form platform conventions.", "global"),
        Rule("R10", "Loudness normalisation", [Cond("normalize_audio")],
             ("loudnorm", True), "Apply EBU R128 loudness normalisation.", "Audio normalisation enabled.", "global"),
        # derived rules used by backward chaining
        Rule("G1", "Vertical reel ready", [Cond("aspect_ratio", "==", "9:16"), Cond("reframe_scheduled"), Cond("resolution_vertical"),
                                            Cond("duration_ok_for_short_form")],
             ("vertical_reel_ready", True), "All requirements for a vertical reel are satisfied.",
             "9:16 aspect, reframing scheduled, vertical resolution and short-form duration.", "global"),
        Rule("G2", "Vertical resolution", [Cond("out_height", ">", Ref("out_width"))],
             ("resolution_vertical", True), "Output is portrait.", "Height exceeds width.", "global"),
        Rule("G3", "Duration fits short-form", [Cond("target_duration", "<=", 90)],
             ("duration_ok_for_short_form", True), "Duration fits Reels/Shorts limits.", "Target duration is <= 90 s.", "global"),
    ]
