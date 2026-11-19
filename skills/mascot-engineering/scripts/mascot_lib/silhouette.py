"""Silhouette extraction, canonical normalisation and width/depth profiles.

This is the deterministic replacement for "Claude looks at the picture and
guesses proportions". Every number it produces traces back to pixels.
Requires numpy, Pillow, scipy.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from .views import Canvas


# --------------------------------------------------------------------------- mask extraction

def extract_mask(img: Image.Image, tolerance: int = 32, min_part_fraction: float = 0.02,
                 exclude_boxes=None, force_method: str | None = None) -> tuple[np.ndarray, dict]:
    """Foreground mask of a single character image. Returns (bool HxW, report dict).

    Method: real alpha channel when present and meaningful; otherwise the
    background colour is the median border colour and background = pixels
    within `tolerance` of it that are CONNECTED to the image border (so a
    white belly on a white background stays foreground if it is outlined).
    Holes are filled, specks below `min_part_fraction` of the largest part dropped.
    """
    report: dict = {"tolerance": tolerance}
    rgba = np.array(img.convert("RGBA"))
    alpha = rgba[..., 3]
    method = force_method
    if method is None:
        transparent = (alpha < 128).mean()
        method = "alpha" if 0.02 < transparent < 0.98 else "border_color"
    report["method"] = method
    if method == "alpha":
        fg = alpha >= 128
    else:
        rgb = rgba[..., :3].astype(np.int16)
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
        bg = np.median(border, axis=0)
        report["background_rgb"] = [int(v) for v in bg]
        near = np.abs(rgb - bg).max(axis=2) <= tolerance
        lab, _ = ndimage.label(near)
        edge_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        edge_labels = edge_labels[edge_labels > 0]
        background = np.isin(lab, edge_labels)
        fg = ~background
    if exclude_boxes:
        for x0, y0, x1, y1 in exclude_boxes:
            fg[int(y0):int(y1), int(x0):int(x1)] = False
        report["excluded_boxes_px"] = [list(map(int, b)) for b in exclude_boxes]
    fg = ndimage.binary_fill_holes(fg)
    lab, n = ndimage.label(fg)
    if n == 0:
        raise ValueError("No foreground found: check background tolerance or alpha channel")
    sizes = ndimage.sum(fg, lab, index=np.arange(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= min_part_fraction * sizes.max()]
    dropped = [int(s) for i, s in enumerate(sizes) if (i + 1) not in keep]
    fg = np.isin(lab, keep)
    report["parts_kept"] = len(keep)
    report["specks_dropped_px"] = dropped
    h, w = fg.shape
    touches = [name for name, edge in (("top", fg[0]), ("bottom", fg[-1]), ("left", fg[:, 0]), ("right", fg[:, -1])) if edge.any()]
    report["touches_border"] = touches
    report["image_size_px"] = [w, h]
    return fg, report


def bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    """(x0, y0, x1, y1) with x1/y1 exclusive."""
    rows = np.nonzero(mask.any(axis=1))[0]
    cols = np.nonzero(mask.any(axis=0))[0]
    if len(rows) == 0:
        raise ValueError("Empty mask")
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


# --------------------------------------------------------------------------- normalisation

def normalize_to_canvas(mask: np.ndarray, rgb_img: Image.Image, canvas: Canvas, height: float = 1.0,
                        anchor_col: float | None = None):
    """Scale/translate a source view so ground->z=0, top->z=height, anchor column->h=0.

    Returns (canvas_mask bool, canvas_rgba uint8, normalisation record).
    """
    x0, y0, x1, y1 = bbox(mask)
    pix_h = y1 - y0
    s = canvas.px_per_unit * height / pix_h          # canvas px per source px
    anchor = (x0 + x1) / 2.0 if anchor_col is None else float(anchor_col)
    col0, _ = canvas.to_pixel(0.0, 0.0)
    _, row0 = canvas.to_pixel(0.0, 0.0)
    col0, row0 = float(col0), float(row0)
    # inverse affine: source = (out - offset)/s + anchor
    data = (1 / s, 0, anchor - col0 / s, 0, 1 / s, y1 - row0 / s)
    n = canvas.resolution_px
    m_img = Image.fromarray((mask * 255).astype(np.uint8))
    m_out = np.array(m_img.transform((n, n), Image.AFFINE, data, resample=Image.BILINEAR)) >= 128
    rgba = rgb_img.convert("RGBA").transform((n, n), Image.AFFINE, data, resample=Image.BICUBIC,
                                             fillcolor=(255, 255, 255, 0))
    record = {
        "bbox_px": [x0, y0, x1, y1],
        "source_height_px": pix_h,
        "scale_canvas_px_per_source_px": s,
        "source_px_per_unit": pix_h / height,
        "anchor_rule": "bbox_center" if anchor_col is None else "explicit_column",
        "anchor_col_px": anchor,
        "character_height_units": height,
    }
    return m_out, np.array(rgba), record


# --------------------------------------------------------------------------- profiles

def row_runs(row: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous True runs as (start, end_exclusive) column indices."""
    padded = np.concatenate([[False], row, [False]]).astype(np.int8)
    d = np.diff(padded)
    starts = np.nonzero(d == 1)[0]
    ends = np.nonzero(d == -1)[0]
    return list(zip(starts.tolist(), ends.tolist()))


