import itertools
import numpy as np
import pytest
from app.algorithms.astar import astar_sequence, beam_sequence, path_cost, sequence_scenes
from app.algorithms.backtracking import solve
from app.algorithms.backward_chaining import prove, unmet
from app.algorithms.csp import CSP, Constraint, build_editing_csp, diagnose_failure, validate_plan
from app.algorithms.expert_system import default_rules
from app.algorithms.forward_chaining import forward_chain
from app.algorithms.heuristic import mst_weight, undirected_lower


def rand_cost(n, seed):
    C = np.random.default_rng(seed).random((n, n)); np.fill_diagonal(C, 0); return C


def brute(C, n):
    return min(path_cost(list(p), C) for p in itertools.permutations(range(n)))


@pytest.mark.parametrize("n,seed", [(2, 1), (3, 2), (4, 3), (5, 4), (6, 5), (7, 6)])
def test_astar_matches_bruteforce_optimum(n, seed):
    C = rand_cost(n, seed)
    r = astar_sequence(C)
    assert sorted(r.order) == list(range(n))
    assert r.optimal and r.algorithm in ("astar", "trivial")
    assert r.cost == pytest.approx(brute(C, n), abs=1e-9)
    assert r.cost == pytest.approx(path_cost(r.order, C), abs=1e-9)


def test_astar_fixed_first_and_stats():
    C = rand_cost(5, 9)
    r = astar_sequence(C, fixed_first=2)
    assert r.order[0] == 2 and r.expanded > 0 and r.generated >= r.expanded and r.explored_states > 0 and r.seconds >= 0 and len(r.trace) > 0
    assert min(path_cost([2, *p], C) for p in itertools.permutations([0, 1, 3, 4])) == pytest.approx(r.cost)


@pytest.mark.parametrize("seed", range(5))
def test_heuristic_is_admissible_and_goal_is_zero(seed):
    n = 6
    C = rand_cost(n, 100 + seed)
    w = undirected_lower(C)
    rng = np.random.default_rng(seed)
    for _ in range(20):
        cur = int(rng.integers(n))
        rem = [i for i in range(n) if i != cur and rng.random() < 0.6]
        h = mst_weight([cur] + rem, w)
        true_best = min((path_cost([cur, *p], C) for p in itertools.permutations(rem)), default=0.0)
        assert h <= true_best + 1e-9, "heuristic overestimates -> inadmissible"
    assert mst_weight([3], w) == 0.0


def test_mst_weight_known_graph():
    w = np.array([[0, 1, 4], [1, 0, 2], [4, 2, 0]], float)
    assert mst_weight([0, 1, 2], w) == 3.0


def test_beam_fallback_is_valid_but_flagged_not_optimal():
    C = rand_cost(12, 7)
    out = sequence_scenes(C, list(range(12)), max_exact=9)
    assert out["algorithm"] == "beam" and out["optimal"] is False and "not guaranteed optimal" in out["note"]
    assert sorted(out["order"]) == list(range(12))


def test_chronological_comparison_and_improvement():
    C = rand_cost(6, 11)
    out = sequence_scenes(C, [5, 4, 3, 2, 1, 0])
    assert out["chronological_order"] == [5, 4, 3, 2, 1, 0]
    assert out["cost"] <= out["chronological_cost"] + 1e-12 and out["improvement_vs_chronological"] >= -1e-12


def test_astar_trivial_cases():
    assert astar_sequence(np.zeros((0, 0))).order == []
    assert astar_sequence(np.zeros((1, 1))).order == [0]


# ---------------- CSP / backtracking -----------------
CANDS = [{"scene_id": i, "eff_duration": d, "importance": imp} for i, (d, imp) in enumerate([(8, 80), (6, 60), (10, 90), (4, 30), (7, 50)])]
CFG = dict(target_duration=30, tolerance=1.0, min_scene_len=2.0, aspect_ratio="9:16", resolution="1080x1920", transition_style="smooth")


