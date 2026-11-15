"""Regression tests for issues found when testing realistic inputs (single-shot talking head, phone rotation,
containers, smooth transitions on jump cuts, Gujarati subtitles)."""
import subprocess
import pytest
from tests.conftest import GUJARATI_SRT, SRT, make_variant
from app.ai.scene_detector import detect_scenes
from app.core.audio_processor import detect_silence
from app.core.video_metadata import extract_metadata


def _project(client, path, srt=SRT, ctype="video/mp4", name="v.mp4"):
    pid = client.post("/api/projects", json={"project_name": "rw"}).json()["project_id"]
    with open(path, "rb") as f:
        r = client.post(f"/api/upload?project_id={pid}", files={"file": (name, f, ctype)})
    assert r.status_code == 201, r.text
    if srt:
        client.post(f"/api/projects/{pid}/transcript", json={"srt": srt})
    client.post(f"/api/analyze/{pid}")
    assert client.get(f"/api/projects/{pid}").json()["status"] == "analyzed"
    return pid


def test_single_shot_talking_head_is_split_at_pauses(oneshot_video_path):
    sil = detect_silence(oneshot_video_path, 12.0)
    scenes = detect_scenes(oneshot_video_path, 12.0, sil)["scenes"]
    assert len(scenes) >= 3, scenes
    assert all(s["boundary_method"] == "pause" for s in scenes)
    for s in scenes:   # every cut lands inside a silence, never in the middle of speech
        if s["start"] > 0:
            assert any(a - 0.05 <= s["start"] <= b + 0.05 for a, b in sil), s


def test_rotation_metadata_is_applied(rotated_video_path):
    m = extract_metadata(rotated_video_path)
    assert (m["width"], m["height"]) == (720, 1280) and m["rotation"] in (90, -90, 270)


def test_rotated_phone_video_renders_upright_and_full_frame(client, rotated_video_path, tmp_path):
    pid = _project(client, rotated_video_path)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with subtitles"}).json()
    assert p["renderable"]
    j = client.post(f"/api/render/{pid}").json()
    st = client.get(f"/api/render/{j['job_id']}/status").json()
    assert st["status"] == "completed", st
    f = tmp_path / "o.mp4"; f.write_bytes(client.get(st["download_url"]).content)
    # no black letterbox bars: mean luma of top and bottom rows must be well above black
    import cv2
    cap = cv2.VideoCapture(str(f)); cap.set(cv2.CAP_PROP_POS_MSEC, 1500); ok, fr = cap.read(); cap.release()
    assert ok and fr.shape[:2] == (1920, 1080)
    assert fr[:40].mean() > 20 and fr[-40:].mean() > 20


@pytest.mark.parametrize("ext,ctype", [("mov", "video/quicktime"), ("mkv", "video/x-matroska"), ("webm", "video/webm"), ("avi", "video/x-msvideo")])
def test_other_containers_upload_analyze_render(client, tmp_path, ext, ctype):
    f = tmp_path / f"clip.{ext}"; make_variant(f, ext)
    pid = _project(client, f, ctype=ctype, name=f"clip.{ext}")
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with subtitles"}).json()
    assert p["renderable"], p["validation"]
    j = client.post(f"/api/render/{pid}").json()
    assert client.get(f"/api/render/{j['job_id']}/status").json()["status"] == "completed"


def test_smooth_transitions_apply_at_every_boundary_even_on_jump_cuts(client, oneshot_video_path):
    pid = _project(client, oneshot_video_path)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with smooth transitions"}).json()
    assert p["renderable"] and len(p["clips"]) >= 2
    assert all(c["transition_in"]["duration"] > 0 for c in p["clips"][1:]), "explicit 'smooth' request must not degrade to hard cuts"
    assert {c["transition_in"]["type"] for c in p["clips"][1:]} <= {"dissolve", "fade", "fadeblack"}
    fired = {r["rule_id"] for r in p["algorithms"]["expert"]["rules"] if r["fired"]}
    assert "R6b" in fired
    p2 = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with hard cuts"}).json()
    assert all(c["transition_in"]["duration"] == 0 for c in p2["clips"])


def test_gujarati_font_is_bundled_and_gujarati_subtitles_render(client, oneshot_video_path):
    from app.rendering.subtitle_renderer import resolve_font
    fam, warn = resolve_font("નમસ્તે")
    assert warn is None and "Gujarati" in fam or fam in ("FreeSerif",) or warn is None
    pid = _project(client, oneshot_video_path, srt=GUJARATI_SRT)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with animated subtitles"}).json()
    assert p["renderable"] and p["subtitles"]["cue_count"] > 0 and not any("Gujarati" in w for w in p["warnings"])
    assert any(any("\u0a80" <= ch <= "\u0aff" for ch in c["text"]) for c in p["subtitle_cues"])
    j = client.post(f"/api/render/{pid}").json()
    assert client.get(f"/api/render/{j['job_id']}/status").json()["status"] == "completed"


def test_missing_gujarati_font_warning_reaches_the_plan(client, oneshot_video_path, monkeypatch):
    import app.rendering.subtitle_renderer as sr
    monkeypatch.setattr(sr, "resolve_font", lambda text: ("Noto Sans", "Gujarati text detected but no Gujarati-capable font was found"))
    pid = _project(client, oneshot_video_path, srt=GUJARATI_SRT)
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with subtitles"}).json()
    assert any("Gujarati" in w for w in p["warnings"])


def test_fonts_are_passed_relative_so_windows_paths_cannot_break_the_filter(oneshot_video_path, tmp_path):
    from app.rendering.ffmpeg_engine import build_graph
    plan = {"clips": [{"scene_id": 0, "duration": 2.0, "segments": [{"start": 0.0, "end": 2.0}], "focus_x": 0.5, "transition_in": {"duration": 0, "type": "none"}}],
            "source": {"width": 640, "height": 360, "has_audio": True}, "config": {"color_preset": "none", "normalize_audio": True}, "output": {"fps": 30}}
    g, total, segs = build_graph(plan, 1080, 1920, True, "subs.ass", False, "fonts")
    assert "ass=subs.ass:fontsdir=fonts" in g and "\\" not in g.split("ass=")[1].split("[")[0]
