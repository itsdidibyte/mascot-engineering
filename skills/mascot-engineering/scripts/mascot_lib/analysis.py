"""Profile comparisons shared by consistency.py and compare.py."""
from __future__ import annotations

import numpy as np

from . import silhouette


def widths(prof_stations, mode: str = "envelope", seed_h: float = 0.0):
    """Arrays (z, left, right, width) from profile stations. NaN where empty."""
    z = np.array([s["z"] for s in prof_stations], dtype=float)
    if mode == "envelope":
        runs = [silhouette.envelope(s["runs"]) for s in prof_stations]
    else:
        runs = silhouette.main_run_profile(prof_stations, seed_h)
    left = np.array([r[0] if r else np.nan for r in runs])
    right = np.array([r[1] if r else np.nan for r in runs])
    return z, left, right, right - left


def bands(z: np.ndarray, err: np.ndarray, tol: float, min_len: int = 2):
    """Contiguous runs where |err| > tol. NaN = not comparable (callers encode one-sided gaps as numbers)."""
    bad = np.abs(np.nan_to_num(err, nan=0.0)) > tol
    out = []
    i = 0
    while i < len(z):
        if bad[i]:
            j = i
            while j + 1 < len(z) and bad[j + 1]:
                j += 1
            if j - i + 1 >= min_len:
                seg = err[i:j + 1]
                finite = seg[np.isfinite(seg)]
                worst = float(finite[np.argmax(np.abs(finite))]) if len(finite) else float("nan")
                out.append({"z_from": round(float(z[i]), 3), "z_to": round(float(z[j]), 3), "worst": round(worst, 4) if np.isfinite(worst) else None})
            i = j + 1
        else:
            i += 1
    return out


def region_name(zf: float, height: float = 1.0) -> str:
    t = zf / height
    if t < 0.15:
        return "feet/base"
    if t < 0.45:
        return "lower body"
    if t < 0.65:
        return "upper body/neck"
    if t < 0.9:
        return "head"
    return "top of head/ears"


def match_extrema(a: list[dict], b: list[dict], tol: float):
    """Pair same-kind extrema of two views by nearest height."""
    pairs = []
    used = set()
    for e in a:
        cands = [(abs(f["z"] - e["z"]), k) for k, f in enumerate(b) if f["kind"] == e["kind"] and k not in used]
        if not cands:
            pairs.append({"kind": e["kind"], "z_a": e["z"], "z_b": None, "dz": None, "status": "UNMATCHED"})
            continue
        dz, k = min(cands)
        if dz > 0.15:
            pairs.append({"kind": e["kind"], "z_a": e["z"], "z_b": None, "dz": None, "status": "UNMATCHED"})
            continue
        used.add(k)
        pairs.append({"kind": e["kind"], "z_a": e["z"], "z_b": b[k]["z"], "dz": round(b[k]["z"] - e["z"], 4),
                      "status": "CONSISTENT" if dz <= tol else "CHECK"})
    return pairs
