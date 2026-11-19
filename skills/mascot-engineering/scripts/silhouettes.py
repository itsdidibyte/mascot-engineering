#!/usr/bin/env python3
"""G1 measurement: extract each reference view's silhouette and normalise it onto the canonical canvas.

    python silhouettes.py WORKSPACE [--view front] [--tolerance 32]
        [--exclude VIEW:x0,y0,x1,y1 ...] [--anchor-col VIEW:col] [--method VIEW:alpha|border_color]
        [--allow-cropped]

Writes per view into 02_views/:
    <view>_mask.png       binary silhouette on the canonical canvas (white = character)
    <view>_ref.png        the reference picture on the same canvas (for overlays)
    <view>_overlay.png    picture + red outline + height guides: CHECK THIS BY EYE
    <view>_profile.json   runs of the silhouette at 101 heights (z = 0.00 .. 1.00)
and records the normalisation (bbox, scale, anchor) in build_spec.json views[].normalization.

Stops with an error if the silhouette touches the image border (probably cropped)
unless --allow-cropped is given; the issue is then logged.
Ground shadows, floor lines or text in the picture end up in the mask: remove them
with --exclude VIEW:x0,y0,x1,y1 (source pixels) and re-run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mascot_lib import drawing, silhouette  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402
from mascot_lib.workspace import append_issue, load_spec, save_json  # noqa: E402

MEASURABLE = ("front", "back", "left", "right", "three_quarter_left", "three_quarter_right")


def per_view(values, cast=str):
    out = {}
    for v in values or []:
        if ":" not in v:
            raise ValueError(f"expected VIEW:value, got {v!r}")
        k, val = v.split(":", 1)
        out.setdefault(k, []).append(cast(val))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--view", action="append", help="only these view ids (default: all measurable)")
    ap.add_argument("--tolerance", type=int, default=32, help="background colour tolerance 0..255")
    ap.add_argument("--exclude", action="append", help="VIEW:x0,y0,x1,y1 source-pixel box to remove (shadows, text)")
    ap.add_argument("--anchor-col", action="append", help="VIEW:col explicit source column for h=0 (default bbox centre)")
    ap.add_argument("--method", action="append", help="VIEW:alpha|border_color to force a mask method")
    ap.add_argument("--allow-cropped", action="store_true")
    a = ap.parse_args(argv)

    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    canvas = Canvas.from_dict(spec.get("canvas"))
    height = float(spec["scale"]["character_height"])
    excl = {k: [tuple(float(x) for x in b.split(",")) for b in v] for k, v in per_view(a.exclude).items()}
    anchors = {k: float(v[-1]) for k, v in per_view(a.anchor_col).items()}
    methods = {k: v[-1] for k, v in per_view(a.method).items()}
    refs = {r["id"]: r for r in spec["source_references"]}
    out_dir = ws / "02_views"
    stations = np.round(np.linspace(0, height, 101), 5)
    stations[0] = height * 0.002   # stay inside the silhouette at the extremes
    stations[-1] = height * 0.998
    failures = 0
    lines = ["# Silhouette extraction report", "", "| view | method | bbox px | src px/unit | parts | border | status |", "|---|---|---|---|---|---|---|"]
    for v in spec["views"]:
        if v["kind"] not in MEASURABLE or v.get("role") == "rejected":
            continue
        if a.view and v["id"] not in a.view:
            continue
        if v["projection"] in ("perspective_unknown",):
            print(f"SKIP {v['id']}: projection is perspective_unknown; not measured (set orthographic_assumed if acceptable)")
            continue
        ref = refs[v["source_reference_id"]]
        img = Image.open(ws / ref["relative_path"])
        img.load()
        mask, rep = silhouette.extract_mask(img, tolerance=a.tolerance, exclude_boxes=excl.get(v["id"]),
                                            force_method=methods.get(v["id"]))
        status = "OK"
        if rep["touches_border"]:
            msg = f"View {v['id']}: silhouette touches the image border ({', '.join(rep['touches_border'])}) - probably cropped; heights/widths unreliable."
            if not a.allow_cropped:
                print("ERROR:", msg, "Use --allow-cropped to proceed anyway.", file=sys.stderr)
                failures += 1
                lines.append(f"| {v['id']} | {rep['method']} | - | - | - | {','.join(rep['touches_border'])} | FAILED (cropped) |")
                continue
            append_issue(spec, "G1", "major", msg)
            status = "CROPPED (allowed)"
        cmask, crgba, norm = silhouette.normalize_to_canvas(mask, img, canvas, height, anchors.get(v["id"]))
        norm["mask_report"] = rep
        norm["canvas"] = canvas.as_dict()
        v["normalization"] = norm
        Image.fromarray((cmask * 255).astype(np.uint8)).save(out_dir / f"{v['id']}_mask.png")
        Image.fromarray(crgba, "RGBA").save(out_dir / f"{v['id']}_ref.png")
        drawing.mask_overlay(crgba, cmask, canvas, f"{v['id']} ({v['kind']})", height).save(out_dir / f"{v['id']}_overlay.png")
        prof = silhouette.profile(cmask, canvas, stations)
        save_json(out_dir / f"{v['id']}_profile.json", {
            "view_id": v["id"], "kind": v["kind"], "units": "world units on the canonical canvas (h horizontal, z up)",
            "method": "row runs of normalised silhouette mask", "canvas": canvas.as_dict(), "stations": prof})
        bb = norm["bbox_px"]
        lines.append(f"| {v['id']} | {rep['method']} | {bb} | {norm['source_px_per_unit']:.1f} | {rep['parts_kept']} | {','.join(rep['touches_border']) or '-'} | {status} |")
        print(f"VIEW {v['id']}: {status} bbox={bb} parts={rep['parts_kept']} specks_dropped={len(rep['specks_dropped_px'])}")
    lines += ["", "Open every `*_overlay.png`: the red outline must hug the character only (no shadow, text or floor).",
              "If it does not, re-run with `--exclude VIEW:x0,y0,x1,y1` or `--tolerance`."]
    (out_dir / "SILHOUETTE_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    save_json(spec_file, spec)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
