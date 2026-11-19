#!/usr/bin/env python3
"""Held-out 3/4-view check: does the model also match a view it was NOT built from?

    python check_three_quarter.py WORKSPACE [--yaw-min 15 --yaw-max 75 --yaw-step 5]
        [--iou-min 0.93] [--tune-n COMPONENT_ID [--n-values 1.5,2,2.5,3,4,5] [--apply]]

Front and side silhouettes fix widths and depths but NOT the cross-section shape in
between (round vs boxy). A 3/4 view sees exactly that. For every measured view of kind
three_quarter_left / three_quarter_right this script:
  1. renders the spec at a sweep of orbit angles (the true angle of an AI 3/4 picture is
     unknown), aligns horizontally by bbox centre, and keeps the best-matching angle;
  2. reports IoU, per-height width differences and a diff image at that angle;
  3. with --tune-n, repeats the sweep for several cross-section exponents n of one
     elliptical_loft component and reports which n explains the 3/4 view best
     (--apply writes it, labelled `inferred` from this view).
Writes 05_validation/THREE_QUARTER.json/.md and <view>_34_diff.png.
Status: PASS if best IoU >= --iou-min, else CHECK (AI 3/4 views are often inaccurate:
the owner decides whether the model or the picture is wrong). Exit 0 always unless error.
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mascot_lib import analysis, drawing, raster, silhouette  # noqa: E402
from mascot_lib.views import THREE_QUARTER_KINDS, Canvas  # noqa: E402
from mascot_lib.workspace import load_spec, save_json  # noqa: E402


def align(ref: np.ndarray, ren: np.ndarray) -> tuple[np.ndarray, int]:
    """Shift `ren` horizontally so its bbox centre matches `ref`'s."""
    if not ren.any() or not ref.any():
        return ren, 0
    rc = np.nonzero(ref.any(axis=0))[0]
    mc = np.nonzero(ren.any(axis=0))[0]
    shift = int(round((rc[0] + rc[-1]) / 2 - (mc[0] + mc[-1]) / 2))
    out = np.zeros_like(ren)
    if shift >= 0:
        out[:, shift:] = ren[:, :ren.shape[1] - shift]
    else:
        out[:, :shift] = ren[:, -shift:]
    return out, shift