def profile(mask: np.ndarray, canvas: Canvas, stations) -> list[dict]:
    """For each station z: runs as [h_left, h_right] in world units (canvas horizontal)."""
    out = []
    n = mask.shape[0]
    for z in stations:
        r = canvas.row_of_z(z)
        runs = []
        if 0 <= r < n:
            for c0, c1 in row_runs(mask[r]):
                h0, _ = canvas.to_world(c0, 0)
                h1, _ = canvas.to_world(c1, 0)
                runs.append([round(float(h0), 5), round(float(h1), 5)])
        out.append({"z": round(float(z), 5), "runs": runs})
    return out


def pick_run(runs, seed_h: float):
    if not runs:
        return None
    for r in runs:
        if r[0] <= seed_h <= r[1]:
            return r
    return min(runs, key=lambda r: min(abs(r[0] - seed_h), abs(r[1] - seed_h)))


def envelope(runs):
    if not runs:
        return None
    return [min(r[0] for r in runs), max(r[1] for r in runs)]


def main_run_profile(prof: list[dict], seed_h: float = 0.0, track: bool = True):
    """Per station the run containing the seed; with track=True the seed follows the run centre.

    Tracking starts at the station with the widest seed-containing run (the torso) and walks
    up and down, so a body that leans or a head offset from the hips is still followed.
    """
    n = len(prof)
    chosen = [None] * n
    widths = []
    for p in prof:
        r = pick_run(p["runs"], seed_h)
        widths.append((r[1] - r[0]) if (r is not None and r[0] <= seed_h <= r[1]) else 0.0)
    if not any(widths):
        widths = [((r[1] - r[0]) if r else 0.0) for r in (pick_run(p["runs"], seed_h) for p in prof)]
    start = int(np.argmax(widths)) if any(widths) else 0
    chosen[start] = pick_run(prof[start]["runs"], seed_h)
    for rng in (range(start + 1, n), range(start - 1, -1, -1)):
        seed = seed_h
        prev = chosen[start]
        for i in rng:
            if track and prev is not None:
                seed = (prev[0] + prev[1]) / 2
            r = pick_run(prof[i]["runs"], seed)
            if r is not None and track and not (r[0] <= seed <= r[1]):
                # the tracked part ended here (top of head, gap between feet): do not jump to
                # a neighbouring part such as an ear or a single foot
                r = None
            chosen[i] = r
            if r is not None:
                prev = r
    return chosen


def smooth(x: np.ndarray, k: int = 5) -> np.ndarray:
    if k <= 1 or len(x) < k:
        return x
    pad = k // 2
    xp = np.pad(x, pad, mode="edge")
    return np.convolve(xp, np.ones(k) / k, mode="valid")


def extrema(z: np.ndarray, w: np.ndarray, prominence: float = 0.02):
    """Local minima ("necks/waists") and maxima ("bulges") of a width curve with simple prominence."""
    ws = smooth(np.asarray(w, dtype=float), 5)
    out = []
    for i in range(1, len(ws) - 1):
        if ws[i] <= 0:
            continue
        kind = None
        if ws[i] < ws[i - 1] and ws[i] <= ws[i + 1]:
            kind = "min"
        elif ws[i] > ws[i - 1] and ws[i] >= ws[i + 1]:
            kind = "max"
        if not kind:
            continue
        left = ws[:i]
        right = ws[i + 1:]
        if kind == "min":
            prom = min(left.max() if len(left) else 0, right.max() if len(right) else 0) - ws[i]
        else:
            lmin = left[left > 0].min() if (left > 0).any() else 0
            rmin = right[right > 0].min() if (right > 0).any() else 0
            prom = ws[i] - max(lmin, rmin)
        if prom >= prominence:
            out.append({"kind": kind, "z": round(float(z[i]), 4), "width": round(float(ws[i]), 4),
                        "prominence": round(float(prom), 4)})
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(bool)
    b = b.astype(bool)
    u = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / u) if u else 1.0
