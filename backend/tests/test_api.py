import json
import subprocess
from pathlib import Path
import pytest
from tests.conftest import SRT

PROMPT = "Create a 6-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions."


def upload(client, path, name="clip.mp4", ctype="video/mp4"):
    pid = client.post("/api/projects", json={"project_name": "t"}).json()["project_id"]
    with open(path, "rb") as f:
        r = client.post(f"/api/upload?project_id={pid}", files={"file": (name, f, ctype)})
    return pid, r


@pytest.fixture(scope="module")
def analyzed(client, video_path):
    pid, r = upload(client, video_path)
    assert r.status_code == 201
    assert client.post(f"/api/projects/{pid}/transcript", json={"srt": SRT}).json()["segments"] == 3
    assert client.post(f"/api/analyze/{pid}").status_code == 202
    return pid


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["ffmpeg"] and h["ffprobe"]


def test_project_crud_and_validation(client):
    r = client.post("/api/projects", json={"project_name": "My project"})
    assert r.status_code == 201
    pid = r.json()["project_id"]
    assert client.get(f"/api/projects/{pid}").json()["status"] == "created"
    assert pid in [p["project_id"] for p in client.get("/api/projects").json()]
    assert client.post("/api/projects", json={"project_name": ""}).status_code == 422
    assert client.get("/api/projects/nope").status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_responses_never_expose_filesystem_paths(client, analyzed):
    blob = json.dumps(client.get(f"/api/projects/{analyzed}").json()) + json.dumps(client.get(f"/api/analysis/{analyzed}").json())
    assert "/tmp" not in blob and "clipgenius_test" not in blob and "original_video_path" not in blob


def test_upload_rejects_bad_extension_mime_and_garbage(client, tmp_path):
    pid = client.post("/api/projects", json={"project_name": "x"}).json()["project_id"]
    assert client.post(f"/api/upload?project_id={pid}", files={"file": ("virus.exe", b"MZ", "application/octet-stream")}).status_code == 400
    assert client.post(f"/api/upload?project_id={pid}", files={"file": ("a.mp4", b"hello", "text/html")}).status_code == 400
    r = client.post(f"/api/upload?project_id={pid}", files={"file": ("a.mp4", b"this is not video" * 200, "video/mp4")})
    assert r.status_code == 400 and "Not a readable video" in r.json()["detail"]
    assert client.post(f"/api/upload?project_id={pid}", files={"file": ("a.mp4", b"", "video/mp4")}).status_code == 400
    assert client.post("/api/upload?project_id=missing", files={"file": ("a.mp4", b"x", "video/mp4")}).status_code == 404


def test_upload_size_limit_and_path_traversal(client, video_path, monkeypatch):
    from app.config import get_settings
    pid, r = upload(client, video_path, name="../../evil name;.mp4")
    assert r.status_code == 201 and r.json()["original_filename"] == "evil_name_.mp4"
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    pid2 = client.post("/api/projects", json={"project_name": "big"}).json()["project_id"]
    r = client.post(f"/api/upload?project_id={pid2}", files={"file": ("a.mp4", video_path.read_bytes(), "video/mp4")})
    assert r.status_code == 400 and "limit" in r.json()["detail"]


def test_analysis_results_are_real(client, analyzed):
    a = client.get(f"/api/analysis/{analyzed}").json()
    s = a["summary"]
    assert abs(s["duration"] - 12.0) < 0.2 and s["scene_count"] == 3
    assert abs(s["silence_duration"] - 3.0) < 0.4 and s["speech_duration"] > 7
    assert [round(x["start"]) for x in a["scenes"]] == [0, 4, 8]
    sc = a["scenes"]
    assert all(0 <= x["importance"] <= 100 and x["thumbnail"] for x in sc)
    assert "machine" not in json.dumps(a)   # nothing fabricated
    assert any("artificial intelligence" in x["transcript"] for x in sc)
    assert a["transcript"]["status"] == "ok" and a["transcript"]["source"] == "imported"
    assert client.get(f"/api/projects/{analyzed}/thumbnails/0").headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/projects/{analyzed}/video").status_code == 200


def test_analysis_without_transcript_reports_missing_features(client, video_path):
    pid, _ = upload(client, video_path)
    client.post(f"/api/analyze/{pid}")
    a = client.get(f"/api/analysis/{pid}").json()
    assert a["transcript"]["status"] == "unavailable" and a["transcript"]["segments"] == []
    assert all("speech_relevance" in x["score_detail"]["missing"] for x in a["scenes"])


def test_plan_requires_analysis(client):
    pid = client.post("/api/projects", json={"project_name": "x"}).json()["project_id"]
    assert client.post(f"/api/edit/{pid}/plan", json={"prompt": PROMPT}).status_code == 409
    assert client.post(f"/api/render/{pid}").status_code == 409


