#!/usr/bin/env python3
"""Fit an arm / leg / tail / antenna as a (tilted) capsule from the silhouettes.

    python fit_limb.py WORKSPACE --id arm_l --x-seed 0.3 --z-range 0.30 0.55
        [--y-seed 0.0] [--body-seed-x 0.0] [--body-seed-y 0.0] [--embed 1.0]
        [--mirror-id arm_r] [--material body] [--replace] [--dry-run]

In the front (or back) view, rows inside --z-range usually show the limb as its own
run beside the body. Those "free" rows are fitted with a straight axis
(X = slope*z + c) and a radius (median half-width x cos(tilt)). The free tip is the
end farther from the body; the other end is pushed --embed radii into the body so
the joint has no gap. If the side view also shows the limb free of the body (a tail,
a leg kicked forward), its Y tilt is fitted too; otherwise Y comes from the side
silhouette centre at that height and is labelled `inferred`.
Writes a `capsule` component (+ mirror twin) and a measurement record meas_<id>.
Always check the result with render_preview.py + compare.py.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

from mascot_lib import silhouette  # noqa: E402
from mascot_lib.views import view_h_to_world_axis  # noqa: E402
from mascot_lib.workspace import load_spec, save_json, view_by_kind  # noqa: E402


def free_rows(prof, sign, z0, z1, seed, body_seed):
    """(z, centre, half) of the run nearest `seed` that does not contain `body_seed` (world units)."""
    out = []
    for s in prof:
        if not (z0 <= s["z"] <= z1):
            continue
        runs = [sorted((r[0] * sign, r[1] * sign)) for r in s["runs"]]
        runs = [r for r in runs if not (r[0] <= body_seed <= r[1])]
        if not runs:
            continue
        r = min(runs, key=lambda r: abs((r[0] + r[1]) / 2 - seed))
        if abs((r[0] + r[1]) / 2 - seed) > 0.5:
            continue
        out.append((s["z"], (r[0] + r[1]) / 2, (r[1] - r[0]) / 2))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--x-seed", type=float, required=True, help="world X near the limb (front view; +X = character's left)")
    ap.add_argument("--z-range", nargs=2, type=float, required=True)
    ap.add_argument("--y-seed", type=float, default=None, help="world Y near the limb in the side view (only if it sticks out there)")
    ap.add_argument("--body-seed-x", type=float, default=0.0)
    ap.add_argument("--body-seed-y", type=float, default=0.0)
    ap.add_argument("--embed", type=float, default=1.0, help="push the attached end this many radii into the body")
    ap.add_argument("--mirror-id", default=None)
    ap.add_argument("--material", default="body")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    if any(c["id"] == a.id for c in spec["components"]) and not a.replace and not a.dry_run:
        print(f"ERROR: component {a.id} exists (use --replace)", file=sys.stderr)
        return 2
    z0, z1 = sorted(a.z_range)
    wv = view_by_kind(spec, "front") or view_by_kind(spec, "back")
    if not wv or not (ws / "02_views" / f"{wv['id']}_profile.json").exists():
        print("ERROR: need a measured front/back view", file=sys.stderr)
        return 2
    _, wsign = view_h_to_world_axis(wv["kind"])
    wprof = json.loads((ws / "02_views" / f"{wv['id']}_profile.json").read_text(encoding="utf-8"))["stations"]
    rows = free_rows(wprof, wsign, z0, z1, a.x_seed, a.body_seed_x)
    if len(rows) < 3:
        print(f"ERROR: only {len(rows)} rows where the limb is separate from the body in {wv['id']}; widen --z-range or check --x-seed",
              file=sys.stderr)
        return 2
    z_all, cx_all, half_all = (np.array(v, dtype=float) for v in zip(*rows))
    # rounded tips and rows clipped by the body have a shorter span and an off-axis centre:
    # fit the axis on the "straight" rows only (span close to the median)
    med = float(np.median(half_all))
    keep = np.abs(half_all - med) <= 0.15 * med
    if keep.sum() < 3:
        keep = np.ones_like(z_all, dtype=bool)
    z, cx, half = z_all[keep], cx_all[keep], half_all[keep]
    sx, ix = np.polyfit(z, cx, 1)
    resid_x = float(np.sqrt(np.mean((sx * z + ix - cx) ** 2)))
    z = z_all  # the tip/base extent uses every free row

    sv = view_by_kind(spec, "right") or view_by_kind(spec, "left")
    sy, iy, y_status, srows = 0.0, None, "proposed", []
    if sv and (ws / "02_views" / f"{sv['id']}_profile.json").exists():
        _, ssign = view_h_to_world_axis(sv["kind"])
        sprof = json.loads((ws / "02_views" / f"{sv['id']}_profile.json").read_text(encoding="utf-8"))["stations"]
        if a.y_seed is not None:
            srows = free_rows(sprof, ssign, z0, z1, a.y_seed, a.body_seed_y)
        if len(srows) >= 3:
            zs, cy, _ = (np.array(v, dtype=float) for v in zip(*srows))
            sy, iy = np.polyfit(zs, cy, 1)
            y_status = "observed"
        else:
            main = silhouette.main_run_profile(sprof, a.body_seed_y * ssign)
            zz = np.array([s["z"] for s in sprof])
            k = int(np.argmin(np.abs(zz - (z0 + z1) / 2)))
            r = main[k]
            iy = (r[0] + r[1]) / 2 * ssign if r else 0.0
            sy = 0.0
            y_status = "inferred"
    else:
        iy = 0.0

    d = np.array([sx, sy, 1.0])
    d /= np.linalg.norm(d)
    tilt = math.acos(d[2])
    radius = float(np.median(half) * math.cos(math.atan(sx)))

    def axis_pt(zq):
        return np.array([sx * zq + ix, sy * zq + (iy if iy is not None else 0.0), zq])
    lo, hi = axis_pt(z.min()), axis_pt(z.max())
    tip_is_high = abs(hi[0] - a.body_seed_x) >= abs(lo[0] - a.body_seed_x)
    if tip_is_high:
        tip = axis_pt(z.max() - radius)                # topmost silhouette point = tip-sphere centre + r (vertical)
        base = lo - d * radius * a.embed
    else:
        tip = axis_pt(z.min() + radius)
        base = hi + d * radius * a.embed
    length = float(max(np.linalg.norm(tip - base), 0.0))
    centre = (tip + base) / 2
    b = math.degrees(math.atan(d[0] / d[2]))
    a_deg = math.degrees(math.atan(-d[1] * math.cos(math.radians(b)) / d[2])) if d[2] else 0.0

    meas_id = f"meas_{a.id}"
    comp = {
        "id": a.id, "name": a.name or a.id.replace("_", " "), "parent_id": None,
        "geometry": {"type": "capsule", "radius": round(radius, 5), "length": round(length, 5), "segments": 32, "cap_rings": 8},
        "location": [round(float(v), 5) for v in centre], "rotation_euler_deg": [round(a_deg, 3), round(b, 3), 0.0],
        "rotation_mode": "XYZ", "material_id": a.material, "articulation": "rigid",
        "evidence": {
            "status": "inferred",
            "method": f"capsule fit to {len(rows)} free silhouette rows (front) z {z0}-{z1}; axis RMS {resid_x:.4f}",
            "reference_ids": [wv["id"]] + ([sv["id"]] if sv else []) + [meas_id],
            "parameters": {"location.x,z;rotation.y;radius": {"status": "observed", "measurement_id": meas_id, "view": wv["id"]},
                           "location.y;rotation.x": {"status": y_status, "view": sv["id"] if sv else None},
                           "attached_end": {"status": "proposed", "note": f"embedded {a.embed} radius into the body"}},
            "uncertainty_note": "Straight-capsule approximation of the limb; the attached end is hidden by the body. "
                                + ("Depth position taken from the side silhouette centre (limb not separate in side view)." if y_status == "inferred" else ""),
        },
    }
    if a.mirror_id:
        comp["mirror"] = {"id": a.mirror_id}
    summary = (f"{a.id}: radius {radius:.4f}, length {length:.4f}, centre {np.round(centre, 4).tolist()}, "
               f"rotation XYZ [{a_deg:.1f}, {b:.1f}, 0] deg, {len(rows)} rows, axis RMS {resid_x:.4f}, Y {y_status}")
    if a.dry_run:
        print("DRY RUN", summary)
        print(json.dumps(comp, indent=2))
        return 0
    spec["components"] = [c for c in spec["components"] if c["id"] != a.id] + [comp]
    if not any(m["id"] == a.material for m in spec["materials"]):
        spec["materials"].append({"id": a.material, "base_color_rgba": [0.8, 0.8, 0.8, 1.0], "evidence_status": "proposed"})
    mpath = ws / "03_geometry" / "MEASUREMENTS.json"
    meas = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"measurements": []}
    meas["measurements"] = [m for m in meas["measurements"] if m["id"] != meas_id] + [{
        "id": meas_id, "component_id": a.id, "width_view": wv["id"], "side_view": sv["id"] if sv else None,
        "method": "free-run line fit", "z_range": [z0, z1], "rows_front": [list(map(float, r)) for r in rows],
        "rows_side": [list(map(float, r)) for r in srows], "fit": {"slope_x": float(sx), "intercept_x": float(ix), "slope_y": float(sy),
                                                                   "axis_rms": resid_x}}]
    save_json(mpath, meas)
    save_json(spec_file, spec)
    print("LIMB", summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
