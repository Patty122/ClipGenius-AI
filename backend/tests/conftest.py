import os
import subprocess
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="clipgenius_test_")
os.environ["CLIPGENIUS_DATA_DIR"] = _TMP
os.environ["CLIPGENIUS_SYNC_JOBS"] = "1"
os.environ["CLIPGENIUS_MAX_UPLOAD_MB"] = "50"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def make_test_video(path: Path, with_audio: bool = True) -> None:
    """12 s, 640x360: red (0-4) | testsrc2 (4-8) | blue (8-12). Audio tones 0-3, 4.5-7.5, 9-12; silence elsewhere."""
    v = ("color=c=red:s=640x360:r=25:d=4[v0];testsrc2=s=640x360:r=25:d=4[v1];color=c=0x2060ff:s=640x360:r=25:d=4[v2];"
         "[v0][v1][v2]concat=n=3:v=1:a=0[v]")
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "nullsrc=s=16x16:d=0.1"]
    graph = v.replace("[v]", "[vout]")
    a = ("sine=f=440:d=3,aformat=sample_rates=44100:channel_layouts=mono[a0];anullsrc=r=44100:cl=mono,atrim=0:1.5[a1];"
         "sine=f=600:d=3,aformat=sample_rates=44100:channel_layouts=mono[a2];anullsrc=r=44100:cl=mono,atrim=0:1.5[a3];"
         "sine=f=330:d=3,aformat=sample_rates=44100:channel_layouts=mono[a4];[a0][a1][a2][a3][a4]concat=n=5:v=0:a=1[aout]")
    graph = graph + (";" + a if with_audio else "")
    cmd += ["-filter_complex", graph, "-map", "[vout]"] + (["-map", "[aout]"] if with_audio else [])
    cmd += ["-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if with_audio else []) + [str(path)]
    subprocess.run(cmd, check=True)


@pytest.fixture(scope="session")
def video_path() -> Path:
    p = Path(_TMP) / "sample.mp4"
    make_test_video(p)
    return p


@pytest.fixture(scope="session")
def silent_video_path() -> Path:
    p = Path(_TMP) / "noaudio.mp4"
    make_test_video(p, with_audio=False)
    return p


@pytest.fixture(autouse=True)
def no_network_whisper(monkeypatch):
    """Whisper model weights are a third-party download; tests must not depend on the network."""
    from app.services import analysis_service
    monkeypatch.setattr(analysis_service, "transcribe_whisper",
                        lambda path, language=None: {"source": "whisper:test-stub", "status": "unavailable", "language": None, "segments": [],
                                                     "message": "model not available in test environment"})


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


SRT = """1
00:00:00,300 --> 00:00:02,800
welcome to this short demo about video editing

2
00:00:04,600 --> 00:00:07,400
artificial intelligence can choose the important scenes

3
00:00:09,100 --> 00:00:11,800
and render a final edited reel automatically
"""


def make_variant(path: Path, kind: str) -> None:
    """Realistic-input variants: one-shot talking head, rotated phone video, other containers."""
    aud = ("sine=f=440:d=3,aformat=sample_rates=44100:channel_layouts=mono[a0];anullsrc=r=44100:cl=mono,atrim=0:1.5[a1];"
           "sine=f=600:d=3,aformat=sample_rates=44100:channel_layouts=mono[a2];anullsrc=r=44100:cl=mono,atrim=0:1.5[a3];"
           "sine=f=330:d=3,aformat=sample_rates=44100:channel_layouts=mono[a4];[a0][a1][a2][a3][a4]concat=n=5:v=0:a=1[aout]")
    size = {"rotated": "1280x720"}.get(kind, "640x360")
    codec = {"webm": ["-c:v", "libvpx-vp9", "-c:a", "libopus"], "avi": ["-c:v", "mpeg4", "-c:a", "libmp3lame"]}.get(kind, ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"])
    tmp = path.with_suffix(".tmp" + path.suffix)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={size}:r=25:d=12", "-filter_complex", aud, "-map", "0:v", "-map", "[aout]",
                    "-t", "12", *codec, str(tmp if kind == "rotated" else path)], check=True)
    if kind == "rotated":   # phone-style: stored landscape + display-rotation metadata
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", "90", "-i", str(tmp), "-c", "copy", str(path)], check=True)
        tmp.unlink()


@pytest.fixture(scope="session")
def oneshot_video_path() -> Path:
    p = Path(_TMP) / "oneshot.mp4"; make_variant(p, "oneshot"); return p


@pytest.fixture(scope="session")
def rotated_video_path() -> Path:
    p = Path(_TMP) / "rotated.mp4"; make_variant(p, "rotated"); return p


GUJARATI_SRT = """1
00:00:00,300 --> 00:00:02,800
નમસ્તે, આ એક ટૂંકો ડેમો છે hello

2
00:00:04,600 --> 00:00:07,400
આજે આપણે જોઈશું કે AI વિડિયો કેવી રીતે એડિટ કરે છે

3
00:00:09,100 --> 00:00:11,800
thank you ધન્યવાદ
"""