@pytest.fixture(scope="module")
def planned(client, analyzed):
    r = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": PROMPT})
    assert r.status_code == 201, r.text
    return r.json()


def test_plan_is_valid_explainable_and_meets_target(planned):
    p = planned
    assert p["validation_status"] == "valid" and p["renderable"] and p["validation"]["violations"] == []
    assert p["config"]["aspect_ratio"] == "9:16" and p["output"]["width"] == 1080 and p["output"]["height"] == 1920
    assert abs(p["output"]["duration"] - 6.0) <= p["config"]["duration_tolerance"] + 1e-6
    ids = [c["scene_id"] for c in p["clips"]]
    assert len(ids) == len(set(ids)) >= 2
    for c in p["clips"]:
        assert all(0 <= s["start"] < s["end"] <= 12.0 + 1e-3 for s in c["segments"])
        assert c["rationale"]
    ops = {o["op"] for o in p["operations"]}
    assert {"select_scenes", "sequence", "trim_silence", "reframe", "subtitles", "transitions"} <= ops
    assert p["subtitles"]["cue_count"] > 0 and all(0 <= c["start"] < c["end"] <= p["output"]["duration"] + 0.05 for c in p["subtitle_cues"])


def test_plan_trims_silence_without_cutting_speech(planned):
    segs = [s for c in planned["clips"] for s in c["segments"]]
    for s in segs:   # silence is 3.0-4.5 and 7.5-9.0: kept segments may include <=0.15 s padding into it, never deeper
        assert not (s["start"] < 3.9 and s["end"] > 3.45 and s["start"] > 3.0 and s["end"] < 4.4), s
    covered = sum(s["end"] - s["start"] for s in segs)
    assert covered <= 6.0 + 1.5


def test_algorithm_endpoints(client, analyzed, planned):
    a = client.get(f"/api/algorithms/{analyzed}/astar").json()
    assert a["optimal"] and a["algorithm"] in ("astar", "trivial") and a["expanded"] >= 1 and a["cost"] <= a["chronological_cost"] + 1e-9
    assert a["trace"] and sorted(a["order_scene_ids"]) == sorted(a["candidate_ids"])
    c = client.get(f"/api/algorithms/{analyzed}/csp").json()
    assert c["status"] == "satisfied" and c["nodes"] > 0 and c["validation"]["status"] == "valid" and len(c["constraints"]) >= 6
    e = client.get(f"/api/algorithms/{analyzed}/expert-system").json()
    fired = {r["rule_id"] for r in e["rules"] if r["fired"]}
    assert {"R4", "R5", "R9", "R10"} <= fired and e["backward"]["proved"]
    assert all({"rule_id", "condition", "facts_evaluated", "fired", "recommendation", "explanation"} <= set(r) for r in e["rules"])
    d = client.get(f"/api/agents/{analyzed}/decisions").json()
    phases = {x["phase"] for x in d}
    assert {"perceive", "understand", "decide", "validate", "plan"} <= phases
    assert {"Video Perception Agent", "Speech Analysis Agent", "Scene Evaluation Agent", "Editing Planner Agent", "Constraint Validation Agent"} <= {x["agent_name"] for x in d}


def test_validate_endpoint(client, analyzed, planned):
    assert client.post(f"/api/edit/{analyzed}/validate").json()["status"] == "valid"
    assert client.get(f"/api/edit/{analyzed}/plan").json()["plan_id"] == planned["plan_id"]
    srt = client.get(f"/api/edit/{analyzed}/subtitles.srt")
    assert srt.status_code == 200 and "-->" in srt.text


def test_infeasible_plan_is_explained_and_never_rendered(client, analyzed):
    r = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": "Create a 100 second vertical reel"})
    p = r.json()
    assert r.status_code == 201 and p["validation_status"] == "infeasible" and not p["renderable"]
    assert p["validation"]["suggestions"] and p["algorithms"]["csp"]["status"] == "unsatisfiable"
    rr = client.post(f"/api/render/{analyzed}")
    assert rr.status_code == 409 and "failed validation" in rr.json()["detail"]["message"]
    assert client.post(f"/api/edit/{analyzed}/preview").status_code == 409


def test_invalid_overrides_rejected(client, analyzed):
    r = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": PROMPT, "overrides": {"resolution": "999x999"}})
    assert r.status_code == 422
    assert client.post(f"/api/edit/{analyzed}/plan", json={"prompt": "x"}).status_code == 422


