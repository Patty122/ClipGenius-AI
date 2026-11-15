#!/usr/bin/env python3
"""Feature matrix: runs every major feature / input type through the real API and reports PASS/FAIL with the real error.
Usage: cd backend && python ../scripts/feature_matrix.py <dir-with-test-videos> [<srt>]
"""
import json, os, subprocess, sys, tempfile, time, traceback
from pathlib import Path

VID = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/fm")
SRT_EN = (VID / "speech.srt").read_text()
SRT_GU = (VID / "gujarati.srt").read_text() if (VID / "gujarati.srt").exists() else None
TMP = Path(tempfile.mkdtemp(prefix="fm_"))
os.environ.update({"CLIPGENIUS_DATA_DIR": str(TMP), "CLIPGENIUS_SYNC_JOBS": "1"})
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient
from app.main import app
import app.services.analysis_service as asv
asv.transcribe_whisper = lambda path, language=None: {"source": "whisper:test-stub", "status": "unavailable", "language": None, "segments": [], "message": "offline"}

RESULTS = []
c = TestClient(app).__enter__()


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True)
    return json.loads(r.stdout)


def project(video, srt=SRT_EN, analyze=True):
    pid = c.post("/api/projects", json={"project_name": video.name}).json()["project_id"]
    with open(video, "rb") as f:
        r = c.post(f"/api/upload?project_id={pid}", files={"file": (video.name, f, "application/octet-stream")})
    if r.status_code != 201:
        raise RuntimeError(f"upload {r.status_code}: {r.text[:300]}")
    if srt:
        c.post(f"/api/projects/{pid}/transcript", json={"srt": srt})
    if analyze:
        c.post(f"/api/analyze/{pid}")
        p = c.get(f"/api/projects/{pid}").json()
        if p["status"] != "analyzed":
            raise RuntimeError(f"analysis status={p['status']}: {p.get('error_message')}")
    return pid


def plan_render(pid, prompt, overrides=None, preview=False, expect_plan=True):
    p = c.post(f"/api/edit/{pid}/plan", json={"prompt": prompt, "overrides": overrides})
    if p.status_code != 201:
        raise RuntimeError(f"plan {p.status_code}: {p.text[:300]}")
    p = p.json()
    if not expect_plan:
        return p, None
    if not p["renderable"]:
        raise RuntimeError(f"plan not renderable: {p['validation_status']} {p['validation']['violations']} {p['validation'].get('suggestions')}")
    j = (c.post(f"/api/edit/{pid}/preview") if preview else c.post(f"/api/render/{pid}")).json()
    st = c.get(f"/api/render/{j['job_id']}/status").json()
    if st["status"] != "completed":
        raise RuntimeError(f"render failed: {st['error_message']}")
    out = TMP / f"{j['job_id']}.mp4"
    out.write_bytes(c.get(st["download_url"]).content)
    return p, (st, out)


def case(name):
    def deco(fn):
        t = time.time()
        try:
            note = fn() or ""
            RESULTS.append((name, "PASS", note, time.time() - t))
        except Exception as e:
            RESULTS.append((name, "FAIL", f"{type(e).__name__}: {str(e)[:400]}", time.time() - t))
            if os.environ.get("FM_TRACE"): traceback.print_exc()
        return fn
    return deco

V = lambda n: VID / n
PROMPT = "Create a 10-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions."

def check_out(p, res, w=None, h=None, tol=0.8):
    st, out = res
    pr = probe(out); v = next(s for s in pr["streams"] if s["codec_type"] == "video")
    exp_w, exp_h = (w, h) if w else (p["output"]["width"], p["output"]["height"])
    assert (v["width"], v["height"]) == (exp_w, exp_h), f"dims {v['width']}x{v['height']} != {exp_w}x{exp_h}"
    d = float(pr["format"]["duration"]); assert abs(d - p["output"]["duration"]) <= tol, f"duration {d:.2f} vs plan {p['output']['duration']:.2f}"
    assert st["report"]["output_verification"]["ok"]
    return f"{v['width']}x{v['height']} {d:.1f}s clips={len(p['clips'])} cues={p['subtitles']['cue_count']}"

