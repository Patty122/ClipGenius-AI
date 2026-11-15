# FAI Viva — Questions and Answers

**1. Is ClipGenius a goal-based or utility-based agent?** Both. Goal-based: it plans toward a goal state (an edit meeting format/duration). Utility-based: among goal-satisfying edits it prefers higher total scene importance and lower transition cost, i.e. it ranks outcomes by a numeric utility.

**2. Give the PEAS description.** Performance: content preserved, duration accuracy, continuity, subtitle accuracy, audio quality, constraint satisfaction. Environment: video, audio, metadata, instruction, configuration. Actuators: trim, select, sequence, subtitle, audio-process, render. Sensors: frames, audio signal, transcript, scene detector, metadata.

**3. Is the environment fully observable? Deterministic?** Observable after the perceive phase (the whole file is available), static during planning, deterministic for a given input and configuration (same plan every time); it is single-agent and episodic per project. Perception quality (e.g. ASR) is imperfect, which is why missing/uncertain features are reported.

**4. Define the A\* state, actions, cost, heuristic.** State = (current scene, visited set). Action = move to an unvisited scene. g = Σ transition costs (visual, loudness, semantic, temporal). h = MST weight over {current} ∪ unvisited. Goal = all candidates visited.

**5. Why is the heuristic admissible?** Any completion is a Hamiltonian path = a spanning tree of the remaining nodes plus *current*. Using w(i,j) = min(c(i,j), c(j,i)) every path edge costs ≥ w, so path cost ≥ MST weight ≥ h. h never overestimates. (Tested against brute force.)

**6. Is it consistent?** Not proven; we do not rely on it: we keep the best g per state and re-open states when a cheaper path is found, which preserves optimality with a merely admissible heuristic.

**7. When is A\* not optimal here?** Above 9 candidates (n·2ⁿ states) we switch to beam search and flag the result as not guaranteed optimal; also if the 200 000-expansion cap is reached.

**8. Complexity of A\* here?** States ≤ n·2ⁿ; each has ≤ n successors; memoised MST O(n²) → O(n³ 2ⁿ) time, O(n 2ⁿ) space — fine for n ≤ 9.

**9. Why did A\* give the same order as chronological in your demo?** The temporal term of the cost penalises backward jumps, and the selected scenes were already visually smooth in order, so chronological *is* the optimum. We report it rather than force a difference; the tests show A\* equals the brute-force optimum, and chronological is only a baseline.

**10. Formulate the CSP.** Variables: aspect, resolution, subtitle position, transition duration, kept duration per scene. Domains: profiles, positions, {0.3,0.5,0.8}, {0} ∪ {min_len…usable length step 0.5}. Constraints: total duration within tolerance, min scene length, within source, ≥ 1 scene, dimensions match aspect, subtitles in safe area, transition ≤ half clip.

**11. Which CSP heuristics do you use?** MRV variable ordering (ties → importance), value ordering by closeness to the importance-proportional duration share, forward checking. They cut the demo search to 9 nodes with 0 backtracks.

**12. Why a second, independent validator?** Defence in depth: the solver and the final plan can differ (e.g. segment rounding, hard-cut reconciliation), and plans can be re-validated later. Rendering refuses any plan the validator rejects.

**13. Forward vs backward chaining?** Forward is data-driven: start from facts, fire all applicable rules to a fixed point (R4 ⇒ reframe_scheduled ⇒ R8/R9). Backward is goal-driven: prove `vertical_reel_ready` by proving the premises of G1 recursively. We use forward chaining to *decide* the edit and backward chaining to *verify/explain* a goal.

**14. How is explainability achieved?** Per-feature score contributions, A\* trace, CSP constraint/failure counts, rule firing records with facts, and a persisted agent decision log.

**15. What if a feature is missing (e.g. no transcript)?** Excluded from the weighted sum and the remaining weights are renormalised; the score explanation lists it as missing. It is never treated as 0 or as perfect.

**16. Which parts are yours and which are third-party?** Own: scoring, A\*, MST heuristic, CSP/backtracking, expert system and chaining, planner, prompt parser, render graph, subtitle mapping. Libraries: FFmpeg, OpenCV, PySceneDetect, scikit-learn (TF-IDF), FastAPI/SQLAlchemy/Pydantic. Pretrained model: Whisper (via faster-whisper). Optional: an LLM for JSON prompt parsing.

**17. Is an LLM required?** No. A deterministic regex parser covers the supported commands; an LLM can only return JSON that Pydantic validates; nothing generated is ever executed.

**18. How do you avoid cutting speech when removing silence?** Kept intervals = detected audio activity ∪ transcript segments, padded 0.15 s each side. Quiet speech in the transcript is kept even if below the dB threshold (tested).

**19. What were the engineering failures you hit?** A render was OOM-killed because every segment read from one input via `trim` (FFmpeg buffered the source); fixed with per-segment seeked inputs. A validator bug (`tolerance` vs `duration_tolerance`) was caught by the API tests. Realistic-input testing then found three more: single-shot videos split too coarsely, *smooth transitions* degrading to hard cuts on jump cuts (added rule R6b), and Gujarati font warnings being discarded.

**20. What does not work yet?** Whisper wasn't executable in the build environment (tested with stubs); Remotion/YOLO/undo not implemented; weights are unvalidated heuristics; Gujarati ASR quality with small Whisper models is untested. These are listed in the README and report.