def test_full_render_preview_download_and_report(client, analyzed, tmp_path):
    p = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": PROMPT}).json()
    assert p["renderable"]
    pv = client.post(f"/api/edit/{analyzed}/preview").json()
    st = client.get(f"/api/render/{pv['job_id']}/status").json()
    assert st["status"] == "completed", st
    job = client.post(f"/api/render/{analyzed}").json()
    st = client.get(f"/api/render/{job['job_id']}/status").json()
    assert st["status"] == "completed" and st["progress"] == 1.0, st
    out = client.get(st["download_url"])
    assert out.status_code == 200 and out.headers["content-type"] == "video/mp4"
    f = tmp_path / "out.mp4"; f.write_bytes(out.content)
    pr = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(f)], capture_output=True, text=True).stdout)
    v = next(s for s in pr["streams"] if s["codec_type"] == "video"); a = next(s for s in pr["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"]) == (1080, 1920) and v["codec_name"] == "h264" and a["codec_name"] == "aac"
    assert abs(float(pr["format"]["duration"]) - p["output"]["duration"]) < 0.6
    assert subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-f", "null", "-"], capture_output=True, text=True).stderr.strip() == ""
    rep = client.get(f"/api/report/{analyzed}").json()
    assert rep["output_verification"]["ok"] and all(c["ok"] for c in rep["output_verification"]["checks"])
    assert rep["scenes_detected"] == 3 and rep["astar"]["nodes_expanded"] >= 1 and rep["csp"]["independent_validation"] == "valid"
    assert abs(rep["original_duration"] - 12.0) < 0.2 and abs(rep["final_duration_measured"] - rep["final_duration_planned"]) < 0.6
    assert len(client.get(f"/api/projects/{analyzed}/jobs").json()) >= 2
    assert client.get("/api/render/missing/download").status_code == 404


def test_original_video_is_never_modified(client, analyzed, video_path):
    import hashlib
    from app.config import get_settings
    from app.models import Project
    from app.database.connection import session_scope
    with session_scope() as db:
        rel = db.get(Project, analyzed).original_video_path
    assert hashlib.md5((get_settings().uploads_dir / rel).read_bytes()).hexdigest() == hashlib.md5(video_path.read_bytes()).hexdigest()


def test_export_option_change_replans_and_validates(client, analyzed):
    assert client.post(f"/api/edit/{analyzed}/plan", json={"prompt": PROMPT}).json()["renderable"]
    r = client.post(f"/api/render/{analyzed}", json={"export": {"aspect_ratio": "1:1", "quality": "720p"}})
    assert r.status_code == 202
    st = client.get(f"/api/render/{r.json()['job_id']}/status").json()
    assert st["status"] == "completed" and st["report"]["output_verification"]["ok"]
    assert client.get(f"/api/edit/{analyzed}/plan").json()["output"]["width"] == 720
    assert client.get(f"/api/edit/{analyzed}/plan").json()["output"]["height"] == 720


def test_render_without_subtitles_and_landscape(client, analyzed):
    p = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": "Create a 6 second landscape video with no subtitles and hard cuts"}).json()
    assert p["renderable"] and p["subtitles"]["cue_count"] == 0 and p["config"]["aspect_ratio"] == "16:9"
    assert all(c["transition_in"]["duration"] == 0 for c in p["clips"])
    j = client.post(f"/api/render/{analyzed}").json()
    assert client.get(f"/api/render/{j['job_id']}/status").json()["status"] == "completed"


def test_video_without_audio_renders(client, silent_video_path):
    pid, _ = upload(client, silent_video_path)
    client.post(f"/api/analyze/{pid}")
    p = client.post(f"/api/edit/{pid}/plan", json={"prompt": "Create a 6 second vertical reel with subtitles"}).json()
    assert p["renderable"] and any("no transcript" in w.lower() for w in p["warnings"])
    j = client.post(f"/api/render/{pid}").json()
    st = client.get(f"/api/render/{j['job_id']}/status").json()
    assert st["status"] == "completed", st
    assert st["report"]["output_verification"]["ok"]


def test_astar_ordering_can_be_toggled_to_chronological(client, analyzed):
    p = client.post(f"/api/edit/{analyzed}/plan", json={"prompt": "Create a 8 second vertical reel and keep the original order"}).json()
    ids = [c["scene_id"] for c in p["clips"]]
    assert ids == sorted(ids) and p["algorithms"]["astar"]["applied"] == "chronological"


def test_stale_job_cleanup_marks_interrupted(client):
    from app.database.connection import session_scope
    from app.models import Project
    with session_scope() as db:
        db.add(Project(project_id="stale1", project_name="s", status="analyzing"))
    from app.main import app, lifespan
    import asyncio
    async def go():
        async with lifespan(app):
            pass
    asyncio.run(go())
    assert client.get("/api/projects/stale1").json()["status"] == "error"
    assert "interrupted" in client.get("/api/projects/stale1").json()["error_message"]
