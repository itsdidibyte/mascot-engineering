#!/usr/bin/env python3
"""G2 measured geometry: turn front + side silhouettes into an elliptical_loft component.

    python propose_spec.py WORKSPACE --id body [--z-range 0 1] [--step 0.02]
        [--front-seed 0.0] [--side-seed 0.0] [--mode main|envelope] [--n 2.0]
        [--material body] [--mirror-id twin_id] [--replace]

At each height z the loft cross-section is a superellipse whose half-width (a) and
centre (cx) come from the FRONT (or mirrored BACK) silhouette and whose half-depth (b)
and centre (cy) come from the SIDE silhouette. With orthographic views this matches
both silhouettes by construction, so the result is a measured starting body instead
of guessed primitives.

  --mode main      follow the silhouette run that contains the seed (default; ignores
                   arms/ears that are separate in that row)
  --mode envelope  outermost extent of everything in the row
  --z-range        build only a slice (e.g. the head: --z-range 0.62 1.0)
  --front-seed/--side-seed   horizontal world position that lies inside the part you
                   want (e.g. an ear at X=+0.25: --front-seed 0.25)

Truth labels: a/cx are `observed` (front), b/cy are `observed` when a side view exists,
otherwise `proposed` (b = a * --depth-ratio) and an issue is logged. Parts measured
away from the body centre get b/cy status `inferred` (the side silhouette there may
belong to another part).
Measured lofts are root components in WORLD coordinates (parent_id null); parent
small parts (eyes, ears) to them instead. Writes the component into build_spec.json and its station table into
03_geometry/MEASUREMENTS.json (id meas_<component>).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

from mascot_lib import silhouette  # noqa: E402
from mascot_lib.views import view_h_to_world_axis  # noqa: E402
from mascot_lib.workspace import append_issue, load_spec, save_json, view_by_kind  # noqa: E402


def load_prof(ws, v):
    return json.loads((ws / "02_views" / f"{v['id']}_profile.json").read_text(encoding="utf-8"))["stations"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--z-range", nargs=2, type=float, default=None)
    ap.add_argument("--step", type=float, default=0.02)
    ap.add_argument("--front-seed", type=float, default=0.0, help="world X inside the part")
    ap.add_argument("--side-seed", type=float, default=0.0, help="world Y inside the part")
    ap.add_argument("--mode", choices=("main", "envelope"), default="main")
    ap.add_argument("--n", type=float, default=2.0, help="cross-section exponent: 2 round, 3-4 boxier")
    ap.add_argument("--depth-ratio", type=float, default=0.85, help="b/a used ONLY when there is no side view")
    ap.add_argument("--material", default="body")
    ap.add_argument("--mirror-id", default=None, help="also create a mirrored twin with this id")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--despike", action="store_true", help="replace stations that bulge out because an arm/ear/foot touches the body (positive spikes vs a 9-station running median) by interpolation")
    ap.add_argument("--jump-tol", type=float, default=0.05, help="warn when a/b change more than this (x height) between stations")
    a = ap.parse_args(argv)

    ws = a.workspace.resolve()
    spec, spec_file = load_spec(ws)
    H = float(spec["scale"]["character_height"])
    if any(c["id"] == a.id for c in spec["components"]) and not a.replace:
        print(f"ERROR: component {a.id} exists (use --replace)", file=sys.stderr)
        return 2

    wv = view_by_kind(spec, "front") or view_by_kind(spec, "back")
    if wv is None or not (ws / "02_views" / f"{wv['id']}_profile.json").exists():
        print("ERROR: need a measured front or back view (run silhouettes.py)", file=sys.stderr)
        return 2
    sv = view_by_kind(spec, "right") or view_by_kind(spec, "left")
    if sv is not None and not (ws / "02_views" / f"{sv['id']}_profile.json").exists():
        sv = None

    w_axis, w_sign = view_h_to_world_axis(wv["kind"])          # front: X,+1  back: X,-1
    assert w_axis == 0
    wprof = load_prof(ws, wv)
    sprof = load_prof(ws, sv) if sv else None
    if sv:
        s_axis, s_sign = view_h_to_world_axis(sv["kind"])      # left: Y,+1  right: Y,-1
        assert s_axis == 1

    z_all = np.array([s["z"] for s in wprof])
    z0, z1 = (a.z_range if a.z_range else (float(z_all[0]), float(z_all[-1])))
    target = np.arange(z0, z1 + 1e-9, a.step)
    if len(target) == 0 or target[-1] < z1 - 1e-6:
        target = np.append(target, z1)
    target = np.clip(target, z_all[0], z_all[-1])
    idx = sorted({int(np.argmin(np.abs(z_all - t))) for t in target})

    def runs_for(prof, seed_view_h):
        if a.mode == "envelope":
            return [silhouette.envelope(s["runs"]) for s in prof]
        return silhouette.main_run_profile(prof, seed_view_h)

    wr = runs_for(wprof, a.front_seed * w_sign)
    sr = runs_for(sprof, a.side_seed * s_sign) if sv else None

    stations, table, gaps = [], [], 0
    for i in idx:
        z = float(z_all[i])
        r = wr[i]
        if r is None:
            gaps += 1
            continue
        x_lo, x_hi = sorted((r[0] * w_sign, r[1] * w_sign))
        cx, ha = (x_lo + x_hi) / 2, (x_hi - x_lo) / 2
        if sv:
            q = sr[i]
            if q is None:
                gaps += 1
                continue
            y_lo, y_hi = sorted((q[0] * s_sign, q[1] * s_sign))
            cy, hb = (y_lo + y_hi) / 2, (y_hi - y_lo) / 2
        else:
            cy, hb = 0.0, ha * a.depth_ratio
        stations.append([round(z, 5), round(cx, 5), round(ha, 5), round(cy, 5), round(hb, 5)])
        table.append({"z": round(z, 5), "width_view_run": r, "side_view_run": (sr[i] if sv else None)})
    despiked = []
    if a.despike and len(stations) >= 5:
        arr = np.array(stations, dtype=float)
        bad = np.zeros(len(arr), dtype=bool)
        for col in (2, 4):  # half-width, half-depth: remove POSITIVE spikes only (attached arms, ear bases)
            pad = np.pad(arr[:, col], 4, mode="edge")
            med = np.array([np.median(pad[k:k + 9]) for k in range(len(arr))])
            bad |= (arr[:, col] - med) > np.maximum(0.01 * H, 0.15 * med)
        if bad.any() and (~bad).sum() >= 2:
            for col in (1, 2, 3, 4):
                arr[bad, col] = np.interp(arr[bad, 0], arr[~bad, 0], arr[~bad, col])
            despiked = [round(float(z), 3) for z in arr[bad, 0]]
        stations = [[round(float(v), 5) for v in row] for row in arr]
    jumps = []
    for s0, s1 in zip(stations, stations[1:]):
        if max(abs(s1[2] - s0[2]), abs(s1[4] - s0[4])) > a.jump_tol * H:
            jumps.append(round((s0[0] + s1[0]) / 2, 3))
    if jumps:
        print(f"WARNING {a.id}: sudden width/depth jumps near z={jumps}. Usually another part (arm, ear, foot) merges "
              "into this silhouette there. Split the part with --z-range, re-run with --despike, or accept and record why.")
    if despiked:
        print(f"NOTE {a.id}: --despike interpolated over bulging stations at z={despiked}; fit those parts separately (fit_limb.py)")
    if len(stations) < 2:
        print("ERROR: fewer than 2 usable stations; check seeds/z-range", file=sys.stderr)
        return 2

    centred = abs(a.front_seed) < 0.05 * H and abs(a.side_seed) < 0.05 * H
    b_status = "observed" if (sv and centred) else ("inferred" if sv else "proposed")
    meas_id = f"meas_{a.id}"
    comp = {
        "id": a.id, "name": a.name or a.id.replace("_", " "), "parent_id": None,
        "geometry": {"type": "elliptical_loft", "stations": stations, "n": a.n, "segments": 64},
        "location": [0.0, 0.0, 0.0], "rotation_euler_deg": [0.0, 0.0, 0.0], "rotation_mode": "XYZ",
        "material_id": a.material, "articulation": "none",
        "evidence": {
            "status": "observed" if b_status == "observed" else "inferred",
            "method": f"elliptical loft from silhouette runs ({a.mode} mode), step {a.step}, exponent n={a.n}, despike={a.despike}",
            "reference_ids": [wv["id"]] + ([sv["id"]] if sv else []) + [meas_id],
            "parameters": {
                "stations[*].a,cx": {"status": "observed", "measurement_id": meas_id, "view": wv["id"]},
                "stations[*].b,cy": {"status": b_status, "measurement_id": meas_id if sv else None,
                                      "view": sv["id"] if sv else None},
                "n": {"status": "proposed", "note": "cross-section roundness is not visible in orthographic silhouettes"},
            },
            "uncertainty_note": ("Cross-section shape between silhouettes is assumed superelliptic. "
                                 + ("" if sv else f"No side view: depth = {a.depth_ratio} x width, PROPOSED. ")
                                 + ("" if centred else "Part is off-centre: side silhouette at these heights may include other parts. "))
        },
    }
    if a.mirror_id:
        comp["mirror"] = {"id": a.mirror_id}
    spec["components"] = [c for c in spec["components"] if c["id"] != a.id] + [comp]
    if not any(m["id"] == a.material for m in spec["materials"]):
        spec["materials"].append({"id": a.material, "base_color_rgba": [0.8, 0.8, 0.8, 1.0], "roughness": 0.5,
                                  "metallic": 0.0, "evidence_status": "proposed", "notes": "placeholder; set at G4"})
    if not sv:
        append_issue(spec, "G2", "major", f"{a.id}: no side view, all depths are PROPOSED (depth_ratio {a.depth_ratio}).")
    mpath = ws / "03_geometry" / "MEASUREMENTS.json"
    meas = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"measurements": []}
    meas["measurements"] = [m for m in meas["measurements"] if m["id"] != meas_id] + [{
        "id": meas_id, "component_id": a.id, "width_view": wv["id"], "side_view": sv["id"] if sv else None,
        "mode": a.mode, "front_seed": a.front_seed, "side_seed": a.side_seed, "z_range": [z0, z1],
        "units": "world units (relative to character height)", "stations": table, "gaps_skipped": gaps,
        "despiked_z": despiked, "jump_warnings_z": jumps}]
    save_json(mpath, meas)
    save_json(spec_file, spec)
    print(f"COMPONENT {a.id}: {len(stations)} stations, b-status={b_status}, gaps={gaps}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
