#!/usr/bin/env python3
"""G3 feedback loop: compare model renders with the normalised reference silhouettes.

    python compare.py WORKSPACE [--source preview|blender] [--tol 0.02] [--iou-min 0.95]

For every measured view with a render mask (04_build/preview or 04_build/renders):
  * silhouette IoU
  * per-height edge errors: where the model is too wide / too narrow, on which side,
    translated into world axes (+X = character's left, -Y = forward)
  * diff image: grey = both, RED = reference only (model MISSING material),
    BLUE = model only (model has EXCESS material)
Writes 05_validation/COMPARE_<source>.json and .md and <view>_diff.png.
Exit 0 if every view passes both thresholds, 4 otherwise. Thresholds are starting
defaults: agree project-specific values at G2 and record them in DECISIONS.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mascot_lib import analysis, drawing, silhouette  # noqa: E402
from mascot_lib.views import Canvas, view_axes  # noqa: E402
from mascot_lib.workspace import load_spec, save_json  # noqa: E402

AXIS_WORDS = {
    (0, 1.0): "+X (character's LEFT)", (0, -1.0): "-X (character's RIGHT)",
    (1, 1.0): "+Y (character's BACK)", (1, -1.0): "-Y (character's FRONT)",
}


def edge_words(kind: str):
    r = view_axes(kind)[0]
    i = int(np.argmax(np.abs(r)))
    s = float(r[i])
    return AXIS_WORDS[(i, -s)], AXIS_WORDS[(i, s)]   # (image-left edge, image-right edge)


def load_mask(p: Path) -> np.ndarray:
    im = Image.open(p)
    if im.mode in ("RGBA", "LA"):
        arr = np.array(im)[..., -1]
    else:
        arr = np.array(im.convert("L"))
    return arr >= 128


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--source", choices=("preview", "blender"), default="preview")
    ap.add_argument("--tol", type=float, default=0.02, help="edge tolerance, fraction of character height")
    ap.add_argument("--iou-min", type=float, default=0.95)
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, _ = load_spec(ws)
    H = float(spec["scale"]["character_height"])
    tol = a.tol * H
    canvas = Canvas.from_dict(spec.get("canvas"))
    rdir = ws / "04_build" / ("preview" if a.source == "preview" else "renders")
    vdir = ws / "02_views"
    out_dir = ws / "05_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    stations = np.round(np.linspace(0.002 * H, 0.998 * H, 200), 5)
    report = {"source": a.source, "tolerance_units": tol, "iou_min": a.iou_min, "views": []}
    all_pass = True
    tested = 0
    for v in spec["views"]:
        ref_p = vdir / f"{v['id']}_mask.png"
        ren_p = rdir / (f"{v['id']}_mask.png")
        if not ref_p.exists() or not ren_p.exists():
            continue
        tested += 1
        ref, ren = load_mask(ref_p), load_mask(ren_p)
        if ref.shape != ren.shape:
            print(f"ERROR {v['id']}: mask sizes differ {ref.shape} vs {ren.shape}", file=sys.stderr)
            return 2
        iou = silhouette.iou(ref, ren)
        pr = silhouette.profile(ref, canvas, stations)
        pm = silhouette.profile(ren, canvas, stations)
        z, rl, rr, _ = analysis.widths(pr)
        _, ml, mr, _ = analysis.widths(pm)
        # positive = model sticks out further than reference on that edge
        left_err = np.where(np.isnan(rl) & np.isnan(ml), np.nan, np.nan_to_num(rl, nan=0) - np.nan_to_num(ml, nan=0))
        right_err = np.where(np.isnan(rr) & np.isnan(mr), np.nan, np.nan_to_num(mr, nan=0) - np.nan_to_num(rr, nan=0))
        # one-sided rows: model missing entirely or extra entirely
        only_ref = ~np.isnan(rl) & np.isnan(ml)
        only_mod = np.isnan(rl) & ~np.isnan(ml)
        left_err[only_ref] = -(rr[only_ref] - rl[only_ref])
        right_err[only_ref] = -(rr[only_ref] - rl[only_ref])
        left_err[only_mod] = (mr[only_mod] - ml[only_mod])
        right_err[only_mod] = (mr[only_mod] - ml[only_mod])
        lw, rw = edge_words(v["kind"])
        findings = []
        for err, side_word in ((left_err, lw), (right_err, rw)):
            for b in analysis.bands(z, err, tol):
                if b["worst"] is None:
                    continue
                what = "TOO WIDE (excess)" if b["worst"] > 0 else "TOO NARROW (missing)"
                findings.append({"z_from": b["z_from"], "z_to": b["z_to"], "edge": side_word, "error": b["worst"],
                                 "region": analysis.region_name((b["z_from"] + b["z_to"]) / 2, H),
                                 "text": f"z {b['z_from']:.2f}-{b['z_to']:.2f} ({analysis.region_name((b['z_from'] + b['z_to']) / 2, H)}): "
                                         f"model {what} by {abs(b['worst']):.3f} on the {side_word} edge"})
        merged = []
        for f in findings:
            twin = next((g for g in merged if g["z_from"] == f["z_from"] and g["z_to"] == f["z_to"]
                         and g["edge"] != f["edge"] and np.sign(g["error"]) == np.sign(f["error"])
                         and abs(g["error"] - f["error"]) <= tol), None)
            if twin:
                twin["edge"] = "BOTH"
                twin["text"] = twin["text"].rsplit(" on the ", 1)[0] + " on BOTH edges (symmetric: change the part's size, not its position)"
            else:
                merged.append(dict(f))
        findings = sorted(merged, key=lambda f: -abs(f["error"]))
        max_edge = float(np.nanmax(np.abs(np.concatenate([left_err, right_err])))) if np.isfinite(np.concatenate([left_err, right_err])).any() else 0.0
        ok = iou >= a.iou_min and not findings
        all_pass &= ok
        ref_rgba_p = vdir / f"{v['id']}_ref.png"
        ref_rgba = np.array(Image.open(ref_rgba_p).convert("RGBA")) if ref_rgba_p.exists() else None
        drawing.diff_overlay(ref, ren, canvas, f"{v['id']} IoU {iou:.3f}", ref_rgba, H).save(out_dir / f"{v['id']}_{a.source}_diff.png")
        report["views"].append({"view_id": v["id"], "kind": v["kind"], "iou": round(iou, 4),
                                "max_edge_error": round(max_edge, 4), "status": "PASS" if ok else "FAIL",
                                "findings": findings,
                                "diff_image": f"05_validation/{v['id']}_{a.source}_diff.png"})
    if tested == 0:
        print("ERROR: nothing to compare (need 02_views/<view>_mask.png and a render mask)", file=sys.stderr)
        return 2
    report["overall"] = "PASS" if all_pass else "FAIL"
    save_json(out_dir / f"COMPARE_{a.source}.json", report)
    md = [f"# Silhouette comparison ({a.source}): **{report['overall']}**", "",
          f"Thresholds: IoU >= {a.iou_min}, edge error <= {tol:.3f} units ({a.tol:.0%} of height).",
          "Diff images: grey = match, RED = model missing, BLUE = model excess.", ""]
    for r in report["views"]:
        md.append(f"## {r['view_id']} ({r['kind']}): {r['status']} - IoU {r['iou']}, max edge error {r['max_edge_error']}")
        for f in r["findings"][:12]:
            md.append(f"- {f['text']}")
        if len(r["findings"]) > 12:
            md.append(f"- ... {len(r['findings']) - 12} more in the JSON")
        md.append("")
    md += ["## How to use this", "1. Fix the LARGEST finding first, changing ONE named component's parameters.",
           "2. Re-render and re-compare. Keep a change only if the target band improves and no other view gets worse.",
           "3. Log each change (component, parameter, old -> new, reason) in 04_build/CHANGELOG.md."]
    (out_dir / f"COMPARE_{a.source}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    for r in report["views"]:
        print(f"{r['view_id']}: {r['status']} IoU={r['iou']} findings={len(r['findings'])}")
    print(f"OVERALL {report['overall']} -> 05_validation/COMPARE_{a.source}.md")
    return 0 if all_pass else 4


if __name__ == "__main__":
    sys.exit(main())
