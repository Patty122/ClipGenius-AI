"""Restricted subprocess execution. Only ffmpeg/ffprobe may be launched, never through a shell."""
from __future__ import annotations
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from ..config import get_settings
from ..utils.logger import get_logger

log = get_logger("process")


class MediaError(RuntimeError):
    """Raised when an FFmpeg/FFprobe invocation fails."""


def _check(cmd: list[str]) -> None:
    s = get_settings()
    if not cmd or Path(cmd[0]).name not in {Path(s.ffmpeg_bin).name, Path(s.ffprobe_bin).name}:
        raise MediaError("Refusing to execute a non-media binary")
    if any(not isinstance(c, str) for c in cmd):
        raise MediaError("Command arguments must be strings")


def run_media(cmd: list[str], timeout: int, binary_out: bool = False) -> subprocess.CompletedProcess:
    _check(cmd)
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, text=not binary_out, shell=False,
                              errors=None if binary_out else "replace")
    except subprocess.TimeoutExpired as e:
        raise MediaError(f"{Path(cmd[0]).name} timed out after {timeout}s") from e


def run_ffmpeg_progress(args: list[str], total_seconds: float, on_progress: Optional[Callable[[float], None]] = None,
                        timeout: Optional[int] = None, cwd: Optional[Path] = None) -> str:
    """Run ffmpeg with real `-progress` parsing. `on_progress` receives 0..1 measured from encoded time."""
    s = get_settings()
    timeout = timeout or s.ffmpeg_timeout
    cmd = [s.ffmpeg_bin, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    _check(cmd)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                            cwd=str(cwd) if cwd else None, shell=False)
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    err_buf: list[str] = []
    t_err = threading.Thread(target=lambda: err_buf.append(proc.stderr.read()), daemon=True)
    t_err.start()
    started = time.time()
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    val = int(line.split("=")[1])
                except ValueError:
                    continue
                if on_progress and total_seconds > 0:
                    on_progress(min(0.999, (val / 1_000_000) / total_seconds))
        proc.wait()
    finally:
        timer.cancel()
        t_err.join(timeout=2)
    stderr = "".join(err_buf)
    if proc.returncode != 0:
        tail = "\n".join(stderr.strip().splitlines()[-12:])
        raise MediaError(f"ffmpeg failed (code {proc.returncode}) after {time.time()-started:.1f}s:\n{tail}")
    if on_progress:
        on_progress(1.0)
    return stderr
