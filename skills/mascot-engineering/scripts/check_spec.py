#!/usr/bin/env python3
"""Validate a build_spec v2 (schema + structure + evidence + honesty of the release label).

    python check_spec.py WORKSPACE_OR_SPEC [--json]

Exit 0 = PASS (warnings allowed), 1 = FAIL.
Checks: JSON schema; unique ids incl. mirror twins; parents exist; no cycles;
materials exist; evidence ids resolve (views, sources, measurements, decisions);
`observed` has evidence, `approved_design` cites a decision; every component mesh is
closed, manifold and outward-facing; source files exist and match their SHA-256;
mirrored parts vs measured asymmetry; and the package_mode claim:
  BLOCKOUT_READY  needs release_evidence.blender_build_log whose geometry_hash equals
                  this spec's geometry hash (proves the CURRENT spec was built) and
                  no blocking issues.
  PRODUCTION_READY additionally needs an owner G6 decision; this tool never certifies it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mascot_lib import meshgen  # noqa: E402
from mascot_lib.workspace import geometry_hash, sha256_file, workspace_of  # noqa: E402

SCHEMA = HERE.parent / "schemas" / "build_spec.schema.json"


def evaluate(spec_file: Path):
    errors, warnings = [], []
    spec_file = Path(spec_file)
    if spec_file.is_dir():
        spec_file = spec_file / "04_build" / "build_spec.json"
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"cannot read spec: {e}"], []
    ws = workspace_of(spec_file)
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema not installed (pip install jsonschema): schema NOT validated"], []
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    for err in sorted(Draft202012Validator(schema).iter_errors(spec), key=lambda e: [str(p) for p in e.path]):
        errors.append(f"SCHEMA {'/'.join(str(p) for p in err.path) or 'root'}: {err.message[:300]}")
    if errors:
        return errors, warnings

    if (spec["scale"]["mode"], spec["scale"]["unit"]) not in {("relative", "normalized"), ("metric", "m")}:
        errors.append("scale.mode/unit mismatch: use relative+normalized or metric+m")
    src_ids = {r["id"] for r in spec["source_references"]}
    view_ids = {v["id"] for v in spec["views"]}
    mat_ids = [m["id"] for m in spec["materials"]]
    dec_ids = {d["id"] for d in spec.get("decisions", [])}
    mpath = ws / "03_geometry" / "MEASUREMENTS.json"
    meas_ids = set()
    if mpath.exists():
        meas_ids = {m["id"] for m in json.loads(mpath.read_text(encoding="utf-8")).get("measurements", [])}
    for name, ids in (("source", [r["id"] for r in spec["source_references"]]), ("view", [v["id"] for v in spec["views"]]), ("material", mat_ids)):
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate {name} ids")
    for v in spec["views"]:
        if v["source_reference_id"] is not None and v["source_reference_id"] not in src_ids:
            errors.append(f"view {v['id']}: unknown source {v['source_reference_id']}")
        if v["kind"] == "other" and v["role"] == "canonical":
            warnings.append(f"view {v['id']}: kind 'other' cannot be measured; role canonical has no effect")
    for kind in ("front", "back", "left", "right"):
        n = sum(1 for v in spec["views"] if v["kind"] == kind and v["role"] == "canonical")
        if n > 1:
            errors.append(f"{n} canonical '{kind}' views: choose one (others -> supporting/rejected) and record a decision")

    comps = meshgen.expand_components(spec["components"])
    ids = [c["id"] for c in comps]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"duplicate component ids (mirror twins included): {sorted(dup)}")
    by_id = {c["id"]: c for c in comps}
    for c in spec["components"]:
        cid = c["id"]
        if c["parent_id"] == cid:
            errors.append(f"{cid}: self-parent")
        elif c["parent_id"] is not None and c["parent_id"] not in by_id:
            errors.append(f"{cid}: unknown parent {c['parent_id']}")
        if c["material_id"] not in mat_ids:
            errors.append(f"{cid}: unknown material {c['material_id']}")
        ev = c["evidence"]
        known = src_ids | view_ids | meas_ids | dec_ids
        for r in ev["reference_ids"]:
            if r not in known:
                errors.append(f"{cid}: evidence reference {r!r} is not a known view/source/measurement/decision id")
        if ev["status"] == "observed" and not (set(ev["reference_ids"]) & (view_ids | meas_ids)):
            errors.append(f"{cid}: status 'observed' but no view or measurement cited")
        if ev["status"] == "approved_design" and ev.get("decision_id") not in dec_ids:
            errors.append(f"{cid}: status 'approved_design' needs evidence.decision_id pointing at decisions[]")
        if ev["status"] in ("inferred", "proposed") and not ev.get("uncertainty_note"):
            warnings.append(f"{cid}: {ev['status']} geometry without uncertainty_note")
        g = c["geometry"]
        if g["type"] == "revolved_profile":
            zs = [p[1] for p in g["profile"]]
            if any(p[0] < 0 for p in g["profile"]):
                errors.append(f"{cid}: negative radius in profile")
            if any(b <= a for a, b in zip(zs, zs[1:])):
                errors.append(f"{cid}: profile z must be strictly increasing")
        if g["type"] == "elliptical_loft":
            zs = [s[0] for s in g["stations"]]
            if any(b <= a for a, b in zip(zs, zs[1:])):
                errors.append(f"{cid}: loft station z must be strictly increasing")
            if any(s[2] < 0 or s[4] < 0 for s in g["stations"]):
                errors.append(f"{cid}: loft half-width/half-depth must be >= 0")
    if not errors:
        try:
            meshgen.world_matrices(comps)
        except (ValueError, KeyError) as e:
            errors.append(f"transform graph: {e}")
    if not errors:
        for c in comps:
            try:
                v, f = meshgen.component_mesh(c)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{c['id']}: mesh generation failed: {e}")
                continue
            if not meshgen.is_closed_manifold(f):
                errors.append(f"{c['id']}: mesh is not closed/manifold")
            elif meshgen.mesh_volume(v, f) <= 0:
                errors.append(f"{c['id']}: mesh faces point inward (negative volume)")

    for r in spec["source_references"]:
        rel = Path(r["relative_path"])
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"source {r['id']}: unsafe path")
            continue
        p = ws / rel
        if not p.is_file():
            errors.append(f"source {r['id']}: missing file {rel}")
        elif sha256_file(p) != r["sha256"]:
            errors.append(f"source {r['id']}: checksum mismatch (reference image was modified)")
        if r["origin"] in ("third_party", "unknown") and not r.get("rights_note"):
            warnings.append(f"source {r['id']}: origin {r['origin']} with no rights_note")

    cons = ws / "02_views" / "CONSISTENCY.json"
    if cons.exists() and not errors:
        sym = next((c for c in json.loads(cons.read_text(encoding="utf-8"))["checks"] if c["check"] == "front_left_right_symmetry"), None)
        if sym and sym.get("bands"):
            W = meshgen.world_matrices(comps)
            for c in spec["components"]:
                if not c.get("mirror"):
                    continue
                v, _ = meshgen.component_mesh(c)
                M = W[c["id"]]
                z = (v @ M[:3, :3].T + M[:3, 3])[:, 2]
                for b in sym["bands"]:
                    if b["z_from"] <= z.max() and b["z_to"] >= z.min():
                        warnings.append(f"{c['id']}: mirrored, but the front view is asymmetric at z {b['z_from']}-{b['z_to']}; confirm with a decision")
                        break

    blocking = [i for i in spec["unresolved_issues"] if isinstance(i, dict) and i.get("severity") == "blocking"]
    mode = spec["package_mode"]
    if mode != "SPEC_ONLY":
        if blocking:
            errors.append(f"{mode} claimed with {len(blocking)} blocking issue(s) open")
        if not spec["components"]:
            errors.append(f"{mode} claimed with no components")
        log_rel = spec.get("release_evidence", {}).get("blender_build_log")
        if not log_rel:
            errors.append(f"{mode} claimed without release_evidence.blender_build_log")
        else:
            lp = ws / log_rel
            if not lp.is_file():
                errors.append(f"build log not found: {log_rel}")
            else:
                log = json.loads(lp.read_text(encoding="utf-8"))
                if log.get("status") != "SUCCESS":
                    errors.append("build log status is not SUCCESS")
                if log.get("geometry_hash") != geometry_hash(spec):
                    errors.append("build log was produced from a DIFFERENT spec (geometry hash mismatch): rebuild")
        cmp_rel = spec.get("release_evidence", {}).get("compare_report")
        if not cmp_rel or not (ws / cmp_rel).is_file():
            warnings.append(f"{mode}: no silhouette compare report linked (release_evidence.compare_report)")
        elif json.loads((ws / cmp_rel).read_text(encoding="utf-8")).get("overall") != "PASS":
            warnings.append(f"{mode}: linked compare report is not PASS; an owner decision must accept the differences")
    if mode == "PRODUCTION_READY":
        if not any(d.get("gate") == "G6" and d.get("decided_by") for d in spec.get("decisions", [])):
            errors.append("PRODUCTION_READY needs an owner G6 decision (decisions[] with gate G6 and decided_by)")
        warnings.append("PRODUCTION_READY is an owner claim; this validator cannot certify rig, materials or animation quality")
    if not spec["source_references"]:
        warnings.append("no reference images registered (synthetic or design-only spec)")
    return errors, warnings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    errs, warns = evaluate(a.spec.resolve())
    if a.json:
        print(json.dumps({"status": "FAIL" if errs else "PASS", "errors": errs, "warnings": warns}, indent=2))
    else:
        for w in warns:
            print("WARN:", w)
        for e in errs:
            print("ERROR:", e)
        print(f"SPEC CHECK: {'FAIL' if errs else 'PASS'} ({len(errs)} errors, {len(warns)} warnings)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