def test_csp_solution_satisfies_all_constraints():
    csp, _ = build_editing_csp(CANDS, CFG)
    r = solve(csp)
    assert r.solution is not None
    a = r.solution
    kept = [a[f"dur_{c['scene_id']}"] for c in CANDS if a[f"dur_{c['scene_id']}"] > 0]
    total = sum(kept) - (len(kept) - 1) * a["trans"]
    assert abs(total - 30) <= 1.0 + 1e-9
    assert all(k >= 2.0 for k in kept)
    assert a["resolution"] == "1080x1920" and a["aspect"] == "9:16"
    assert a["sub_pos"] in ("top", "center", "lower")   # 'bottom' is outside the 9:16 safe area
    for c in csp.constraints:
        assert c.check(a), c.name


def test_csp_infeasible_reports_constraints_and_suggestions():
    cfg = {**CFG, "target_duration": 120}
    csp, _ = build_editing_csp(CANDS, cfg)
    r = solve(csp)
    assert r.solution is None and r.failed_constraints
    d = diagnose_failure(CANDS, cfg)
    assert d["available_seconds"] == 35 and any("lower the target" in s for s in d["suggestions"])


def test_backtracking_actually_backtracks_on_map_colouring():
    regions = ["WA", "NT", "SA", "Q", "NSW", "V", "T"]
    adj = [("WA", "NT"), ("WA", "SA"), ("NT", "SA"), ("NT", "Q"), ("SA", "Q"), ("SA", "NSW"), ("SA", "V"), ("Q", "NSW"), ("NSW", "V")]
    csp = CSP({r: ["red", "green", "blue"] for r in regions},
              [Constraint(f"{a}!={b}", (a, b), (lambda x, y=None, a=a, b=b: x[a] != x[b])) for a, b in adj])
    r = solve(csp)
    assert r.solution and all(r.solution[a] != r.solution[b] for a, b in adj)
    # pigeonhole: 4-clique with 3 colours is unsatisfiable -> must backtrack and fail
    cl = ["a", "b", "c", "d"]
    csp2 = CSP({v: [1, 2, 3] for v in cl}, [Constraint(f"{x}!={y}", (x, y), (lambda s, x=x, y=y: s[x] != s[y])) for x, y in itertools.combinations(cl, 2)])
    r2 = solve(csp2)
    assert r2.solution is None and r2.backtracks > 0


def test_mrv_and_value_ordering_prefers_important_scenes():
    csp, info = build_editing_csp(CANDS, CFG)
    r = solve(csp)
    assert r.trace[0]["var"] in ("aspect", "resolution")   # singleton domains first (MRV)
    # most important scene (id 2, importance 90) should get a larger share than the least important (id 3)
    assert r.solution["dur_2"] >= r.solution["dur_3"]


def _plan(**over):
    p = {"config": {**CFG, "duration_tolerance": 1.0, "min_scene_len": 2.0, "target_duration": 10, "tolerance": 1.0},
         "source": {"duration": 20.0}, "output": {"width": 1080, "height": 1920, "duration": 10.0},
         "clips": [{"scene_id": 0, "duration": 5.0, "segments": [{"start": 0.0, "end": 5.0}], "transition_in": {"duration": 0.0}},
                   {"scene_id": 1, "duration": 5.0, "segments": [{"start": 6.0, "end": 11.0}], "transition_in": {"duration": 0.0}}],
         "subtitles": {"enabled": True, "position": "lower"}, "subtitle_cues": [{"start": 0.5, "end": 2.0, "text": "x"}], "audio_duration": 10.0}
    p.update(over)
    return p


def test_validate_plan_accepts_good_plan():
    assert validate_plan(_plan())["status"] == "valid"


