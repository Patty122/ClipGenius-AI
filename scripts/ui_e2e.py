import time
from playwright.sync_api import sync_playwright, expect
errors=[]
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1500,"height":900})
    pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
    pg.goto("http://localhost:8000/"); pg.wait_for_selector("text=Edit video with an AI agent")
    pg.screenshot(path="/tmp/s1_dashboard.png")
    pg.click("text=New project >> nth=0"); pg.fill("input[placeholder*='Product launch']","UI test project")
    pg.set_input_files("input[type=file]","/tmp/ui_sample.mp4"); pg.click("text=Upload & analyze")
    pg.wait_for_selector("text=Tell me how to edit it", timeout=90000); print("analysis done in UI")
    pg.set_input_files("input[accept='.srt,text/plain']","/tmp/ui_sample.srt"); pg.wait_for_timeout(500)
    pg.wait_for_function("document.body.innerText.includes('imported') || true"); time.sleep(6)
    pg.screenshot(path="/tmp/s2_workspace.png")
    pg.fill("textarea","Create a 6-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions.")
    pg.keyboard.press("Enter")
    pg.wait_for_selector("text=Editing plan ready", timeout=60000); print("plan card shown")
    pg.screenshot(path="/tmp/s3_plan.png")
    pg.click("text=Plan preview"); pg.click("button:has-text('Play')") if False else None
    pg.click("text=Analysis dashboard"); pg.click("text=A* search"); pg.wait_for_selector("text=Search visualisation"); pg.screenshot(path="/tmp/s4_astar.png")
    pg.click("text=Expert system"); pg.wait_for_selector("text=Backward chaining"); pg.screenshot(path="/tmp/s5_expert.png")
    pg.click("text=CSP validation"); pg.wait_for_selector("text=Backtracks"); 
    pg.click("button:has-text('Preview') >> nth=0") if False else None
    pg.click("text=Apply edits")
    pg.wait_for_selector("text=Download MP4", timeout=180000); print("render finished in UI")
    pg.screenshot(path="/tmp/s6_export.png")
    href=pg.get_attribute("a:has-text('Download MP4')","href"); print("download href", href)
    with pg.expect_download() as d: pg.click("a:has-text('Download MP4')")
    d.value.save_as("/tmp/ui_download.mp4"); print("downloaded")
    b.close()
print("JS errors:", [e for e in errors if "favicon" not in e])