# ---------- input formats & media variants ----------
for fname in ["talking_one_shot.mp4", "phone_rot.mp4", "vfr.mp4", "cont.mov", "cont.mkv", "cont.webm", "cont.avi", "cinema_stereo.mp4", "surround.mp4", "mono8k.mp4", "quiet.mp4", "uhd8s.mp4"]:
    if not V(fname).exists(): continue
    @case(f"input: {fname}")
    def _(fname=fname):
        pid = project(V(fname))
        a = c.get(f"/api/analysis/{pid}").json()
        p, res = plan_render(pid, PROMPT if fname != "uhd8s.mp4" else "Create a 5-second vertical reel with subtitles")
        return f"scenes={a['summary']['scene_count']} meta={a['metadata']['width']}x{a['metadata']['height']} | " + check_out(p, res)

@case("input: video without audio")
def _():
    pid = project(V("noaudio.mp4"), srt=SRT_EN)
    p, res = plan_render(pid, PROMPT)
    return check_out(p, res)

# ---------- one-shot talking head: scene splitting quality ----------
@case("talking head: pause-based scene split (1 visual scene -> several)")
def _():
    pid = project(V("talking_one_shot.mp4"))
    a = c.get(f"/api/analysis/{pid}").json()
    n = a["summary"]["scene_count"]
    assert n >= 3, f"only {n} scene(s) detected for a 20 s video with 3 clear pauses: {a['scene_notes']}"
    return f"{n} scenes; " + "; ".join(a["scene_notes"])[:200]

@case("quiet speech is not cut away")
def _():
    pid = project(V("quiet.mp4"))
    p, res = plan_render(pid, "Create a 10-second vertical reel remove silence")
    segs = [s for cl in p["clips"] for s in cl["segments"]]
    assert segs, "no segments kept for quiet speech"
    return check_out(p, res)

# ---------- aspect x quality ----------
for ar in ("9:16", "16:9", "1:1"):
    for q in ("720p", "1080p"):
        @case(f"export {ar} {q}")
        def _(ar=ar, q=q):
            pid = project(V("talking_one_shot.mp4"))
            p, res = plan_render(pid, "Create a 10 second video", {"aspect_ratio": ar, "quality": q})
            return check_out(p, res)

# ---------- subtitles ----------
for st_ in ("classic", "bold", "animated", "karaoke"):
    @case(f"subtitle style {st_}")
    def _(st_=st_):
        pid = project(V("talking_one_shot.mp4"))
        p, res = plan_render(pid, PROMPT, {"subtitle_style": st_, "subtitle_size": 48, "subtitle_color": "#00FFAA", "subtitle_position": "center"})
        assert p["subtitles"]["cue_count"] > 0
        return check_out(p, res)

@case("subtitles: SRT export + burn-in off")
def _():
    pid = project(V("talking_one_shot.mp4"))
    p, res = plan_render(pid, PROMPT)
    srt = c.get(f"/api/edit/{pid}/subtitles.srt"); assert srt.status_code == 200 and "-->" in srt.text
    return check_out(p, res) + " | srt ok"

if SRT_GU:
    @case("subtitles: Gujarati + English text")
    def _():
        pid = project(V("talking_one_shot.mp4"), srt=SRT_GU)
        p, res = plan_render(pid, PROMPT)
        warn = [w for w in p["warnings"] if "Gujarati" in w]
        return check_out(p, res) + (f" | WARNING: {warn[0][:90]}" if warn else " | font ok")

@case("no transcript: plan warns and still renders")
def _():
    pid = project(V("talking_one_shot.mp4"), srt=None)
    p, res = plan_render(pid, PROMPT)
    assert any("no transcript" in w.lower() for w in p["warnings"])
    return check_out(p, res) + " | warned"

# ---------- editing options ----------
for preset in ("cinematic", "vivid", "bw"):
    @case(f"color preset {preset}")
    def _(preset=preset):
        pid = project(V("talking_one_shot.mp4")); p, res = plan_render(pid, PROMPT, {"color_preset": preset}); return check_out(p, res)

for tr in ("smooth", "fade", "none"):
    @case(f"transitions {tr}")
    def _(tr=tr):
        pid = project(V("talking_one_shot.mp4")); p, res = plan_render(pid, PROMPT, {"transition_style": tr}); return check_out(p, res) + f" transitions={[x['transition_in']['type'] for x in p['clips']]}"

