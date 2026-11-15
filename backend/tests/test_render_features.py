import subprocess
from pathlib import Path
import pytest
from tests.conftest import SRT


def _project(client, video_path, with_srt=True):
    pid = client.post("/api/projects", json={"project_name": "feat"}).json()["project_id"]
    with open(video_path, "rb") as f:
        client.post(f"/api/upload?project_id={pid}", files={"file": ("a.mp4", f, "video/mp4")})
    if with_srt:
        client.post(f"/api/projects/{pid}/transcript", json={"srt": SRT})
    client.post(f"/api/analyze/{pid}")
    return pid


def _render(client, pid, prompt, overrides=None):
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": prompt, "overrides": overrides}).json()
    assert p["renderable"], p["validation"]
    j = client.post(f"/api/render/{pid}").json()
    st = client.get(f"/api/render/{j['job_id']}/status").json()
    assert st["status"] == "completed", st
    return p, st


@pytest.mark.parametrize("style", ["classic", "bold", "karaoke", "animated"])
def test_every_subtitle_style_renders_and_verifies(client, video_path, style):
    pid = _project(client, video_path)
    p, st = _render(client, pid, "Create a 6 second vertical reel with subtitles", {"subtitle_style": style})
    assert p["config"]["subtitle_style"] == style and st["report"]["output_verification"]["ok"]


def test_color_presets_and_square_and_720p(client, video_path):
    pid = _project(client, video_path)
    for preset in ("cinematic", "vivid", "bw"):
        p, st = _render(client, pid, f"Create a 6 second square video {preset}")
        assert p["config"]["aspect_ratio"] == "1:1" and p["output"]["width"] == 1080 and st["report"]["output_verification"]["ok"]
    p, st = _render(client, pid, "Create a 6 second landscape video 720p")
    assert (p["output"]["width"], p["output"]["height"]) == (1280, 720) and st["report"]["output_verification"]["ok"]


def test_music_is_mixed_with_ducking(client, video_path, tmp_path):
    pid = _project(client, video_path)
    mp3 = tmp_path / "bed.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=3", str(mp3)], check=True)
    with open(mp3, "rb") as f:
        assert client.post(f"/api/projects/{pid}/music", files={"file": ("bed.wav", f, "audio/wav")}).status_code == 201
    p, st = _render(client, pid, "Create a 6 second vertical reel with background music")
    assert p["config"]["music_enabled"] and any(o["op"] == "music" for o in p["operations"])
    assert st["report"]["output_verification"]["ok"]


def test_music_requested_without_file_warns(client, video_path):
    pid = _project(client, video_path)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with background music"}).json()
    assert any("no music file" in w for w in p["warnings"]) and not any(o["op"] == "music" for o in p["operations"])


def test_silence_stats_are_counted_for_used_scenes(client, video_path):
    pid = _project(client, video_path)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel remove silence"}).json()
    assert p["stats"]["silence_intervals_removed"] >= 1 and p["stats"]["silence_seconds_removed"] > 0


def test_keeping_silence_changes_the_plan(client, video_path):
    pid = _project(client, video_path)
    a = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 10 second vertical reel"}).json()
    b = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 10 second vertical reel", "overrides": {"remove_silence": False}}).json()
    assert not any(o["op"] == "trim_silence" for o in b["operations"]) and any(o["op"] == "trim_silence" for o in a["operations"])


def test_low_target_with_large_min_scene_is_explained(client, video_path):
    pid = _project(client, video_path)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 3 second vertical reel", "overrides": {"min_scene_len": 4.0}}).json()
    assert p["validation_status"] in ("infeasible", "valid")
    if p["validation_status"] == "infeasible":
        assert p["validation"]["suggestions"]
