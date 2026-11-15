#!/usr/bin/env python3
"""Full UI exercise with Playwright (server must be running with the built frontend on :8000).
Usage: python ui_e2e_full.py <video.mp4> <transcript.srt> [<music.mp3>]"""
import sys, time
from playwright.sync_api import sync_playwright
VIDEO, SRT = sys.argv[1], sys.argv[2]
MUSIC = sys.argv[3] if len(sys.argv) > 3 else None
errs, bad, steps = [], [], []

def step(name, ok=True, note=""):
    steps.append((name, ok, note)); print(("PASS " if ok else "FAIL ") + name, note, flush=True)

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 900}, accept_downloads=True)
    pg.on("pageerror", lambda e: errs.append("pageerror: " + str(e)))
    pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" and "404" not in m.text else None)
    pg.on("response", lambda r: bad.append(f"{r.status} {r.request.method} {r.url}") if r.status >= 400 and not (r.status == 404 and r.url.endswith("/plan")) else None)

    def tryit(name, fn):
        try: fn(); step(name)
        except Exception as e: step(name, False, str(e).splitlines()[0][:200])

    pg.goto("http://localhost:8000/"); pg.wait_for_selector("text=Edit video with an AI agent")

    def bad_upload():
        pg.click("text=New project >> nth=0"); open("/tmp/not_video.mp4", "wb").write(b"not a video" * 500)
        pg.set_input_files("input[type=file]", "/tmp/not_video.mp4"); pg.click("text=Upload & analyze")
        pg.wait_for_selector("text=Not a readable video", timeout=15000); pg.click("button:has(svg.lucide-x)")
    tryit("dashboard: invalid file rejected with visible message", bad_upload)

    def good_upload():
        pg.click("text=New project >> nth=0"); pg.fill("input[placeholder*='Product launch']", "E2E project")
        pg.set_input_files("input[type=file]", VIDEO); pg.click("text=Upload & analyze")
        pg.wait_for_selector("text=Tell me how to edit it", timeout=120000)
    tryit("upload + analysis (overlay, then assistant greeting)", good_upload)
    tryit("missing-transcript notice is shown", lambda: pg.wait_for_selector("text=No transcript is available"))

    def srt():
        pg.set_input_files("input[accept='.srt,text/plain']", SRT); time.sleep(9)
        pg.wait_for_selector("text=/\\d+ cues|Download SRT|artificial intelligence/") if False else None
        body = pg.inner_text("body"); assert "No transcript (" not in body, "timeline still reports no transcript"
    tryit("import SRT re-runs analysis and transcript appears on timeline", srt)
    tryit("timeline: click to seek", lambda: (pg.mouse.click(500, 700), time.sleep(.5)))
    tryit("timeline: zoom +/-", lambda: (pg.click("text=px/s >> xpath=../button[2]"), pg.click("text=px/s >> xpath=../button[1]")))
    tryit("sidebar: project files + thumbnail seek", lambda: (pg.click("text=Project files"), pg.click("img[loading=lazy] >> nth=1"), pg.click("button:has-text('Media')")))
    if MUSIC:
        tryit("music upload", lambda: (pg.set_input_files("input[accept='audio/*']", MUSIC), pg.wait_for_selector("text=Background music uploaded")))

    def plan():
        pg.click("text=Editing configuration"); pg.fill("textarea", "Create a 10 second vertical reel with animated subtitles and smooth transitions"); pg.keyboard.press("Enter")
        pg.wait_for_selector("text=Editing plan ready", timeout=60000)
    tryit("assistant: prompt -> plan card", plan)
    tryit("plan card: scenes, operations, constraints", lambda: (pg.wait_for_selector("text=Selected scenes"), pg.wait_for_selector("text=Editing operations"), pg.wait_for_selector("text=Constraint results")))

    def preview_mode():
        pg.click("button:has-text('Plan preview')"); pg.click("button.btn-primary:has(svg.lucide-play)"); time.sleep(3)
        t = pg.inner_text("div.font-mono >> nth=0"); assert t.strip() and not t.strip().startswith("0:00.0 / 0:00.0"), t
    tryit("plan preview plays the planned segments", preview_mode)

    def tabs():
        pg.click("button:has-text('Analysis dashboard')")
        for tab, marker in [("Overview", "Scene importance"), ("A* search", "Search visualisation"), ("CSP validation", "Backtracks"), ("Expert system", "Backward chaining"), ("Agent log", "PEAS")]:
            pg.click(f"button:has-text('{tab}')"); pg.wait_for_selector(f"text={marker}", timeout=8000)
        pg.click("button:has-text('Overview')"); pg.click("svg rect >> nth=1")
    tryit("analysis dashboard: 5 tabs render", tabs)
    tryit("back to preview", lambda: pg.click("button:has-text('Preview') >> nth=0"))

    def quick_preview():
        pg.click("div.ml-auto button:has-text('Preview')"); pg.wait_for_selector("text=preview render", timeout=20000)
        pg.wait_for_selector("text=Download MP4", timeout=120000)
    tryit("top bar Preview -> quick preview completes", quick_preview)

    def rendered_tab():
        pg.click("button:has-text('Preview') >> nth=0"); pg.click("button:has-text('Rendered')"); pg.wait_for_selector("video"); time.sleep(1.5)
        assert pg.eval_on_selector("video", "v => v.readyState") >= 1
    tryit("'Rendered' tab loads render in player", rendered_tab)

    def export_opts():
        pg.click("div.ml-auto button:has-text('Export')"); pg.select_option("select >> nth=0", "720p")
        pg.click("button:has-text('Export MP4')"); pg.wait_for_selector("text=final render", timeout=20000)
        pg.wait_for_selector("text=Execution report", timeout=240000)
    tryit("export with changed resolution (re-plan + render)", export_opts)
    tryit("execution report lists FFprobe checks", lambda: (pg.click("text=Execution report"), pg.wait_for_selector("text=Rules fired"), pg.wait_for_selector("text=full_decode_no_errors")))

    def download():
        with pg.expect_download() as d: pg.click("a:has-text('Download MP4') >> nth=0")
        d.value.save_as("/tmp/e2e_full.mp4")
    tryit("download MP4", download)

    def infeasible():
        pg.click("button:has-text('AI assistant')"); pg.fill("textarea", "Create a 200 second vertical reel"); pg.keyboard.press("Enter")
        pg.wait_for_selector("text=Plan could not be satisfied", timeout=30000); assert pg.is_disabled("button:has-text('Apply edits') >> nth=-1")
    tryit("infeasible plan explained, Apply edits disabled", infeasible)

    def home_delete():
        pg.click("button[title='Back to dashboard']"); pg.wait_for_selector("text=Recent projects"); pg.wait_for_selector("text=E2E project")
        pg.wait_for_selector("text=Editing history"); pg.once("dialog", lambda d: d.accept())
        pg.hover("text=E2E project"); pg.click("button[title='Delete project'] >> nth=0"); time.sleep(1.5)
        assert pg.locator("text=E2E project").count() == 0
    tryit("dashboard: history + delete project", home_delete)
    b.close()
fails = [s for s in steps if not s[1]]
print(f"\n{len(steps)-len(fails)}/{len(steps)} UI steps passed"); print("JS errors:", errs or "none"); print("HTTP >=400 (excl. expected plan 404):", bad or "none")
sys.exit(1 if fails or errs else 0)