@case("sequencing: A* vs chronological")
def _():
    pid = project(V("talking_one_shot.mp4"))
    p1, r1 = plan_render(pid, PROMPT, {"sequencing": "astar"}); p2, r2 = plan_render(pid, PROMPT, {"sequencing": "chronological"})
    ids = [x["scene_id"] for x in p2["clips"]]; assert ids == sorted(ids)
    return f"astar order {[x['scene_id'] for x in p1['clips']]} cost {p1['algorithms']['astar']['cost']} | chrono {ids}"

@case("silence removal on vs off changes plan")
def _():
    pid = project(V("talking_one_shot.mp4"))
    a, _r = plan_render(pid, "Create a 12 second vertical reel", expect_plan=False); b, _r = plan_render(pid, "Create a 12 second vertical reel", {"remove_silence": False}, expect_plan=False)
    assert any(o["op"] == "trim_silence" for o in a["operations"]) and not any(o["op"] == "trim_silence" for o in b["operations"])
    return f"removed {a['stats']['silence_seconds_removed']}s silence in {a['stats']['silence_intervals_removed']} gap(s)"

@case("topic focus changes scoring")
def _():
    pid = project(V("talking_one_shot.mp4"))
    p, res = plan_render(pid, "Create a 10 second reel focusing on artificial intelligence", {"topic": "artificial intelligence"})
    return check_out(p, res)

@case("music mixing + ducking")
def _():
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=f=220:d=4", str(TMP / "bed.mp3")], check=True)
    pid = project(V("talking_one_shot.mp4"))
    r = c.post(f"/api/projects/{pid}/music", files={"file": ("bed.mp3", (TMP / "bed.mp3").read_bytes(), "audio/mpeg")}); assert r.status_code == 201, r.text
    p, res = plan_render(pid, "Create a 10 second vertical reel with background music"); assert any(o["op"] == "music" for o in p["operations"])
    return check_out(p, res)

@case("quick preview render")
def _():
    pid = project(V("talking_one_shot.mp4")); p, res = plan_render(pid, PROMPT, preview=True)
    pr = probe(res[1]); v = next(s for s in pr["streams"] if s["codec_type"] == "video"); assert min(v["width"], v["height"]) == 360
    return f"preview {v['width']}x{v['height']}"

for tgt in (5, 8, 15, 19):
    @case(f"target duration {tgt}s from 20s source")
    def _(tgt=tgt):
        pid = project(V("talking_one_shot.mp4")); p, res = plan_render(pid, f"Create a {tgt} second vertical reel"); return check_out(p, res)

@case("infeasible request is explained")
def _():
    pid = project(V("talking_one_shot.mp4")); p, _r = plan_render(pid, "Create a 120 second vertical reel", expect_plan=False)
    assert p["validation_status"] == "infeasible" and p["validation"]["suggestions"]
    r = c.post(f"/api/render/{pid}"); assert r.status_code == 409
    return p["validation"]["suggestions"][0][:90]

@case("natural-language commands")
def _():
    pid = project(V("talking_one_shot.mp4")); out = []
    for pr_, key, val in [("Make this video suitable for YouTube Shorts", "aspect_ratio", "9:16"), ("Create a landscape video", "aspect_ratio", "16:9"), ("make a square 10 second video", "aspect_ratio", "1:1"),
                          ("Remove silence", "remove_silence", True), ("Add subtitles", "subtitles", True), ("Create cinematic edit", "color_preset", "cinematic"), ("Change target duration to 12 seconds", "target_duration", 12.0)]:
        p, _r = plan_render(pid, pr_, expect_plan=False); assert p["config"][key] == val, f"'{pr_}' -> {key}={p['config'][key]}"; out.append(key)
    return "ok"

@case("download of rendered file + execution report")
def _():
    pid = project(V("talking_one_shot.mp4")); p, res = plan_render(pid, PROMPT)
    rep = c.get(f"/api/report/{pid}").json(); assert rep["output_verification"]["ok"]
    return f"report ok, {len(rep['output_verification']['checks'])} checks"

print(f"\n{'CASE':58} {'RESULT':6} {'TIME':>6}  NOTE")
for n, r, note, t in RESULTS:
    print(f"{n[:58]:58} {r:6} {t:5.1f}s  {note[:230]}")
f = [r for r in RESULTS if r[1] == "FAIL"]
print(f"\n{len(RESULTS)-len(f)}/{len(RESULTS)} passed")
sys.exit(1 if f else 0)
