"""Video Perception Agent: real visual features from decoded frames (OpenCV).

Per scene: colour-histogram signatures (start/end/mean), motion energy, a motion-centroid `focus_x` used for
reframing, mean luma and a thumbnail. Nothing here is a learned description -- only measured pixels.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

SAMPLE_FPS = 4.0
SMALL = (96, 54)


def _hist(frame_small: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame_small, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1, 2], None, [8, 4, 4], [0, 180, 0, 256, 0, 256]).flatten()
    s = h.sum()
    return h / s if s > 0 else h


def analyze_scene_visuals(video_path: Path, scenes: list[dict], thumb_dir: Path, fps_hint: float = 25.0) -> list[dict]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("OpenCV could not open the video")
    fps = cap.get(cv2.CAP_PROP_FPS) or fps_hint or 25.0
    thumb_dir.mkdir(parents=True, exist_ok=True)

    needed: dict[int, int] = {}  # frame index -> scene_id
    mid_idx: dict[int, int] = {}
    for sc in scenes:
        a, b = sc["start"], sc["end"]
        n = max(2, int((b - a) * SAMPLE_FPS))
        for k in range(n):
            t = a + (b - a) * (k + 0.5) / n
            needed[int(t * fps)] = sc["scene_id"]
        mid_idx[sc["scene_id"]] = int(((a + b) / 2) * fps)
        needed[mid_idx[sc["scene_id"]]] = sc["scene_id"]
    last_needed = max(needed)
    samples: dict[int, list] = {sc["scene_id"]: [] for sc in scenes}
    thumbs: dict[int, np.ndarray] = {}
    mid_to_scene = {v: k for k, v in mid_idx.items()}

    idx = 0
    while idx <= last_needed:
        if not cap.grab():
            break
        if idx in needed:
            ok, frame = cap.retrieve()
            if ok:
                small = cv2.resize(frame, SMALL, interpolation=cv2.INTER_AREA)
                samples[needed[idx]].append((idx, _hist(small), cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)))
                if idx in mid_to_scene:
                    thumbs[mid_to_scene[idx]] = frame
        idx += 1
    cap.release()

    out = []
    for sc in scenes:
        sid = sc["scene_id"]
        sm = sorted(samples[sid], key=lambda x: x[0])
        if not sm:
            out.append({"scene_id": sid, "motion": None, "focus_x": 0.5, "brightness": None, "sig_start": None, "sig_end": None,
                        "sig_mean": None, "thumbnail": None})
            continue
        diffs = [np.abs(sm[i][2] - sm[i - 1][2]) for i in range(1, len(sm))]
        motion = float(np.mean([d.mean() / 255.0 for d in diffs])) if diffs else 0.0
        focus = 0.5
        if diffs:
            col_energy = np.mean(diffs, axis=0).sum(axis=0)
            if col_energy.sum() > 1e-6 and motion > 0.004:
                focus = float((col_energy * np.arange(len(col_energy))).sum() / col_energy.sum() / (len(col_energy) - 1))
        thumb_name = None
        fr = thumbs.get(sid)
        if fr is not None:
            h, w = fr.shape[:2]
            tw = 320
            fr = cv2.resize(fr, (tw, max(2, int(h * tw / w))), interpolation=cv2.INTER_AREA)
            thumb_name = f"scene_{sid}.jpg"
            cv2.imwrite(str(thumb_dir / thumb_name), fr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        out.append({"scene_id": sid, "motion": round(motion, 5), "focus_x": round(min(0.95, max(0.05, focus)), 4),
                    "brightness": round(float(np.mean([x[2].mean() for x in sm])) / 255.0, 4),
                    "sig_start": sm[0][1].round(6).tolist(), "sig_end": sm[-1][1].round(6).tolist(),
                    "sig_mean": np.mean([x[1] for x in sm], axis=0).round(6).tolist(), "thumbnail": thumb_name})
    return out


def hist_distance(a: list[float] | None, b: list[float] | None) -> float | None:
    """Bhattacharyya distance in [0,1] between normalised histograms (None when a signature is missing)."""
    if a is None or b is None:
        return None
    a_, b_ = np.asarray(a), np.asarray(b)
    bc = float(np.sum(np.sqrt(a_ * b_)))
    return float(np.sqrt(max(0.0, 1.0 - bc)))