@pytest.mark.parametrize("mutate,expect", [
    (lambda p: p["clips"][0]["segments"].__setitem__(0, {"start": -1.0, "end": 4.0}), "valid_timestamps"),
    (lambda p: p["clips"][0]["segments"].__setitem__(0, {"start": 5.0, "end": 5.0}), "start_before_end"),
    (lambda p: p["clips"][1]["segments"].__setitem__(0, {"start": 18.0, "end": 23.0}), "within_source_bounds"),
    (lambda p: p["output"].__setitem__("duration", 25.0), "target_duration"),
    (lambda p: p["output"].update(width=1000, height=1000), "export_dimensions_match_aspect"),
    (lambda p: p["subtitles"].__setitem__("position", "bottom"), "subtitle_in_safe_area"),
    (lambda p: p.__setitem__("audio_duration", 8.0), "audio_video_sync"),
    (lambda p: p["clips"][1].__setitem__("scene_id", 0), "no_unintended_overlap"),
    (lambda p: p["subtitle_cues"].append({"start": 9.0, "end": 30.0, "text": "late"}), "subtitle_timestamps"),
    (lambda p: p["clips"][0].__setitem__("duration", 1.0), "min_scene_duration"),
])
def test_validate_plan_catches_violations(mutate, expect):
    p = _plan(); mutate(p)
    r = validate_plan(p)
    assert r["status"] == "invalid" and expect in {v["constraint"] for v in r["violations"]}


# ---------------- Expert system -----------------
BASE = dict(aspect_ratio="9:16", target_duration=30, out_width=1080, out_height=1920, source_wider_than_target=True,
            subtitles_enabled=True, has_transcript=True, music_enabled=True, normalize_audio=True)


def test_forward_chaining_fires_and_chains_to_fixed_point():
    wm, log = forward_chain(default_rules(), BASE, "global")
    fired = {r.rule_id for r in log if r.fired}
    assert {"R4", "R5", "R7", "R10"} <= fired
    assert {"R8", "R9"} <= fired, "derived fact reframe_scheduled (from R4) must enable R8/R9"
    rec = next(r for r in log if r.rule_id == "R5")
    assert rec.facts_evaluated == {"subtitles_enabled": True, "has_transcript": True} and "IF" in rec.condition


def test_forward_chaining_does_not_fire_when_premises_fail():
    wm, log = forward_chain(default_rules(), {**BASE, "aspect_ratio": "16:9", "has_transcript": False, "music_enabled": False}, "global")
    fired = {r.rule_id for r in log if r.fired}
    assert "R4" not in fired and "R8" not in fired and "R5" not in fired and "R5b" in fired and "R7" not in fired


def test_scene_and_transition_rules():
    rs = default_rules()
    wm, _ = forward_chain(rs, dict(remove_silence=True, silence_duration=2.0, silence_threshold=0.5, speech_relevance_norm=0.9, high_relevance=0.7,
                                  scene_duration=1.0, min_scene_len=2.0, importance=10, low_importance=35), "scene")
    assert wm["trim_silence"] and wm["priority_retain"] and wm["exclude_candidate"]
    wm2, _ = forward_chain(rs, dict(visual_discontinuity=0.5, continuity_threshold=0.25, transitions_enabled=True), "transition")
    assert wm2["transition_needed"]
    wm3, _ = forward_chain(rs, dict(visual_discontinuity=0.1, continuity_threshold=0.25, transitions_enabled=True), "transition")
    assert "transition_needed" not in wm3 and wm3["transition_soft"]   # R6b: continuous scenes get a soft dissolve


def test_backward_chaining_proves_goal_via_subgoals():
    tree = prove("vertical_reel_ready", default_rules(), dict(BASE))   # base facts only: sub-goals proven recursively
    assert tree["proved"] and tree["via"].startswith("G1")
    sub = {c["goal"] for c in tree["children"]}
    assert "reframe_scheduled" in sub and "resolution_vertical" in sub


def test_backward_chaining_recognises_already_derived_fact():
    wm, _ = forward_chain(default_rules(), BASE, "global")
    tree = prove("vertical_reel_ready", default_rules(), {**BASE, **wm})
    assert tree["proved"] and tree["via"] == "fact"


def test_backward_chaining_explains_failure():
    facts = {**BASE, "aspect_ratio": "16:9", "out_width": 1920, "out_height": 1080, "target_duration": 300}
    tree = prove("vertical_reel_ready", default_rules(), facts)
    assert not tree["proved"]
    u = unmet(tree)
    assert any("aspect_ratio" in x for x in u) or any("target_duration" in x for x in u)
