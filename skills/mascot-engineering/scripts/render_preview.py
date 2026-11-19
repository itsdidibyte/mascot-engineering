#!/usr/bin/env python3
"""Fast Blender-free preview: render the build spec on the canonical canvas for each measured view.

    python render_preview.py WORKSPACE [--spec PATH] [--views front,right] [--out-dir DIR]

Writes 04_build/preview/<view_id>_mask.png and <view_id>_shaded.png using the same
meshes Blender would build (mascot_lib.meshgen). Subdivision modifiers are not
simulated. Use it for quick iterations; use blender_build.py for the .blend and
authoritative renders.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

from mascot_lib import raster  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402
from mascot_lib.workspace import load_spec  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--spec", type=Path, default=None)
    ap.add_argument("--views", default=None, help="comma-separated view ids (default: all measured views)")
    ap.add_argument("--out-dir", type=Path, default=None)
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, _ = load_spec(a.spec or ws)
    if not spec["components"]:
        print("ERROR: spec has no components", file=sys.stderr)
        return 2
    canvas = Canvas.from_dict(spec.get("canvas"))
    out = (a.out_dir or ws / "04_build" / "preview").resolve()
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(a.views.split(",")) if a.views else None
    n = 0
    for v in spec["views"]:
        if v["kind"] not in ("front", "back", "left", "right") or v.get("normalization") is None:
            continue
        if wanted and v["id"] not in wanted:
            continue
        mask, rgba = raster.render_view(spec, v["kind"], canvas, shaded=True)
        Image.fromarray(mask).save(out / f"{v['id']}_mask.png")
        Image.fromarray(rgba, "RGBA").save(out / f"{v['id']}_shaded.png")
        n += 1
        print(f"PREVIEW {v['id']} ({v['kind']}) -> {out}")
    if n == 0:
        print("ERROR: no measured views to render (run silhouettes.py first)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
