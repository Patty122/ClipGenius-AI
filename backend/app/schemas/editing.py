"""Validated editing configuration (the contract between the prompt interpreter and the planner)."""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from ..algorithms.csp import ASPECTS

AspectT = Literal["9:16", "16:9", "1:1"]


class EditConfig(BaseModel):
    target_duration: float = Field(30.0, ge=3, le=600)
    duration_tolerance: Optional[float] = Field(None, ge=0.25, le=30)
    aspect_ratio: AspectT = "9:16"
    resolution: Optional[str] = None              # "1080x1920"; derived from aspect + quality when absent
    quality: Literal["720p", "1080p"] = "1080p"
    remove_silence: bool = True
    preserve_speech: bool = True
    subtitles: bool = True
    subtitle_style: Literal["classic", "bold", "animated", "karaoke"] = "animated"
    subtitle_size: int = Field(60, ge=20, le=140)
    subtitle_color: str = "#FFFFFF"
    subtitle_position: Optional[Literal["top", "center", "lower", "bottom"]] = None
    transition_style: Literal["none", "smooth", "fade", "cut"] = "smooth"
    music_enabled: bool = False
    normalize_audio: bool = True
    color_preset: Literal["none", "cinematic", "vivid", "bw"] = "none"
    sequencing: Literal["astar", "chronological"] = "astar"
    topic: Optional[str] = Field(None, max_length=200)
    min_scene_len: float = Field(2.0, ge=0.5, le=30)
    max_candidates: int = Field(9, ge=2, le=40)
    output_format: Literal["mp4"] = "mp4"

    @field_validator("subtitle_color")
    @classmethod
    def _color(cls, v: str) -> str:
        import re
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", v):
            raise ValueError("subtitle_color must be #RRGGBB")
        return v.upper()

    @model_validator(mode="after")
    def _derive(self):
        if self.duration_tolerance is None:
            self.duration_tolerance = round(max(1.0, 0.03 * self.target_duration), 2)
        profs = ASPECTS[self.aspect_ratio]
        if self.resolution:
            try:
                w, h = map(int, self.resolution.lower().split("x"))
            except Exception:
                raise ValueError("resolution must look like 1080x1920")
            if (w, h) not in profs:
                raise ValueError(f"{self.resolution} is not a supported profile for {self.aspect_ratio}: {profs}")
        else:
            w, h = profs[0] if self.quality == "1080p" else profs[1]
            self.resolution = f"{w}x{h}"
        return self


class ExportOptions(BaseModel):
    quality: Optional[Literal["720p", "1080p"]] = None
    aspect_ratio: Optional[AspectT] = None
    subtitles: Optional[bool] = None
    music_enabled: Optional[bool] = None
    normalize_audio: Optional[bool] = None
    burn_subtitles: bool = True
