"""Transition cost model (path cost g) and the admissible MST heuristic (h) for scene sequencing."""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
from ..ai.video_perception import hist_distance


@dataclass
class CostWeights:
    """Configurable weights of the transition cost. Normalised so c(a,b) lies in [0,1]."""
    visual: float = 0.30
    audio: float = 0.20
    semantic: float = 0.20
    temporal: float = 0.30

    def normalised(self) -> "CostWeights":
        t = self.visual + self.audio + self.semantic + self.temporal
        if t <= 0:
            raise ValueError("cost weights must sum to > 0")
        return CostWeights(self.visual / t, self.audio / t, self.semantic / t, self.temporal / t)


@dataclass
class CostMatrix:
    cost: np.ndarray                       # directed cost[i][j] for transition i -> j, all >= 0
    components: dict = field(default_factory=dict)   # (i,j) -> {visual,audio,semantic,temporal}
    notes: list = field(default_factory=list)


def build_cost_matrix(scenes: list[dict], total_duration: float, weights: CostWeights | None = None,
                      semantic_sim: np.ndarray | None = None) -> CostMatrix:
    """c(a,b) = w_v*visual_discontinuity + w_a*audio_jump + w_s*semantic_inconsistency + w_t*temporal_jump.

    visual   : Bhattacharyya distance between a's last-frame and b's first-frame colour histograms
    audio    : |loudness_dB(a) - loudness_dB(b)| / 30 dB, clipped to [0,1]
    semantic : 1 - TF-IDF cosine(a,b)  (0 if no transcript is available -> reported in notes)
    temporal : forward gaps are cheap, backward jumps cost >= 0.5 (breaks narrative order)
    """
    w = (weights or CostWeights()).normalised()
    n = len(scenes)
    C = np.zeros((n, n))
    comps: dict = {}
    notes: list[str] = []
    if semantic_sim is None:
        notes.append("semantic term is 0 (no transcript available)")
    if any(s.get("sig_start") is None for s in scenes):
        notes.append("visual term is 0 for scenes lacking frame signatures")
    for i, a in enumerate(scenes):
        for j, b in enumerate(scenes):
            if i == j:
                continue
            v = hist_distance(a.get("sig_end"), b.get("sig_start")) or 0.0
            la, lb = a.get("loudness_db"), b.get("loudness_db")
            au = min(1.0, abs(la - lb) / 30.0) if la is not None and lb is not None else 0.0
            se = float(1.0 - semantic_sim[i][j]) if semantic_sim is not None else 0.0
            if b["start"] >= a["end"]:
                te = 0.5 * min(1.0, (b["start"] - a["end"]) / max(total_duration, 1e-6))
            else:
                te = 0.5 + 0.5 * min(1.0, (a["end"] - b["start"]) / max(total_duration, 1e-6))
            C[i][j] = w.visual * v + w.audio * au + w.semantic * se + w.temporal * te
            comps[(i, j)] = {"visual": round(v, 4), "audio": round(au, 4), "semantic": round(se, 4), "temporal": round(te, 4)}
    return CostMatrix(C, comps, notes)


def undirected_lower(cost: np.ndarray) -> np.ndarray:
    """w[i][j] = min(c[i][j], c[j][i]). Every directed edge of a path costs >= w, so MST on w lower-bounds any path."""
    return np.minimum(cost, cost.T)


def mst_weight(nodes: list[int], w: np.ndarray) -> float:
    """Prim's algorithm: weight of the minimum spanning tree over `nodes`.

    ADMISSIBILITY: a Hamiltonian path through `nodes` is itself a spanning tree, so its undirected-lower cost
    >= MST weight >= ... hence h(n) = MST({current} U remaining) never overestimates the true remaining cost.
    """
    k = len(nodes)
    if k <= 1:
        return 0.0
    in_tree = {nodes[0]}
    best = {v: w[nodes[0]][v] for v in nodes[1:]}
    total = 0.0
    while best:
        v = min(best, key=best.get)
        total += best.pop(v)
        in_tree.add(v)
        for u in best:
            if w[v][u] < best[u]:
                best[u] = w[v][u]
    return float(total)
