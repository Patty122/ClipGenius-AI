# Faculty Demonstration Guide (≈ 10 minutes)

## Before you start
1. `cd backend && uvicorn app.main:app --port 8000` and `cd frontend && npm run build` (UI is then served at http://localhost:8000), **or** run `npm run dev` for :5173.
2. Prepare a 1–3 minute video with speech. For the first Whisper run, be online once (model download ~75 MB). If offline, export/obtain an `.srt` for the clip.
3. Check the **System** card on the dashboard: FFmpeg ✔, FFprobe ✔.

## Script
| # | Action | What to say / show |
|---|---|---|
| 1 | Dashboard → **New project** → upload video | Upload is validated by *probing the content*, not just the extension. |
| 2 | Wait for analysis (progress is measured, not simulated) | Perceive stage: FFprobe metadata → silencedetect → Whisper → PySceneDetect → OpenCV features. |
| 3 | Timeline | Scene blocks with importance, cyan audio activity, red silence, transcript. Click to seek. |
| 4 | Assistant → paste: *Create a 30-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions.* | Understand stage: deterministic parser → validated `EditConfig` (no LLM needed). |
| 5 | Read the **plan card** | Selected/removed scenes with reasons, operations, CSP result, A\* vs chronological cost. This is the human-review step. |
| 6 | **Analysis dashboard** → *Overview* | Click a bar: exact score breakdown and which features were missing. |
| 7 | → *A\* search* | Expansion table with g, h, f; optimal flag; chronological comparison. Explain admissible MST heuristic. |
| 8 | → *CSP validation* | Constraint list, nodes/backtracks/pruned values, assignment. Then request an impossible edit (*"Create a 300 second reel"*) → infeasible, reasons + suggestions, **Export disabled / API returns 409**. |
| 9 | → *Expert system* | Fired rules with facts; backward-chaining proof of `vertical_reel_ready`. |
| 10 | → *Agent log* | PEAS phases and agents. |
| 11 | Preview centre tab → **Plan preview** | Instant playback of the plan from the original footage with aspect crop. |
| 12 | **Apply edits** → Export panel | Real progress bar from FFmpeg `-progress`; then verified download and the execution report (FFprobe checks). |
| 13 | Open the MP4 | 1080×1920, burned subtitles in the safe area. |

## Reproducible numbers
`cd backend && python ../scripts/run_demo.py` regenerates `docs/demo/*.json` from a synthetic video (≈ 70 s on one core). State clearly that it is synthetic and uses an imported SRT.

## Likely demo problems
* *Whisper "unavailable"* → no internet for the first model download: import an SRT (Media panel → Import SRT) and press analyze again.
* *Non-Latin text shows boxes* → add a font for that script to `backend/assets/fonts/` (Noto Sans Gujarati is bundled).
* *Render slow* → CPU-only; use 720p for the live demo (Export → Resolution).
