#!/usr/bin/env python3
"""G0 intake: create (or extend) a character workspace from labelled reference images.

    python intake.py WORKSPACE --id my_mascot \
        --view front=refs/front.png --view right=refs/side.png --view back=refs/back.png \
        [--origin ai_generated] [--height 1.0] [--add]

View kinds: front, back, left, right (measured turnaround views);
three_quarter_left / three_quarter_right (3/4 views: NOT used to build, used as a
held-out check by check_three_quarter.py; name them by where the nose points);
other (close-ups, expressions: visual reference only).
Side views: name the view after the way the NOSE points in the picture
(nose toward image-right -> "right", toward image-left -> "left").

The images are copied into 01_references/ (originals untouched), hashed, and
registered in 04_build/build_spec.json (schema 2.0.0, package_mode SPEC_ONLY).
Nothing about geometry, camera or rights is inferred.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mascot_lib import SCHEMA_VERSION  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402
from mascot_lib.workspace import FOLDERS, append_issue, load_spec, save_json, sha256_file, spec_path  # noqa: E402

KINDS = ("front", "back", "left", "right", "three_quarter_left", "three_quarter_right", "other")
EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
ORIGINS = ("ai_generated", "hand_drawn", "render_3d", "photo", "third_party", "unknown")


def parse_view(arg: str):
    if "=" not in arg:
        raise ValueError(f"--view expects kind=path, got {arg!r}")
    kind, path = arg.split("=", 1)
    kind = kind.strip().lower()
    if kind not in KINDS:
        raise ValueError(f"Unknown view kind {kind!r}; use one of {KINDS}")
    p = Path(path).expanduser().resolve()
    if not p.is_file() or p.suffix.lower() not in EXT:
        raise ValueError(f"Not a supported image file: {p}")
    return kind, p


def new_spec(character_id: str, height: float) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "character_id": character_id,
        "design_version": "UNSET: name the approved design version (e.g. v1-2026-11-19)",
        "package_mode": "SPEC_ONLY",
        "scale": {"mode": "relative", "unit": "normalized", "character_height": height,
                  "anchor_note": "Height of the character in the canonical views = character_height. No physical size claimed."},
        "coordinate_system": "BLENDER_Z_UP_FACING_NEG_Y_X_LEFT",
        "root_anchor": "Ground contact centre: Z=0 at the lowest silhouette point; X=0 on the front-view bbox centre; Y=0 on the side-view bbox centre.",
        "canvas": Canvas().as_dict(),
        "source_references": [],
        "views": [],
        "materials": [],
        "components": [],
        "decisions": [],
        "unresolved_issues": [],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--id", required=True, help="lowercase slug, e.g. blob_mascot")
    ap.add_argument("--view", action="append", default=[], help="kind=path (repeatable)")
    ap.add_argument("--origin", default="unknown", choices=ORIGINS, help="how the reference images were made")
    ap.add_argument("--rights-note", default="Not stated by owner.", help="free text: who owns / may use these images")
    ap.add_argument("--height", type=float, default=1.0, help="character height in relative units (default 1.0)")
    ap.add_argument("--add", action="store_true", help="add views to an existing workspace")
    a = ap.parse_args(argv)

    if not re.fullmatch(r"[a-z][a-z0-9_-]*", a.id):
        print("ERROR: --id must be a lowercase slug", file=sys.stderr)
        return 2
    try:
        views = [parse_view(v) for v in a.view]
    except ValueError as e:
        print("ERROR:", e, file=sys.stderr)
        return 2
    if not views:
        print("ERROR: give at least one --view kind=path", file=sys.stderr)
        return 2

    ws = a.workspace.resolve()
    if spec_path(ws).exists():
        if not a.add:
            print(f"ERROR: workspace already initialised: {ws} (use --add to register more views)", file=sys.stderr)
            return 2
        spec, _ = load_spec(ws)
        if spec["character_id"] != a.id:
            print("ERROR: --id differs from the existing workspace character_id", file=sys.stderr)
            return 2
    else:
        if ws.exists() and any(ws.iterdir()):
            print(f"ERROR: {ws} exists and is not empty", file=sys.stderr)
            return 2
        spec = new_spec(a.id, a.height)
    for d in FOLDERS:
        (ws / d).mkdir(parents=True, exist_ok=True)

    from PIL import Image
    existing_ids = {v["id"] for v in spec["views"]}
    existing_hash = {r["sha256"]: r["id"] for r in spec["source_references"]}
    added = []
    for kind, src in views:
        digest = sha256_file(src)
        if digest in existing_hash:
            print(f"SKIP {src.name}: identical file already registered as {existing_hash[digest]}")
            continue
        n = 1
        vid = kind
        while vid in existing_ids:
            n += 1
            vid = f"{kind}_{n}"
        with Image.open(src) as im:
            w, h = im.size
            mode = im.mode
            im.verify()
        rel = Path("01_references") / f"{vid}{src.suffix.lower()}"
        shutil.copy2(src, ws / rel)
        ref_id = f"src_{vid}"
        spec["source_references"].append({
            "id": ref_id, "relative_path": rel.as_posix(), "sha256": digest,
            "original_filename": src.name, "image_size_px": [w, h], "color_mode": mode,
            "origin": a.origin, "rights_note": a.rights_note,
        })
        role = "canonical" if not any(v["kind"] == kind and v.get("role") == "canonical" for v in spec["views"]) else "supporting"
        if kind == "other":
            role = "supporting"
        spec["views"].append({
            "id": vid, "source_reference_id": ref_id, "kind": kind,
            "projection": "orthographic_assumed" if kind != "other" else "perspective_unknown",
            "role": role, "normalization": None,
            "notes": "Projection is ASSUMED orthographic (typical for turnaround sheets). Change to perspective_unknown if the picture shows obvious perspective.",
        })
        existing_ids.add(vid)
        existing_hash[digest] = ref_id
        added.append((vid, kind, role, w, h))

    kinds = {v["kind"] for v in spec["views"] if v.get("role") == "canonical"}
    if "front" not in kinds and "back" not in kinds:
        append_issue(spec, "G0", "blocking", "No front or back view: widths cannot be measured.")
    if not ({"left", "right"} & kinds):
        append_issue(spec, "G0", "major", "No side view: all depths (Y) will be PROPOSED, not observed. Ask the owner for a side view.")
    if a.origin in ("third_party", "unknown"):
        append_issue(spec, "G0", "minor", f"Reference origin is '{a.origin}'. Record who owns the design before commercial use.")

    save_json(spec_path(ws), spec)
    save_json(ws / "00_intake" / "SOURCE_REGISTER.json", spec["source_references"])
    log = ws / "00_intake" / "INTAKE_LOG.md"
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n## Intake {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n\n")
        for vid, kind, role, w, h in added:
            f.write(f"- `{vid}` kind={kind} role={role} size={w}x{h}px\n")
    for name, body in (("OPEN_ISSUES.md", "# Open issues\n\nSee `unresolved_issues` in 04_build/build_spec.json (machine-readable source of truth).\n"),
                       ("DECISIONS.md", "# Decisions\n\nOne entry per owner decision: ID, gate, date, what was decided, which files it affects.\n"),
                       ("HANDOFF.md", f"# Handoff: {a.id}\n\nStatus: SPEC_ONLY. Run the mascot-engineering skill on this folder to continue.\n")):
        p = ws / name
        if not p.exists():
            p.write_text(body, encoding="utf-8")
    print(f"INTAKE OK: {ws} | added {len(added)} view(s): " + ", ".join(f"{v}({k},{r})" for v, k, r, _, _ in added))
    return 0


if __name__ == "__main__":
    sys.exit(main())
