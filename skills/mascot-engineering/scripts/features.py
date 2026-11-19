#!/usr/bin/env python3
"""Find features drawn INSIDE the silhouette (eyes, nose, mouth, belly patch, buttons).

    python features.py WORKSPACE [--view front] [--min-area 0.0004] [--color-dist 90]
        [--margin 0.02] [--add PREFIX:ID[,ID..]] [--protrude 0.3] [--material dark]

Silhouette comparison cannot see these, so they are found by colour: pixels inside the
normalised front reference whose colour differs strongly (> --color-dist, RGB distance)
from the dominant body colour, away from the outline (--margin, x height), grouped into
blobs larger than --min-area (x height^2). Each blob gets a centre (X, Z), half-size,
mean colour and a suggested surface depth Y computed from the measured front/side
silhouettes at that height (point on the elliptical cross-section).
Writes 03_geometry/FEATURES.json and FEATURES.png (numbered blobs).

--add eye:1,2   turns blobs 1 and 2 into ellipsoid components eye_1, eye_2 (X/Z/size
                `observed`, Y on the surface `inferred`, thickness `proposed`:
                depth radius = --protrude x the smaller visible half-size).
Shading, highlights and outlines in the drawing also create blobs; blobs with the body's
hue are flagged likely_shading. Look at FEATURES.png and add only real features.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from scipy import ndimage  # noqa: E402

from mascot_lib import silhouette  # noqa: E402
from mascot_lib.views import Canvas, view_h_to_world_axis  # noqa: E402
from mascot_lib.workspace import load_spec, save_json, view_by_kind  # noqa: E402


def surface_y(ws, spec, x, z):
    """Front surface Y at (x, z) on the ellipse from front/side main runs (None if unknown)."""
    fv = view_by_kind(spec, "front")
    sv = view_by_kind(spec, "right") or view_by_kind(spec, "left")
    if not fv or not sv:
        return None, "no side view"
    out = []
    for v in (fv, sv):
        prof = json.loads((ws / "02_views" / f"{v['id']}_profile.json").read_text(encoding="utf-8"))["stations"]
        zz = np.array([s["z"] for s in prof])
        k = int(np.argmin(np.abs(zz - z)))
        _, sign = view_h_to_world_axis(v["kind"])
        runs = [sorted((r[0] * sign, r[1] * sign)) for r in prof[k]["runs"]]
        seed = x if v is fv else 0.0
        r = silhouette.pick_run(runs, seed)
        if r is None:
            return None, "no silhouette at that height"
        out.append(r)
    (x0, x1), (y0, y1) = out
    cx, a = (x0 + x1) / 2, (x1 - x0) / 2
    cy, b = (y0 + y1) / 2, (y1 - y0) / 2
    t = min(1.0, abs(x - cx) / a) if a > 0 else 1.0
    return cy - b * float(np.sqrt(max(0.0, 1 - t * t))), "ellipse from front+side main runs"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--view", default=None, help="view id (default: canonical front)")
    ap.add_argument("--min-area", type=float, default=0.0004)
    ap.add_argument("--color-dist", type=float, default=90)
    ap.add_argument("--margin", type=float, default=0.02)
    ap.add_argument("--add", default=None, help="PREFIX:ID[,ID..] e.g. eye:1,2")
    ap.add_argument("--protrude", type=float, default=0.3)
    ap.add_argument("--material", default="dark")
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    H = float(spec["scale"]["character_height"])
    canvas = Canvas.from_dict(spec.get("canvas"))
    v = next((x for x in spec["views"] if x["id"] == a.view), None) if a.view else view_by_kind(spec, "front")
    if not v or not (ws / "02_views" / f"{v['id']}_ref.png").exists():
        print("ERROR: need a measured front view (run silhouettes.py)", file=sys.stderr)
        return 2
    if v["kind"] != "front":
        print("ERROR: features are placed from the FRONT view only", file=sys.stderr)
        return 2
    rgba = np.array(Image.open(ws / "02_views" / f"{v['id']}_ref.png").convert("RGBA"))
    mask = np.array(Image.open(ws / "02_views" / f"{v['id']}_mask.png").convert("L")) >= 128
    inner = ndimage.binary_erosion(mask, iterations=max(1, int(a.margin * H * canvas.px_per_unit)))
    rgb = rgba[..., :3].astype(float)
    body = np.median(rgb[inner], axis=0)
    dist = np.sqrt(((rgb - body) ** 2).sum(axis=2))
    cand = inner & (dist > a.color_dist)
    cand = ndimage.binary_opening(cand, iterations=1)
    lab, n = ndimage.label(cand)
    min_px = a.min_area * (H * canvas.px_per_unit) ** 2
    feats = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < min_px:
            continue
        h0, z1 = canvas.to_world(xs.min(), ys.min())
        h1, z0 = canvas.to_world(xs.max() + 1, ys.max() + 1)
        cx, cz = (float(h0) + float(h1)) / 2, (float(z0) + float(z1)) / 2
        y, how = surface_y(ws, spec, cx, cz)
        col = rgb[ys, xs].mean(axis=0)
        chroma = np.abs(col / max(col.sum(), 1e-6) - body / max(body.sum(), 1e-6)).sum()
        feats.append({"centre_xz": [round(cx, 4), round(cz, 4)], "half_size_xz": [round((float(h1) - float(h0)) / 2, 4), round((float(z1) - float(z0)) / 2, 4)],
                      "area_units2": round(len(ys) / canvas.px_per_unit ** 2, 6), "mean_rgb": [int(c) for c in col],
                      "hex": "#%02x%02x%02x" % tuple(int(c) for c in col),
                      "likely_shading": bool(chroma < 0.08),
                      "surface_y": None if y is None else round(y, 4), "surface_y_method": how})
    feats.sort(key=lambda f: (-f["centre_xz"][1], f["centre_xz"][0]))
    for k, f in enumerate(feats, 1):
        f["id"] = k
    img = Image.fromarray(rgba, "RGBA").copy()
    d = ImageDraw.Draw(img)
    for f in feats:
        (cx, cz), (hx, hz) = f["centre_xz"], f["half_size_xz"]
        c0, r0 = canvas.to_pixel(cx - hx, cz + hz)
        c1, r1 = canvas.to_pixel(cx + hx, cz - hz)
        d.rectangle([float(c0) - 2, float(r0) - 2, float(c1) + 2, float(r1) + 2], outline=(0, 160, 255, 255), width=2)
        d.text((float(c1) + 4, float(r0) - 4), str(f["id"]), fill=(0, 90, 220, 255))
    out = ws / "03_geometry"
    out.mkdir(parents=True, exist_ok=True)
    img.save(out / "FEATURES.png")
    save_json(out / "FEATURES.json", {"view_id": v["id"], "body_rgb": [int(c) for c in body], "color_dist": a.color_dist, "features": feats})
    for f in feats:
        tag = "  (same hue as body: probably drawn SHADING, not a feature)" if f["likely_shading"] else ""
        print(f"#{f['id']}: centre X,Z {f['centre_xz']} half {f['half_size_xz']} colour {f['hex']} surface Y {f['surface_y']}{tag}")
    if a.add:
        prefix, ids = a.add.split(":", 1)
        by = {f["id"]: f for f in feats}
        for sid in ids.split(","):
            f = by.get(int(sid))
            if not f:
                print(f"ERROR: no feature #{sid}", file=sys.stderr)
                return 2
            if f["surface_y"] is None:
                print(f"ERROR: feature #{sid}: surface depth unknown ({f['surface_y_method']})", file=sys.stderr)
                return 2
            hx, hz = f["half_size_xz"]
            ry = a.protrude * min(hx, hz)
            cid = f"{prefix}_{sid}"
            comp = {"id": cid, "name": f"{prefix} {sid}", "parent_id": None,
                    "geometry": {"type": "ellipsoid", "radii": [hx, ry, hz], "segments": 32, "rings": 16},
                    "location": [f["centre_xz"][0], round(f["surface_y"] + ry * 0.5, 5), f["centre_xz"][1]],
                    "rotation_euler_deg": [0, 0, 0], "rotation_mode": "XYZ", "material_id": a.material, "articulation": "rigid",
                    "evidence": {"status": "inferred", "method": f"colour blob #{sid} in {v['id']} (FEATURES.json)",
                                 "reference_ids": [v["id"]],
                                 "parameters": {"location.x,z;radii.x,z": {"status": "observed", "view": v["id"]},
                                                "location.y": {"status": "inferred", "note": f["surface_y_method"]},
                                                "radii.y": {"status": "proposed", "note": f"protrusion {a.protrude} x visible half-size"}},
                                 "uncertainty_note": "Surface depth assumes an elliptical cross-section; protrusion is a proposal."}}
            spec["components"] = [c for c in spec["components"] if c["id"] != cid] + [comp]
            if not any(m["id"] == a.material for m in spec["materials"]):
                spec["materials"].append({"id": a.material, "base_color_rgba": [round(c / 255, 4) for c in f["mean_rgb"]] + [1.0],
                                          "evidence_status": "observed", "notes": f"mean colour of feature #{sid} in {v['id']}"})
            print(f"ADDED {cid}")
        save_json(spec_file, spec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
