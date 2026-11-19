#!/usr/bin/env python3
"""G6 package: validate, write manifest.json, and create a byte-reproducible ZIP.

    python pack.py WORKSPACE OUT.zip [--allow-fail]

Runs check_spec first and refuses to pack a failing spec unless --allow-fail
(the manifest then records spec_check FAIL). The manifest lists every file with
SHA-256 and size, the package_mode claim, the geometry hash and open issue counts.
Symlinks are rejected; the ZIP must be outside the workspace.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_spec import evaluate  # noqa: E402
from mascot_lib.workspace import geometry_hash, load_spec, save_json, sha256_file  # noqa: E402


def pack(ws: Path, dest: Path, allow_fail: bool = False) -> tuple[Path, dict]:
    ws, dest = ws.resolve(), dest.resolve()
    if ws in dest.parents:
        raise ValueError("ZIP must be written outside the workspace")
    for req in ("HANDOFF.md", "OPEN_ISSUES.md", "04_build/build_spec.json"):
        if not (ws / req).is_file():
            raise ValueError(f"missing required file {req}")
    errors, warnings = evaluate(ws / "04_build" / "build_spec.json")
    if errors and not allow_fail:
        raise ValueError("spec check FAILED: " + "; ".join(errors[:5]))
    spec, _ = load_spec(ws)
    files = []
    for f in sorted(ws.rglob("*")):
        if f.is_symlink():
            raise ValueError(f"symlink not allowed: {f}")
        if f.is_file() and f.name != "manifest.json":
            files.append({"path": f.relative_to(ws).as_posix(), "sha256": sha256_file(f), "size_bytes": f.stat().st_size})
    issues = spec.get("unresolved_issues", [])
    manifest = {
        "manifest_version": "2.0.0", "package_id": ws.name, "character_id": spec["character_id"],
        "design_version": spec.get("design_version"), "package_mode_claim": spec["package_mode"],
        "geometry_hash": geometry_hash(spec), "spec_check": "FAIL" if errors else "PASS",
        "spec_check_errors": errors, "spec_check_warnings": warnings,
        "open_issues": {s: sum(1 for i in issues if isinstance(i, dict) and i.get("severity") == s) for s in ("blocking", "major", "minor", "info")},
        "files": files,
    }
    save_json(ws / "manifest.json", manifest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(ws.rglob("*")):
            if f.is_file():
                zi = zipfile.ZipInfo(f"{ws.name}/{f.relative_to(ws).as_posix()}", (1980, 1, 1, 0, 0, 0))
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o100644 << 16
                z.writestr(zi, f.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return dest, manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("dest", type=Path)
    ap.add_argument("--allow-fail", action="store_true")
    a = ap.parse_args(argv)
    try:
        out, man = pack(a.workspace, a.dest, a.allow_fail)
    except (ValueError, OSError) as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    print(f"PACKED {out} | {len(man['files'])} files | mode={man['package_mode_claim']} | spec_check={man['spec_check']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
