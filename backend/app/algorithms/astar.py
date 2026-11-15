"""A* search for scene sequencing -- implemented from scratch (heapq OPEN list, dict CLOSED/best-g table).

State  : (current scene, frozenset/bitmask of visited scenes)
Initial: virtual root; any scene may start (or a fixed first scene) with g = 0
Goal   : all candidate scenes visited
Action : move from current scene to an unvisited scene, cost c(current, next)
g(n)   : accumulated transition cost            h(n): MST lower bound over {current} U unvisited
f(n)   : g(n) + h(n)
Exact A* is only used up to `max_exact` scenes (state space n*2^n); beyond that a clearly-labelled beam search
fallback is used and the result is NOT claimed optimal.
"""
from __future__ import annotations
import heapq
import itertools
import time
from dataclasses import dataclass, field
import numpy as np
from .heuristic import mst_weight, undirected_lower


@dataclass
class SearchResult:
    order: list[int]
    cost: float
    algorithm: str                     # "astar" | "beam" | "chronological" | "trivial"
    optimal: bool
    expanded: int = 0
    generated: int = 0
    explored_states: int = 0
    seconds: float = 0.0
    trace: list = field(default_factory=list)   # visualisation data (first expansions)
    note: str = ""

    def to_dict(self) -> dict:
        return {k: (v if not isinstance(v, np.generic) else v.item()) for k, v in self.__dict__.items()}


def path_cost(order: list[int], cost: np.ndarray) -> float:
    return float(sum(cost[a][b] for a, b in zip(order, order[1:])))


def _h(cur: int, mask: int, n: int, w: np.ndarray, memo: dict) -> float:
    key = (cur, mask)
    if key not in memo:
        rem = [i for i in range(n) if not (mask >> i) & 1]
        memo[key] = mst_weight([cur] + rem, w) if rem else 0.0
    return memo[key]


def astar_sequence(cost: np.ndarray, fixed_first: int | None = None, max_expansions: int = 200_000,
                   trace_limit: int = 200) -> SearchResult:
    t0 = time.perf_counter()
    n = cost.shape[0]
    if n == 0:
        return SearchResult([], 0.0, "trivial", True)
    if n == 1:
        return SearchResult([0], 0.0, "trivial", True, explored_states=1)
    w = undirected_lower(cost)
    full = (1 << n) - 1
    memo: dict = {}
    counter = itertools.count()
    best_g: dict[tuple[int, int], float] = {}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    open_list: list = []
    generated = 0
    starts = [fixed_first] if fixed_first is not None else range(n)
    for i in starts:
        st = (i, 1 << i)
        best_g[st] = 0.0
        parent[st] = None
        heapq.heappush(open_list, (_h(i, 1 << i, n, w, memo), next(counter), 0.0, st))
        generated += 1
    expanded, trace = 0, []

    def rebuild(st):
        seq = []
        while st is not None:
            seq.append(st[0])
            st = parent[st]
        return seq[::-1]

    while open_list:
        f, _, g, st = heapq.heappop(open_list)
        if g > best_g.get(st, float("inf")) + 1e-12:
            continue  # stale entry (lazy deletion)
        cur, mask = st
        if mask == full:
            order = rebuild(st)
            return SearchResult(order, g, "astar", True, expanded, generated, len(best_g), time.perf_counter() - t0, trace,
                                "Exact A*: admissible MST heuristic, goal tested on expansion, re-opening allowed")
        expanded += 1
        if len(trace) < trace_limit:
            trace.append({"step": expanded, "path": rebuild(st), "g": round(g, 5), "h": round(f - g, 5), "f": round(f, 5)})
        if expanded > max_expansions:
            res = beam_sequence(cost, fixed_first=fixed_first)
            res.note = f"A* exceeded {max_expansions} expansions; fell back to beam search (not guaranteed optimal)"
            res.expanded += expanded
            return res
        for j in range(n):
            if (mask >> j) & 1:
                continue
            g2, m2 = g + float(cost[cur][j]), mask | (1 << j)
            st2 = (j, m2)
            if g2 < best_g.get(st2, float("inf")) - 1e-12:
                best_g[st2] = g2
                parent[st2] = st
                heapq.heappush(open_list, (g2 + _h(j, m2, n, w, memo), next(counter), g2, st2))
                generated += 1
    raise RuntimeError("A* exhausted the open list without reaching the goal")  # unreachable for complete graphs


def beam_sequence(cost: np.ndarray, beam_width: int = 64, fixed_first: int | None = None) -> SearchResult:
    """Beam search over the same state space ranked by f = g + h. Heuristic, NOT guaranteed optimal."""
    t0 = time.perf_counter()
    n = cost.shape[0]
    if n <= 1:
        return SearchResult(list(range(n)), 0.0, "trivial", True)
    w = undirected_lower(cost)
    memo: dict = {}
    starts = [fixed_first] if fixed_first is not None else range(n)
    beam = [(_h(i, 1 << i, n, w, memo), 0.0, [i], 1 << i) for i in starts]
    generated, expanded = len(beam), 0
    for _ in range(n - 1):
        cand = []
        for f, g, path, mask in beam:
            expanded += 1
            cur = path[-1]
            for j in range(n):
                if (mask >> j) & 1:
                    continue
                g2, m2 = g + float(cost[cur][j]), mask | (1 << j)
                cand.append((g2 + _h(j, m2, n, w, memo), g2, path + [j], m2))
                generated += 1
        cand.sort(key=lambda x: x[0])
        beam = cand[:beam_width]
    best = min(beam, key=lambda x: x[1])
    return SearchResult(best[2], best[1], "beam", False, expanded, generated, generated, time.perf_counter() - t0, [],
                        f"Beam search (width {beam_width}); not guaranteed optimal")


def sequence_scenes(cost: np.ndarray, starts: list[float], max_exact: int = 9, fixed_first: int | None = None) -> dict:
    """Driver: choose A* (exact) or beam fallback and compare with chronological order."""
    n = cost.shape[0]
    chrono = sorted(range(n), key=lambda i: starts[i])
    chrono_cost = path_cost(chrono, cost)
    res = astar_sequence(cost, fixed_first) if n <= max_exact else beam_sequence(cost, fixed_first=fixed_first)
    if n > max_exact:
        res.note = f"{n} candidates > exact limit {max_exact}: beam-search fallback (not guaranteed optimal)"
    d = res.to_dict()
    d["cost"] = round(res.cost, 6)
    d["seconds"] = round(res.seconds, 6)
    d.update({"chronological_order": chrono, "chronological_cost": round(chrono_cost, 6),
              "improvement_vs_chronological": round(round(chrono_cost, 6) - round(res.cost, 6), 6),
              "improvement_pct": round(100 * (chrono_cost - res.cost) / chrono_cost, 2) if chrono_cost > 1e-12 else 0.0,
              "cost_matrix": np.round(cost, 4).tolist()})
    return d