def sweep(spec, ref_small, canvas_small, yaws):
    best = (-1.0, None)
    scores = []
    for y in yaws:
        m, _ = raster.render_view(spec, f"yaw:{y}", canvas_small, shaded=False)
        m, _ = align(ref_small, m >= 128)
        s = silhouette.iou(ref_small, m)
        scores.append((float(y), round(s, 4)))
        if s > best[0]:
            best = (s, float(y))
    return best, scores


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--yaw-min", type=float, default=15)
    ap.add_argument("--yaw-max", type=float, default=75)
    ap.add_argument("--yaw-step", type=float, default=5)
    ap.add_argument("--iou-min", type=float, default=0.93)
    ap.add_argument("--tune-n", default=None, help="elliptical_loft component id whose exponent n to tune")
    ap.add_argument("--n-values", default="1.5,2,2.5,3,4,5")
    ap.add_argument("--apply", action="store_true", help="write the best n into the spec")
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    if not spec["components"]:
        print("ERROR: spec has no components", file=sys.stderr)
        return 2
    H = float(spec["scale"]["character_height"])
    canvas = Canvas.from_dict(spec.get("canvas"))
    small = Canvas(canvas.world_size, canvas.center_h, canvas.center_z, 384)
    out_dir = ws / "05_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    views = [v for v in spec["views"] if v["kind"] in THREE_QUARTER_KINDS and (ws / "02_views" / f"{v['id']}_mask.png").exists()]
    if not views:
        print("ERROR: no measured three_quarter_left/right view (register one with intake.py, then run silhouettes.py)", file=sys.stderr)
        return 2
    report = {"iou_min": a.iou_min, "views": []}
    md = ["# Held-out 3/4 view check", "",
          "The model was built from front/side/back only; this view tests the cross-section in between.", ""]
    target = None
    if a.tune_n:
        target = next((c for c in spec["components"] if c["id"] == a.tune_n), None)
        if target is None or target["geometry"]["type"] != "elliptical_loft":
            print(f"ERROR: --tune-n needs an elliptical_loft component id; got {a.tune_n!r}", file=sys.stderr)
            return 2
    def prep(v):
        sign = 1.0 if v["kind"] == "three_quarter_left" else -1.0
        yaws = [sign * y for y in np.arange(a.yaw_min, a.yaw_max + 1e-9, a.yaw_step)]
        ref = np.array(Image.open(ws / "02_views" / f"{v['id']}_mask.png").convert("L")) >= 128
        ref_small = np.array(Image.fromarray((ref * 255).astype(np.uint8)).resize((small.resolution_px,) * 2, Image.BILINEAR)) >= 128
        return yaws, ref, ref_small

    tuning = {}
    if target is not None:
        n_values = [float(x) for x in a.n_values.split(",")]
        for v in views:
            yaws, _, ref_small = prep(v)
            rows = []
            for n in n_values:
                s2 = copy.deepcopy(spec)
                next(c for c in s2["components"] if c["id"] == a.tune_n)["geometry"]["n"] = n
                (iou_n, yaw_n), _ = sweep(s2, ref_small, small, yaws)
                rows.append({"n": n, "best_iou": round(iou_n, 4), "yaw_deg": yaw_n})
            tuning[v["id"]] = {"component": a.tune_n, "current_n": target["geometry"].get("n", 2.0), "rows": rows,
                               "best": max(rows, key=lambda r: r["best_iou"])}
        if a.apply:
            n_best = float(np.median([t["best"]["n"] for t in tuning.values()]))
            target["geometry"]["n"] = n_best
            target["evidence"].setdefault("parameters", {})["n"] = {
                "status": "inferred", "view": ",".join(tuning),
                "note": "exponent chosen by held-out 3/4-view IoU sweep: " + "; ".join(f"{k}: best n={t['best']['n']} IoU {t['best']['best_iou']}" for k, t in tuning.items())}
            print(f"APPLIED n={n_best} to {a.tune_n}")

    for v in views:
        yaws, ref, ref_small = prep(v)
        (best_iou_small, best_yaw), scores = sweep(spec, ref_small, small, yaws)
        near = [y for y, sc in scores if sc >= best_iou_small - 0.005]
        rec = {"view_id": v["id"], "kind": v["kind"], "yaw_scores": scores, "best_yaw_deg": best_yaw,
               "yaw_plausible_range_deg": [min(near), max(near)]}
        if v["id"] in tuning:
            rec["n_tuning"] = tuning[v["id"]]
        m, _ = raster.render_view(spec, f"yaw:{best_yaw}", canvas, shaded=False)
        m, shift = align(ref, m >= 128)
        iou = silhouette.iou(ref, m)
        stations = np.round(np.linspace(0.002 * H, 0.998 * H, 200), 5)
        z, _, _, wr = analysis.widths(silhouette.profile(ref, canvas, stations))
        _, _, _, wm = analysis.widths(silhouette.profile(m, canvas, stations))
        d = np.nan_to_num(wm) - np.nan_to_num(wr)
        bands = analysis.bands(z, d, 0.02 * H)
        rec.update({"iou": round(iou, 4), "align_shift_px": shift, "status": "PASS" if iou >= a.iou_min else "CHECK",
                    "width_bands": bands, "diff_image": f"05_validation/{v['id']}_34_diff.png"})
        ref_rgba_p = ws / "02_views" / f"{v['id']}_ref.png"
        ref_rgba = np.array(Image.open(ref_rgba_p).convert("RGBA")) if ref_rgba_p.exists() else None
        drawing.diff_overlay(ref, m, canvas, f"{v['id']} yaw {best_yaw:+.0f} IoU {iou:.3f}", ref_rgba, H).save(out_dir / f"{v['id']}_34_diff.png")
        v["yaw_deg_estimate"] = best_yaw
        report["views"].append(rec)
        lo, hi = rec["yaw_plausible_range_deg"]
        md.append(f"## {v['id']} ({v['kind']}): {rec['status']} - IoU {iou:.3f} at estimated angle {best_yaw:+.0f} deg "
                  f"(angles {lo:+.0f}..{hi:+.0f} fit almost equally well{'; a round body makes the angle hard to pin down' if hi - lo >= 20 else ''})")
        for b in bands[:8]:
            what = "wider" if (b["worst"] or 0) > 0 else "narrower"
            md.append(f"- z {b['z_from']:.2f}-{b['z_to']:.2f} ({analysis.region_name(b['z_from'], H)}): model {what} by {abs(b['worst']):.3f}")
        if "n_tuning" in rec:
            t = rec["n_tuning"]
            md.append(f"- cross-section exponent for `{t['component']}` (n before this run = {t['current_n']}):")
            for r in t["rows"]:
                md.append(f"  - n={r['n']}: IoU {r['best_iou']} (yaw {r['yaw_deg']:+.0f})")
            md.append(f"  - best: n={t['best']['n']}" + (" (APPLIED; add a CHANGELOG line)" if a.apply else " (not applied; use --apply)"))
        md.append("")
    md += ["## How to read this",
           "- PASS: the cross-section between front and side is plausible.",
           "- CHECK with width bands: the model is too round (wider in 3/4) or too boxy. Try --tune-n,",
           "  or the 3/4 picture is off-model (common in AI sheets): ask the owner which to trust."]
    save_json(spec_file, spec)
    save_json(out_dir / "THREE_QUARTER.json", report)
    (out_dir / "THREE_QUARTER.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in report["views"]:
        extra = f" best n={r['n_tuning']['best']['n']}" if "n_tuning" in r else ""
        print(f"{r['view_id']}: {r['status']} IoU={r['iou']} yaw={r['best_yaw_deg']:+.0f}{extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
