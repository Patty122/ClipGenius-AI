# ClipGenius AI — Academic Report
**An Intelligent Agent-Based Video Editing and Optimization System Using Artificial Intelligence**
*Fundamentals of Artificial Intelligence — final project*

> **Provenance legend.** **[OWN]** = algorithm implemented by us in this repository. **[LIB]** = third-party library used as a tool. **[MODEL]** = third-party pretrained model. **[OPT]** = optional integration. All numbers marked *measured* come from `scripts/run_demo.py` (files in `docs/demo/`) or `pytest`; none are hand-written.

---
## 1. Abstract
ClipGenius AI turns raw footage plus a natural-language instruction into an edited, verified MP4. A modular intelligent agent perceives the video (FFprobe, PySceneDetect, OpenCV, silence analysis, transcript), scores scenes with an explainable heuristic, **sequences** candidate scenes with a hand-written **A\*** search (admissible MST heuristic), assigns durations/transitions/subtitle placement with a hand-written **CSP backtracking solver**, applies a **rule-based expert system** (forward and backward chaining), validates the final plan independently, and renders with FFmpeg. On the reproducible demonstration (120 s synthetic video → 30 s 1080×1920 reel) the pipeline detected 17 scenes, selected 8, satisfied all constraints in 16 CSP nodes (4 backtracks), and produced a file that passed 9/9 FFprobe/decode checks (measured duration 29.37 s vs target 30 ± 1 s). 98 automated tests pass, and a 46-case feature matrix plus a 20-step browser test were run on realistic inputs (phone rotation, VFR, MOV/MKV/WebM/AVI, 5.1/mono audio, UHD, single-shot talking head).

## 2. Introduction
Short-form video editing is repetitive: find the good moments, cut dead air, fit a duration, reframe for a platform, caption, export. These sub-problems map onto classical AI topics — agents, heuristic search, constraint satisfaction and knowledge-based systems — which makes video editing a useful, visible domain for Fundamentals of AI.

## 3. Problem Statement
Given a video *V* of duration *T*, and an instruction *I* (target duration, aspect ratio, subtitles, silence removal, transitions…), produce an edit *E* — an ordered list of source segments with transitions — that (a) preserves the most important content, (b) satisfies hard format constraints, (c) has smooth transitions, and (d) can be rendered and verified automatically, without a paid cloud service.

## 4. Objectives
The 15 objectives of the brief map to modules as follows: automatic analysis (`services/analysis_service.py`), scene detection (`ai/scene_detector.py`), transcription (`ai/speech_analyzer.py`), importance scoring (`ai/scene_scorer.py`), selection (`services/planning_service.py`), A\* sequencing (`algorithms/astar.py`), CSP (`algorithms/csp.py`, `backtracking.py`), expert system (`algorithms/expert_system.py`, `forward_chaining.py`, `backward_chaining.py`), silence removal (`core/audio_processor.py`), subtitles (`rendering/subtitle_renderer.py`), reframing + rendering + audio (`rendering/ffmpeg_engine.py`), preview/export (React app), explainability (decision log, score explanations, rule traces).

## 5. Literature and Technology Review
* **Agents and PEAS** — Russell & Norvig, *Artificial Intelligence: A Modern Approach*, 4th ed. (2020).
* **A\*** — Hart, Nilsson & Raphael (1968): A\* with an admissible heuristic returns an optimal path.
* **MST heuristics** — Prim (1957) minimum spanning tree as a lower bound for path-through-all-nodes problems.
* **CSP** — backtracking with variable ordering (MRV) and forward checking: Haralick & Elliott (1980); AIMA ch. 6.
* **Knowledge-based systems** — production rules with forward/backward chaining: AIMA ch. 7–9.
* **Text relevance** — TF-IDF weighting (Salton & Buckley, 1988) and cosine similarity [LIB: scikit-learn].
* **Colour-histogram comparison** — Bhattacharyya distance (1943) [LIB: OpenCV for histograms].
* **Speech recognition** — Whisper (Radford et al., 2022, arXiv:2212.04356) via faster-whisper [MODEL/LIB].
* **Scene detection** — content-aware HSV-difference detector [LIB: PySceneDetect]. **Media** — FFmpeg/FFprobe; EBU R128 loudness (EBU R 128, 2014).

