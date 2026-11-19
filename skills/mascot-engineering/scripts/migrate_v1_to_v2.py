#!/usr/bin/env python3
"""Migrate a v1.0.0 build spec (ChatGPT kit) to v2.0.0 without changing the built shape.

    python migrate_v1_to_v2.py OLD_SPEC.json NEW_SPEC.json

v1 axes: +X character RIGHT, +Y FORWARD, +Z up.  v2 axes (Blender-native): +X character
LEFT, -Y forward, +Z up. The two differ by a 180 deg turn about Z, applied by
conjugation so every component keeps its id, parent, primitive and dimensions:
    location (x, y, z)          -> (-x, -y, z)
    XYZ Euler (a, b, c)         -> (-a, -b, c)
    pinhole R_world_to_cv       -> R @ Rz(180)^T
v1 primitives are all symmetric under that turn, so meshes are unchanged.
Dropped: box.bevel (v2 boxes are plain; use superellipsoid for rounded boxes).
Every changed number is written to a MIGRATION_LOG.md next to the new spec.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402

from mascot_lib import meshgen  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402

RZ180 = np.diag([-1.0, -1.0, 1.0])


def fnum(x):
    v = float(x)
    return 0.0 if v == 0 else v  # avoid -0.0 noise


def migrate(v1: dict) -> tuple[dict, list[str]]:
    if v1.get("schema_version") != "1.0.0":
        raise ValueError("input is not a v1.0.0 spec")
    log = []
    comps = []
    approved = []
    for c in v1["components"]:
        n = copy.deepcopy(c)
        x, y, z = c["location"]
        n["location"] = [fnum(-x), fnum(-y), fnum(z)]
        a, b, cc = c["rotation_euler_deg"]
        n["rotation_euler_deg"] = [fnum(-a), fnum(-b), fnum(cc)]
        n["rotation_mode"] = "XYZ"
        if n["location"] != [fnum(v) for v in c["location"]]:
            log.append(f"- `{c['id']}` location {c['location']} -> {n['location']} (axis convention)")
        if n["rotation_euler_deg"] != [fnum(v) for v in c["rotation_euler_deg"]]:
            log.append(f"- `{c['id']}` rotation {c['rotation_euler_deg']} -> {n['rotation_euler_deg']} (axis convention)")
        if n["geometry"]["type"] == "box" and "bevel" in n["geometry"]:
            log.append(f"- `{c['id']}` dropped box.bevel={n['geometry'].pop('bevel')} (not in v2)")
            n["notes"] = (n.get("notes", "") + " v1 bevel dropped in migration.").strip()
        if n["evidence"]["status"] == "approved_design":
            n["evidence"]["decision_id"] = "D-MIGRATED-V1"
            approved.append(c["id"])
        comps.append(n)
    views = []
    for v in v1.get("camera_views", []):
        model, cal = v["camera_model"], v["calibration_status"]
        known = cal in ("known", "fitted")
        proj = {"orthographic": "orthographic_known" if known else "orthographic_assumed",
                "pinhole": "perspective_known" if known else "perspective_unknown"}.get(model, "perspective_unknown")
        nv = {"id": v["id"], "source_reference_id": v["source_reference_id"], "kind": "other", "projection": proj,
              "role": "supporting", "normalization": None,
              "notes": "Migrated from v1 camera_views: set kind (front/back/left/right) by hand after checking the image. " + v.get("notes", "")}
        if model == "pinhole" and known and v.get("intrinsics") and v.get("world_to_cv_camera_R") is not None:
            R = np.array(v["world_to_cv_camera_R"], dtype=float) @ RZ180.T
            nv["camera_cv"] = {**{k: v["intrinsics"][k] for k in ("fx", "fy", "cx", "cy")},
                               "R_world_to_cv": R.round(12).tolist(), "t_world_to_cv": list(v["world_to_cv_camera_t"])}
            log.append(f"- view `{v['id']}` R_world_to_cv right-multiplied by Rz(180)^T")
        views.append(nv)
    srcs = [{"id": r["id"], "relative_path": r["relative_path"], "sha256": r["sha256"], "origin": "unknown",
             "rights_note": f"v1 rights_status={r.get('rights_status', 'unknown')}. {r.get('notes', '')}".strip()} for r in v1["source_references"]]
    probe = {"components": comps}
    top = 0.0
    for _, vw, _ in meshgen.scene_meshes(probe):
        top = max(top, float(vw[:, 2].max()))
    height = round(top, 4) if top > 0 else 1.0
    v2 = {
        "schema_version": "2.0.0", "character_id": v1["character_id"],
        "design_version": "migrated-from-v1", "package_mode": "SPEC_ONLY",
        "scale": {"mode": v1["scale_mode"], "unit": v1["unit"], "character_height": height,
                  "anchor_note": "character_height = top of migrated geometry"},
        "coordinate_system": "BLENDER_Z_UP_FACING_NEG_Y_X_LEFT",
        "root_anchor": v1["root_anchor"],
        "canvas": Canvas(world_size=round(1.4 * height, 4), center_z=round(0.5 * height, 4)).as_dict(),
        "source_references": srcs, "views": views, "materials": v1["materials"], "components": comps,
        "decisions": [], "unresolved_issues": list(v1.get("unresolved_issues", [])),
        "notes": "Migrated from schema 1.0.0. package_mode reset to SPEC_ONLY: rebuild and re-verify before any higher claim.",
    }
    if approved:
        v2["decisions"].append({"id": "D-MIGRATED-V1", "gate": "G2", "decided_by": "v1 spec label (not re-confirmed)",
                                "summary": "Values labelled approved_design in the v1 spec were carried over unchanged. "
                                           "No new approval is implied; the owner should re-confirm.", "affects": approved})
    if v1.get("package_mode") != "SPEC_ONLY":
        log.append(f"- package_mode {v1['package_mode']} -> SPEC_ONLY (evidence must be regenerated)")
    return v2, log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    a = ap.parse_args(argv)
    v1 = json.loads(a.old.read_text(encoding="utf-8"))
    try:
        v2, log = migrate(v1)
    except ValueError as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    a.new.parent.mkdir(parents=True, exist_ok=True)
    a.new.write_text(json.dumps(v2, indent=2) + "\n", encoding="utf-8")
    (a.new.parent / "MIGRATION_LOG.md").write_text("# Migration v1.0.0 -> v2.0.0\n\n" + ("\n".join(log) or "- no numeric changes") + "\n", encoding="utf-8")
    print(f"MIGRATED {a.old} -> {a.new} ({len(log)} logged changes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
