"""Application settings (environment-driven; no secrets are ever sent to the frontend)."""
from __future__ import annotations
import os
import shutil
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_prefix="CLIPGENIUS_", extra="ignore")

    data_dir: Path = BACKEND_DIR
    max_upload_mb: int = 500
    max_video_seconds: int = 3600
    allowed_extensions: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v")
    allowed_audio_extensions: tuple[str, ...] = (".mp3", ".wav", ".m4a", ".aac", ".ogg")

    whisper_model: str = "tiny"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    silence_db: float = -35.0
    silence_min_seconds: float = 0.5
    silence_pad_seconds: float = 0.15
    scene_threshold: float = 27.0
    min_scene_seconds: float = 1.0
    max_scene_seconds: float = 8.0

    ffmpeg_timeout: int = 1800
    ffprobe_timeout: int = 60
    sync_jobs: bool = False  # run jobs inline (used by tests)

    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    @property
    def uploads_dir(self) -> Path: return self.data_dir / "uploads"
    @property
    def outputs_dir(self) -> Path: return self.data_dir / "outputs"
    @property
    def temp_dir(self) -> Path: return self.data_dir / "temp"
    @property
    def db_url(self) -> str: return f"sqlite:///{self.data_dir / 'clipgenius.db'}"
    @property
    def fonts_dir(self) -> Path: return BACKEND_DIR / "assets" / "fonts"
    @property
    def ffmpeg_bin(self) -> str: return shutil.which("ffmpeg") or "ffmpeg"
    @property
    def ffprobe_bin(self) -> str: return shutil.which("ffprobe") or "ffprobe"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.outputs_dir, self.temp_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if not s.llm_api_key and os.environ.get("OPENAI_API_KEY"):
        s.llm_api_key = os.environ["OPENAI_API_KEY"]
    s.ensure_dirs()
    return s