## 6. Existing Systems
Consumer editors (CapCut, Adobe Premiere's text-based editing and auto-reframe, Descript, clip-extraction services) automate parts of this workflow, but they are closed products: the decision process (why a scene was kept, which constraints were checked) is not inspectable and they usually depend on cloud services. They are cited as context only; we make no claims about their internals.

## 7. Proposed System
A local, inspectable agent that exposes every decision: per-scene score breakdowns, the A\* search trace, the CSP constraint list and search statistics, each expert rule's facts and firing status, and a chronological agent decision log. A plan that fails validation is never rendered, and the output is verified by FFprobe plus a full decode.

## 8. System Architecture
```
 React/Vite UI ──HTTP/JSON──▶ FastAPI routes ──▶ services ──▶ AI/algorithm modules ──▶ FFmpeg/FFprobe
 (dashboard, workspace,        (validation,       analysis       perception, speech,       (restricted
  timeline, assistant,          background jobs)  planning       scorer, A*, CSP,           subprocess)
  analysis, export)                               rendering      expert system
                                   │
                         SQLite (SQLAlchemy): projects, scenes, editing_plans, render_jobs, agent_decisions
                         Filesystem: uploads/<project>/, outputs/<job>/, temp/<job>/   (no videos in SQLite)
```
Flow: **upload → validate (probe) → analyze → plan (review) → validate → render → verify → download**. Long operations run in a single-worker background pool (one CPU core is the target machine) with measured progress (FFmpeg `-progress`).

## 9. PEAS Representation
| | |
|---|---|
| **Performance measure** | content preservation (importance of kept scenes), duration accuracy, subtitle accuracy, visual continuity (transition cost), audio quality (loudness, fades), constraint satisfaction |
| **Environment** | uploaded video, its audio stream and metadata, the user instruction, the editing configuration |
| **Actuators** | trim, scene selection, scene sequencing, subtitle generation, audio processing, rendering |
| **Sensors** | video frames, audio signal, speech transcript, scene-detection output, metadata (FFprobe) |

## 10. Intelligent Agent Architecture
`AgentContext` (`ai/agent_controller.py`) holds shared state and persists every decision (`agent_decisions` table) with phase ∈ {perceive, understand, plan, decide, validate, act, evaluate}. Six cooperating modules inside one process: **Video Perception Agent** (metadata, scenes, frames), **Speech Analysis Agent** (silence, transcript), **Scene Evaluation Agent** (scoring), **Editing Planner Agent** (interpret, select, sequence, assemble), **Constraint Validation Agent** (CSP + validator), **Rendering Agent** (FFmpeg + verification).
*Why goal-based:* the agent chooses actions to reach an explicit goal state (an edit meeting format and duration). *Why utility-based:* among goal-satisfying edits it prefers those maximising Σ importance − transition cost, i.e. it ranks outcomes by a utility rather than only checking goal satisfaction.

## 11. State-Space Representation
*Sequencing (A\*)* — state = (current scene, set of visited scenes); initial = virtual root (any scene may start, g = 0); actions = go to an unvisited scene; goal = all candidates visited; step cost = transition cost c(a,b). State space size ≤ n·2ⁿ.
*Planning (CSP)* — state = partial assignment of variables to domain values; goal = complete assignment satisfying all constraints.

## 12. A\* Search Algorithm — `algorithms/astar.py` **[OWN]**
* **Definition.** Best-first search expanding the node with minimal f(n) = g(n) + h(n); optimal when h is admissible and goals are tested on expansion.
* **Why needed.** Order of kept scenes affects continuity; choosing the cheapest ordering is a shortest-Hamiltonian-path problem.
* **Formulation.** c(a,b) = w_v·D_B(end(a),start(b)) + w_a·min(1,|L_a−L_b|/30) + w_s·(1−cos_tfidf(a,b)) + w_t·τ(a,b), with weights normalised to 1 (defaults .30/.20/.20/.30). D_B = Bhattacharyya distance of HSV histograms; L = mean loudness (dB); τ = 0.5·gap/T for forward jumps, 0.5 + 0.5·back-jump/T for backward jumps.
* **Input / Output.** Cost matrix (n×n) / ordered scene list, cost, expanded/generated/explored counts, time, expansion trace, chronological order and its cost.
* **Working.** (1) push every start state with f = h; (2) pop min-f; skip stale entries; (3) if all visited → return; (4) expand to each unvisited scene, keep it if g improves (re-opening allowed); (5) repeat. Beam fallback (width 64) above 9 candidates or 200 000 expansions — **labelled not guaranteed optimal**.
* **Source.** `astar_sequence`, `beam_sequence`, `sequence_scenes` in `astar.py`.
* **Example (measured).** 8 candidates: 76 expanded, 366 generated, 361 states, 3.3 ms, cost 2.716678 = chronological cost (0 % improvement — chronological order was already optimal under this cost model; reported honestly).
* **Complexity.** Time O(n³·2ⁿ) worst case (n·2ⁿ states × O(n) successors × memoised O(n²) heuristic); space O(n·2ⁿ). Beam: O(B·n⁴).
* **Tests.** `test_astar_matches_bruteforce_optimum` (n = 2…7, equals brute-force optimum), fixed-first, beam flagged, chronological comparison, trivial cases — all pass.

## 13. Heuristic Function — `algorithms/heuristic.py` **[OWN]**
h(n) = MST weight (Prim) over {current} ∪ unvisited, computed on w(i,j) = min(c(i,j), c(j,i)).
*Admissibility argument:* the true remaining cost is a directed Hamiltonian path starting at *current*; each of its edges costs ≥ w(i,j); a Hamiltonian path is a spanning tree, so its undirected-lower cost ≥ MST weight. Hence h never overestimates. h(goal) = 0.
*Tests.* `test_heuristic_is_admissible_and_goal_is_zero` checks h ≤ brute-force remaining cost on random states; `test_mst_weight_known_graph`.

## 14. CSP Formulation — `algorithms/csp.py` **[OWN]**
* **Variables.** `aspect`, `resolution`, `sub_pos` (subtitle position), `trans` (transition duration), `dur_<scene>` (seconds of usable content kept; 0 = dropped). Start/end timestamps follow from `dur` and the scene's kept intervals; audio duration is derived and checked by the validator.
* **Domains.** aspect ∈ {requested}; resolution ∈ supported profiles for the aspect (1080×1920/720×1280, 1920×1080/1280×720, 1080×1080/720×720); sub_pos ∈ {top, center, lower, bottom}; trans ∈ {0.3, 0.5, 0.8} (or {0} for hard cuts); dur ∈ {0} ∪ {min_len, min_len+0.5, …, usable length}.
* **Constraints (7 in the solver + independent validator with 11 checks).** target duration ± tolerance (n-ary, with bound pruning); min scene duration; within source bounds; ≥ 1 scene kept; export dimensions match aspect; subtitle inside platform safe area (9:16: 12–78 % of height); transition ≤ ½ of every adjacent clip. Validator additionally checks negative/inverted timestamps, unintended overlap (a scene used twice), audio/video sync, cue timestamps.
* **Failure handling.** `diagnose_failure` computes achievable content and produces concrete suggestions; the API returns status `infeasible`, and `/render` answers 409.

## 15. Backtracking Algorithm — `algorithms/backtracking.py` **[OWN]**
Depth-first assignment with **MRV** (fewest legal values; ties → highest scene importance), **value ordering** (values closest to the scene's importance-proportional share of the target duration first; 0 last), **forward checking** (prune values violating any constraint) and per-constraint failure counters.
*Example (measured):* 16 nodes, 4 backtracks, 65 values pruned, solution `trans=0.8, sub_pos=lower, dur_0=7.5, dur_2=4.5, dur_6=3.5, dur_8=4.0, dur_9=3.5, dur_10=3.91, dur_13=4.5, dur_15=3.5`.
*Complexity:* worst case O(dⁿ) (d ≈ 20 values, n ≤ 9 scene variables); MRV + forward checking make typical cases near-linear. *Tests:* map-colouring solved; a 4-clique with 3 colours is proved unsatisfiable with backtracks > 0; MRV picks singleton domains first; infeasible target returns `None` with failed-constraint counts.

## 16. Knowledge Base — `algorithms/expert_system.py` **[OWN]**
15 IF-THEN rules over a working memory of facts; each rule has premises (`Cond(fact, op, value|Ref)`), a conclusion fact, recommendation and explanation. Scopes: *scene*, *transition*, *global*.
R1 trim silence · R2 retain high-relevance speech · R3 drop short low-value scene · R4 vertical reframing (9:16) · R5/R5b subtitles from transcript / blocked without transcript · R6 strong transition (fade / fade-to-black) when continuity is poor · R6b soft dissolve for jump cuts (so an explicit *smooth transitions* request is honoured at every boundary) · R7 mix music with ducking · R8 focus-aware crop · R9 short-form profile · R10 loudness normalisation · G1–G3 derived rules for the *vertical_reel_ready* goal.
Each execution is stored: rule id, condition text, facts evaluated, fired?, recommendation, explanation (`GET /algorithms/{id}/expert-system`). Rule outcomes drive the pipeline (exclusions, priority boost, per-boundary transition vs hard cut, reframe mode, audio chain).

## 17. Forward Chaining — `forward_chaining.py` **[OWN]**
Data-driven: repeat { fire every unfired rule whose premises hold; assert its conclusion } until no new fact. Example (tested): R4 asserts `reframe_scheduled`, which enables R8 and R9 on the next pass. *Complexity:* O(iterations · |rules| · |premises|), iterations ≤ number of derivable facts. *Measured demo:* fired R1, R2, R3, R4, R5, R6, R6b, R8, R9, R10 (+ derived G1–G3).

## 18. Backward Chaining — `backward_chaining.py` **[OWN]**
Goal-driven: to prove *g*, find rules concluding *g* and recursively prove each premise (facts are checked directly; derivable premises become sub-goals; cycles are cut). Returns a proof tree and the list of unmet leaf requirements. *Measured demo:* `vertical_reel_ready` **proved** via G1 ← {aspect 9:16, reframe_scheduled (R4), resolution_vertical (G2), duration_ok_for_short_form (G3)}. *Tests:* proof from base facts only; recognition of an already-derived fact; failure explanation for 16:9/300 s.

## 19. Computer Vision Pipeline — `ai/video_perception.py`, `ai/scene_detector.py`
1. FFprobe metadata (duration, fps, resolution, codecs, rotation, audio streams) **[LIB]**. 2. PySceneDetect ContentDetector (threshold 27) **[LIB]**; scenes > 8 s are split recursively at the midpoint of their longest interior silence **[OWN]** (essential for single-shot talking-head footage, where the visual detector finds no cuts), scenes < 1 s are merged. 3. One sequential decode pass samples ≈ 4 frames/s per scene; per sample: 8×4×4 HSV histogram, 96×54 grayscale **[LIB: OpenCV]**. 4. **Motion** = mean |Δgray|/255 between consecutive samples; **focus_x** = motion-energy centroid (drives crop); **signatures** (first/last/mean histogram) feed transitions and distinctiveness; thumbnail = middle frame. 5. Audio: `silencedetect` (−35 dB, 0.5 s) → silence/activity; RMS loudness per scene. **No scene descriptions are generated** (no vision-language model is used); YOLO [OPT] is not integrated.
*Tests:* cuts at 4 s/8 s found within 0.2 s; flat colours have motion < 0.001 while the moving pattern > 0.003; identical histograms → distance 0.

## 20. Implementation Details
Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (SQLite, WAL), ≈ 3 200 lines (+ ≈ 800 lines of tests). Frontend: React 18 + Vite + TypeScript + Tailwind, ≈ 930 lines; custom timeline with scene, audio, silence, transcript, edit and subtitle tracks. Key engineering decisions:
* **Per-segment seeked inputs** (`-ss/-t -i`) instead of one input with `trim`: the latter buffered ≈ the whole source in RAM and the render was OOM-killed (observed, exit −9, on the 3.9 GB sandbox); the fix keeps memory flat.
* **Silence removal never drops speech**: kept intervals = audio activity ∪ transcript segments, each padded by 0.15 s.
* **Cut-count reconciliation**: transitions overlap clips (shortening the output) while hard cuts do not; the planner re-solves the CSP with the number of hard-cut boundaries decided by rule R6 until consistent.
* **Missing-feature policy**: unavailable features are excluded and weights renormalised; reported per scene.
* **Honest fallbacks**: Whisper unavailable → `unavailable` + real error; SRT import; font warning surfaced in the plan. Whisper runs with Silero VAD (retry without) to avoid hallucinated text over silence.
* **Bugs found by realistic-input testing and fixed**: single-shot videos were split too coarsely (20 s → 2 scenes; now at every pause); explicit *smooth transitions* degraded to hard cuts on visually-continuous scenes (rule R6b); the Gujarati font warning was raised at render time and discarded (now in the plan; a Noto Sans Gujarati font is bundled and Gujarati+English captions were verified visually); absolute font paths would break the filter on Windows (now relative).

## 21. Test Cases (98 tests, all passing)
| File | # | Covers |
|---|---|---|
| `test_algorithms.py` | 37 | A\* vs brute force, heuristic admissibility, beam flagged, CSP satisfy/infeasible, backtracking, MRV, 10 validator violations, forward/backward chaining |
| `test_media.py` | 19 | FFprobe metadata, silence timestamps, loudness, keep-intervals, scene detection, visual features, scoring/missing features/weights, Whisper stubs (ok/unavailable), SRT, cue mapping, ASS styles/Unicode, upload & path security, binary allow-list |
| `test_api.py` | 21 | project CRUD, upload validation, real analysis, plan validity, algorithm endpoints, infeasible → 409, render + preview + download + FFprobe verification + report, original untouched, export re-plan, no-audio video, chronological toggle, interrupted-job handling |
| `test_render_features.py` | 10 | all 4 subtitle styles, colour presets, square/720p, music ducking, warnings, silence statistics |
| `test_real_world.py` | 11 | single-shot pause splitting, phone rotation (upright, no letterbox), MOV/MKV/WebM/AVI, smooth transitions on jump cuts, Gujarati font + rendering, font-warning propagation, relative font path |
Requirement coverage 1–16 of the brief: metadata ✔, scene detection ✔, transcription integration ✔ (stubbed model), scoring ✔, A\* ✔, admissibility ✔, CSP ✔, backtracking ✔, forward ✔, backward ✔, plan validation ✔, FFmpeg rendering ✔, subtitles ✔, API ✔, upload validation ✔, output verification ✔. Beyond pytest: `scripts/feature_matrix.py` (46 cases over 12 input variants and every option; first run 44/46, the 2 failures led to the scene-splitting fix and were otherwise expected-infeasible), and `scripts/ui_e2e_full.py` (Playwright, 20 UI steps: invalid upload message, upload/analysis, SRT import, timeline seek/zoom, music upload, plan, plan preview, all 5 analysis tabs, quick preview, rendered tab, export with re-plan, report, download, infeasible plan, delete) — all passed with no JS errors.

## 22. Results and Observations (measured, `docs/demo/demo_report.json`)
Input: synthetic 120.0 s, 1280×720, 8 patterns with tone-burst "speech" and silences; transcript imported as SRT (see limitations). Instruction: *"Create a 30-second vertical Instagram Reel. Preserve important speech, remove unnecessary silence, add animated subtitles and use smooth transitions."*
| Metric | Value |
|---|---|
| Detected scenes / selected | 17 / 8 (scene ids 0, 2, 6, 8, 9, 10, 13, 15) |
| Removed | 9 scenes; 1 silence gap (2.35 s) inside used spans |
| Planned / measured final duration | 29.31 s / 29.37 s (target 30 ± 1 s) |
| A\* | exact, optimal; 76 expanded, 366 generated; cost 2.716678 = chronological |
| CSP | satisfied; 16 nodes, 4 backtracks, 65 pruned; independent validation: valid |
| Expert rules fired | R1, R2, R3, R4, R5, R6, R6b, R8, R9, R10 (+G1–G3); backward goal proved |
| Subtitle cues | 18 |
| Transitions | 5 × fadeblack 0.8 s (R6), 2 × dissolve 0.8 s (R6b) |
| Time | analysis 19.1 s, planning 0.04 s, render 50.8 s (1 CPU core) |
| Output verification | 9/9: exists, readable, MP4, H.264, yuv420p, 1080×1920, duration, audio, full decode with 0 errors |
Observations: planning is negligible next to analysis and rendering; A\* is not always better than chronological order — when candidate scenes are already temporally smooth the search confirms it; frame inspection of the output (`docs/demo/demo_frames.png`) shows 9:16 reframing with burned-in captions inside the safe area.

## 23. Limitations
Whisper could not be executed in the build sandbox (no model download) — integration is tested with stubs, a live run is not demonstrated; the VAD option is therefore also untested against a real model. The demo is synthetic; "speech activity" is audio energy. No Remotion, no YOLO. No undo/redo. Exact A\* ≤ 9 candidates. Importance weights are unvalidated heuristics. Gujarati: a Noto Sans Gujarati font is bundled and Gujarati + English captions were rendered and inspected visually, but accuracy of Whisper for Gujarati (small models are weak) is untested. Single user, no authentication. The browser E2E script is not part of the pytest run.

## 24. Future Scope
Learn scoring weights from user feedback; vision-language scene descriptions; speaker/face tracking for reframing (YOLO / face detection); Remotion captions; word-level karaoke from Whisper on real footage; multi-track timeline editing with manual overrides and undo; GPU encoders; user accounts and a task queue.

## 25. Conclusion
The project delivers a working, locally runnable system in which classical AI techniques each make a real, inspectable contribution to an end-to-end task: heuristic scoring selects content, A\* sequences it, a CSP guarantees format and duration, a rule base chooses processing steps, and an agent loop explains and verifies everything. Limits are stated openly above.

## 26. References
1. Russell, S., Norvig, P. *Artificial Intelligence: A Modern Approach*, 4th ed. Pearson, 2020.
2. Hart, P.E., Nilsson, N.J., Raphael, B. "A Formal Basis for the Heuristic Determination of Minimum Cost Paths." *IEEE Trans. Systems Science and Cybernetics* 4(2):100–107, 1968.
3. Prim, R.C. "Shortest Connection Networks and Some Generalizations." *Bell System Technical Journal* 36(6):1389–1401, 1957.
4. Haralick, R.M., Elliott, G.L. "Increasing Tree Search Efficiency for Constraint Satisfaction Problems." *Artificial Intelligence* 14(3):263–313, 1980.
5. Salton, G., Buckley, C. "Term-weighting Approaches in Automatic Text Retrieval." *Information Processing & Management* 24(5):513–523, 1988.
6. Bhattacharyya, A. "On a Measure of Divergence between Two Statistical Populations." *Bull. Calcutta Math. Soc.* 35:99–109, 1943.
7. Radford, A. et al. "Robust Speech Recognition via Large-Scale Weak Supervision." arXiv:2212.04356, 2022.
8. Bradski, G. "The OpenCV Library." *Dr. Dobb's Journal*, 2000. 9. PySceneDetect documentation (scenedetect.com). 10. FFmpeg documentation (ffmpeg.org). 11. faster-whisper (github.com/SYSTRAN/faster-whisper). 12. EBU R 128, *Loudness normalisation and permitted maximum level of audio signals*, 2014.
