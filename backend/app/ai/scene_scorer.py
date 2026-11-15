"""Scene Evaluation Agent: explainable, configurable heuristic importance scoring (0-100).

Features (all normalised to [0,1] across the scenes of the video before weighting):
  speech_relevance  - TF-IDF cosine between the scene text and the video's mean text vector (how central is it)
  speech_activity   - fraction of the scene with audio activity/transcribed speech
  visual_activity   - motion energy (min-max normalised)
  distinctiveness   - mean histogram distance to the other scenes (min-max normalised)
  topic_relevance   - TF-IDF cosine to the user's topic phrase (only if a topic was given)

Missing-feature policy ("renormalise"): an unavailable feature is EXCLUDED and the remaining weights are
rescaled to sum to 1. It is never treated as 0 or as a perfect 1, and the score reports which features were missing.
Weights are configurable defaults, not scientifically established constants.
"""
from __future__ import annotations
import numpy as np
from pydantic import BaseModel, Field, model_validator
from .video_perception import hist_distance

FEATURES = ["speech_relevance", "speech_activity", "visual_activity", "distinctiveness", "topic_relevance"]


class ScoringWeights(BaseModel):
    speech_relevance: float = Field(0.30, ge=0)
    speech_activity: float = Field(0.20, ge=0)
    visual_activity: float = Field(0.15, ge=0)
    distinctiveness: float = Field(0.15, ge=0)
    topic_relevance: float = Field(0.20, ge=0)

    @model_validator(mode="after")
    def _nonzero(self):
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("At least one weight must be positive")
        return self


def _minmax(vals: list[float | None]) -> list[float | None]:
    present = [v for v in vals if v is not None]
    if not present:
        return vals
    lo, hi = min(present), max(present)
    if hi - lo < 1e-9:
        return [None if v is None else 0.5 for v in vals]  # constant feature carries no ranking information
    return [None if v is None else (v - lo) / (hi - lo) for v in vals]


def _tfidf_cosines(texts: list[str], topic: str | None):
    """Returns (centrality list, topic list, tf-idf matrix) -- entries None if text is unavailable."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    n = len(texts)
    if not any(t.strip() for t in texts):
        return [None] * n, [None] * n if topic else [None] * n, None
    corpus = texts + ([topic] if topic else [])
    try:
        vec = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", lowercase=True)
        m = vec.fit_transform(corpus)
    except ValueError:
        return [None] * n, [None] * n, None
    sc = m[:n]
    mean_vec = np.asarray(sc.mean(axis=0))
    cent = cosine_similarity(sc, mean_vec).ravel()
    cent_l = [float(c) if texts[i].strip() else 0.0 for i, c in enumerate(cent)]
    topic_l = [None] * n
    if topic:
        tv = m[n]
        tcos = cosine_similarity(sc, tv).ravel()
        topic_l = [float(c) if texts[i].strip() else 0.0 for i, c in enumerate(tcos)]
    return cent_l, topic_l, sc


def score_scenes(scenes: list[dict], topic: str | None = None, weights: ScoringWeights | None = None) -> list[dict]:
    """Mutates and returns scenes with `features`, `importance`, `score_detail`."""
    w = weights or ScoringWeights()
    n = len(scenes)
    texts = [s.get("transcript", "") or "" for s in scenes]
    cent, topic_rel, _ = _tfidf_cosines(texts, topic)
    speech_act = [s.get("speech_density") for s in scenes]
    motion = [s.get("motion") for s in scenes]
    dist: list[float | None] = []
    for i, s in enumerate(scenes):
        ds = [hist_distance(s.get("sig_mean"), o.get("sig_mean")) for j, o in enumerate(scenes) if j != i]
        ds = [d for d in ds if d is not None]
        dist.append(float(np.mean(ds)) if ds and n > 1 else None)
    raw = {"speech_relevance": cent, "speech_activity": speech_act, "visual_activity": motion, "distinctiveness": dist,
           "topic_relevance": topic_rel if topic else [None] * n}
    norm = {k: _minmax(list(v)) for k, v in raw.items()}
    wd = w.model_dump()
    for i, s in enumerate(scenes):
        avail = {k: norm[k][i] for k in FEATURES if norm[k][i] is not None and wd[k] > 0}
        missing = [k for k in FEATURES if norm[k][i] is None]
        total_w = sum(wd[k] for k in avail)
        contrib = {k: (wd[k] / total_w) * v * 100 for k, v in avail.items()} if total_w > 0 else {}
        score = round(sum(contrib.values()), 2)
        reason = []
        for k, c in sorted(contrib.items(), key=lambda x: -x[1])[:3]:
            reason.append(f"{k.replace('_', ' ')} contributed {c:.1f} pts (normalised {avail[k]:.2f}, weight {wd[k] / total_w:.2f})")
        why = f"Score {score:.1f}/100. " + "; ".join(reason) + "."
        if missing:
            why += f" Unavailable features ({', '.join(missing)}) were excluded and the other weights renormalised."
        s["features"] = {k: {"raw": raw[k][i], "normalized": norm[k][i]} for k in FEATURES}
        s["importance"] = score
        s["score_detail"] = {"contributions": {k: round(v, 3) for k, v in contrib.items()}, "missing": missing,
                             "weights_used": {k: round(wd[k] / total_w, 4) for k in avail} if total_w else {}, "explanation": why}
    return scenes
