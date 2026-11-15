#!/usr/bin/env python3
"""Reproducible demonstration: 2-minute synthetic video -> 30 s vertical reel, through the real HTTP API.

Honest scope notes (also written into the report):
  * The video is SYNTHETIC (FFmpeg test patterns + tone bursts standing in for speech); no real person speaks in it.
  * Whisper weights cannot be downloaded in offline environments, so the demo imports an SRT transcript
    (a documented input path). With a real talking-head video and internet access, Whisper does this automatically.
Every number in the report is measured from the run; nothing is hard-coded.
Usage:  cd backend && python ../scripts/run_demo.py
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "demo"
TMP = Path(tempfile.mkdtemp(prefix="clipgenius_demo_"))
os.environ.update({"CLIPGENIUS_DATA_DIR": str(TMP), "CLIPGENIUS_SYNC_JOBS": "1"})
sys.path.insert(0, str(ROOT / "backend"))

SOURCES = ["testsrc2=s=1280x720:r=25:d=15", "mandelbrot=s=1280x720:r=25", "gradients=s=1280x720:r=25:d=15", "rgbtestsrc=s=1280x720:r=25:d=15",
           "cellauto=s=1280x720:r=25:rule=110", "life=s=1280x720:r=25:mold=10:life_color=#00ff00", "smptebars=s=1280x720:r=25:d=15", "testsrc2=s=1280x720:r=25:d=15:alpha=1"]
SPEECH = [11, 9, 12, 8, 10, 12, 7, 11]      # seconds of "speech-like" audio per 15 s scene, remainder is silence
TEXT = ["welcome to this introduction to artificial intelligence in video editing", "today we explore how intelligent agents plan an edit",
        "first the agent perceives the video and detects every scene", "scene detection finds the cuts between shots",
        "next speech recognition produces a timestamped transcript", "each scene receives an importance score from many signals",
        "the most important moments are selected for the final reel", "a star search orders the scenes to keep transitions smooth",
        "a constraint solver guarantees the duration and format rules", "an expert system adds subtitles transitions and audio rules",
        "silence is removed but speech is always preserved", "finally ffmpeg renders and verifies the exported video",
        "the result is a short vertical reel ready to share", "thank you for watching this demonstration"]


def sh(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def build_video(path: Path):
    inputs, vf, af = [], [], []
    for i, src in enumerate(SOURCES):
        inputs += ["-f", "lavfi", "-t", "15", "-i", src]
        vf.append(f"[{i}:v]trim=0:15,setpts=PTS-STARTPTS,fps=25,scale=1280:720,format=yuv420p[v{i}]")
        sp = SPEECH[i]
        af.append(f"sine=f={180+40*i}:d={sp},tremolo=f=5:d=0.8,aformat=sample_rates=44100:channel_layouts=mono,volume=0.6[s{i}];"
                  f"anullsrc=r=44100:cl=mono,atrim=0:{15-sp}[q{i}];[s{i}][q{i}]concat=n=2:v=0:a=1[a{i}]")
    graph = ";".join(vf + af) + ";" + "".join(f"[v{i}]" for i in range(8)) + "concat=n=8:v=1:a=0[vo];" + "".join(f"[a{i}]" for i in range(8)) + "concat=n=8:v=0:a=1[ao]"
    sh(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[vo]", "-map", "[ao]", "-t", "120", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "28", "-c:a", "aac", str(path)])


def srt() -> str:
    cues, k = [], 0
    for i, sp in enumerate(SPEECH):
        base = i * 15
        n = 2 if sp >= 9 else 1
        for j in range(n):
            if k >= len(TEXT): break
            a, b = base + 0.4 + j * sp / n, base + (j + 1) * sp / n - 0.2
            cues.append((a, b, TEXT[k])); k += 1
    def t(x): h, r = divmod(int(x * 1000), 3600000); m, r = divmod(r, 60000); s, ms = divmod(r, 1000); return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    return "\n".join(f"{i}\n{t(a)} --> {t(b)}\n{x}\n" for i, (a, b, x) in enumerate(cues, 1))


def main():
    from fastapi.testclient import TestClient
    from app.main import app
    OUT.mkdir(parents=True, exist_ok=True)
    video = TMP / "demo_input.mp4"
    print("Generating 120 s synthetic input video ..."); build_video(video)
    prompt = "Create a 30-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions."
    t0 = time.perf_counter()
    with TestClient(app) as c:
        pid = c.post("/api/projects", json={"project_name": "Demo: 2-minute video to 30 s reel"}).json()["project_id"]
        with open(video, "rb") as f:
            assert c.post(f"/api/upload?project_id={pid}", files={"file": ("demo_input.mp4", f, "video/mp4")}).status_code == 201
        c.post(f"/api/projects/{pid}/transcript", json={"srt": srt()})
        c.post(f"/api/analyze/{pid}")
        analysis = c.get(f"/api/analysis/{pid}").json()
        plan = c.post(f"/api/edit/{pid}/plan", json={"prompt": prompt}).json()
        print("plan:", plan["validation_status"], "duration", plan["output"]["duration"], "clips", [x["scene_id"] for x in plan["clips"]])
        job = c.post(f"/api/render/{pid}").json()
        st = c.get(f"/api/render/{job['job_id']}/status").json()
        if st["status"] != "completed":
            print("RENDER FAILED:", st["error_message"]); sys.exit(1)
        total = time.perf_counter() - t0
        rep = c.get(f"/api/report/{pid}").json()
        rep["wall_clock_seconds_end_to_end"] = round(total, 2)
        rep["input_description"] = "Synthetic 120 s 1280x720 test video (FFmpeg patterns + tone bursts); transcript imported as SRT (Whisper weights unavailable offline)"
        rep["scene_table"] = [{k: s[k] for k in ("scene_id", "start", "end", "importance", "speech_density", "silence_pct", "motion", "transcript")} for s in analysis["scenes"]]
        (OUT / "demo_report.json").write_text(json.dumps(rep, indent=2))
        (OUT / "demo_plan.json").write_text(json.dumps({k: plan[k] for k in ("config", "clips", "removed_scenes", "operations", "output", "validation", "warnings")}, indent=2))
        (OUT / "demo_astar.json").write_text(json.dumps(c.get(f"/api/algorithms/{pid}/astar").json(), indent=2))
        (OUT / "demo_csp.json").write_text(json.dumps(c.get(f"/api/algorithms/{pid}/csp").json(), indent=2))
        (OUT / "demo_expert_system.json").write_text(json.dumps(c.get(f"/api/algorithms/{pid}/expert-system").json(), indent=2))
        (OUT / "demo_agent_decisions.json").write_text(json.dumps(c.get(f"/api/agents/{pid}/decisions").json(), indent=2))
        (OUT / "demo_reel.mp4").write_bytes(c.get(st["download_url"]).content)
        (OUT / "demo_subtitles.srt").write_text(c.get(f"/api/edit/{pid}/subtitles.srt").text)
    print(json.dumps({k: rep[k] for k in ("original_duration", "final_duration_measured", "scenes_detected", "scenes_selected", "removed_segments", "astar", "csp",
                                          "expert_rules_triggered", "processing_seconds", "wall_clock_seconds_end_to_end")}, indent=2))
    print("output verification ok:", rep["output_verification"]["ok"], "|", len(rep["output_verification"]["checks"]), "checks")
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
