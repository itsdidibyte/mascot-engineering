"""Synthetic ground truth: a known 3D mascot rendered into fake 'turnaround' images.

Used by the tests and by examples/blobby. Because the 3D truth is known, the
pipeline's measurements can be checked numerically (something no amount of
documentation can do).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

SKILL = Path(__file__).resolve().parents[1] / "skills" / "mascot-engineering"
sys.path.insert(0, str(SKILL / "scripts"))

from mascot_lib import raster  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402


def ev():
    return {"status": "approved_design", "method": "synthetic ground truth", "reference_ids": [], "decision_id": "D-TRUTH"}


def truth_spec(head_z: float = 0.78) -> dict:
    body = [[0.0, 0, 0.0, 0, 0.0], [0.02, 0, 0.16, 0, 0.14], [0.08, 0, 0.24, 0, 0.2], [0.18, 0, 0.27, 0, 0.23],
            [0.3, 0, 0.26, 0, 0.22], [0.42, 0, 0.23, 0, 0.2], [0.52, 0, 0.19, 0, 0.17], [0.6, 0, 0.14, 0, 0.13],
            [0.64, 0, 0.0, 0, 0.0]]
    return {
        "schema_version": "2.0.0", "character_id": "blobby", "design_version": "truth", "package_mode": "SPEC_ONLY",
        "scale": {"mode": "relative", "unit": "normalized", "character_height": 1.0},
        "coordinate_system": "BLENDER_Z_UP_FACING_NEG_Y_X_LEFT", "root_anchor": "ground centre",
        "canvas": Canvas().as_dict(), "source_references": [], "views": [],
        "materials": [{"id": "body", "base_color_rgba": [0.95, 0.6, 0.25, 1]},
                      {"id": "dark", "base_color_rgba": [0.08, 0.08, 0.1, 1]}],
        "components": [
            {"id": "body", "name": "body", "parent_id": None, "geometry": {"type": "elliptical_loft", "stations": body},
             "location": [0, 0, 0], "rotation_euler_deg": [0, 0, 0], "material_id": "body", "evidence": ev()},
            {"id": "head", "name": "head", "parent_id": None, "geometry": {"type": "ellipsoid", "radii": [0.24, 0.21, 0.2]},
             "location": [0, 0, head_z], "rotation_euler_deg": [0, 0, 0], "material_id": "body", "evidence": ev()},
            {"id": "ear_l", "name": "ear L", "parent_id": "head", "geometry": {"type": "ellipsoid", "radii": [0.05, 0.03, 0.09]},
             "location": [0.15, 0.0, 1.0 - 0.09 - head_z], "rotation_euler_deg": [0, 0, 0], "material_id": "body",
             "mirror": {"id": "ear_r"}, "evidence": ev()},
            {"id": "eye_l", "name": "eye L", "parent_id": "head", "geometry": {"type": "ellipsoid", "radii": [0.03, 0.02, 0.05]},
             "location": [0.08, -0.19, 0.02], "rotation_euler_deg": [0, 0, 0], "material_id": "dark",
             "mirror": {"id": "eye_r"}, "evidence": ev()},
            {"id": "arm_l", "name": "arm L", "parent_id": None, "geometry": {"type": "capsule", "radius": 0.045, "length": 0.16},
             "location": [0.3, 0.0, 0.4], "rotation_euler_deg": [0, 35, 0], "material_id": "body",
             "mirror": {"id": "arm_r"}, "evidence": ev()},
            {"id": "foot_l", "name": "foot L", "parent_id": None, "geometry": {"type": "ellipsoid", "radii": [0.08, 0.11, 0.04]},
             "location": [0.11, -0.03, 0.04], "rotation_euler_deg": [0, 0, 0], "material_id": "body",
             "mirror": {"id": "foot_r"}, "evidence": ev()},
        ],
        "decisions": [{"id": "D-TRUTH", "gate": "G2", "summary": "synthetic truth", "decided_by": "test"}],
        "unresolved_issues": [],
    }


def fake_reference(spec: dict, kind: str, out: Path, char_px: int, size=(1024, 1100), offset=(0, 0), bg=(255, 255, 255)):
    """Render a view and paste it, rescaled, on a plain background like an AI turnaround image."""
    canvas = Canvas(resolution_px=2048)
    mask, rgba = raster.render_view(spec, kind, canvas, shaded=True)
    ys, xs = np.nonzero(mask)
    crop = Image.fromarray(rgba, "RGBA").crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    s = char_px / crop.height
    crop = crop.resize((max(1, round(crop.width * s)), char_px), Image.LANCZOS)
    img = Image.new("RGB", size, bg)
    x = (size[0] - crop.width) // 2 + offset[0]
    y = (size[1] - crop.height) // 2 + offset[1]
    img.paste(crop, (x, y), crop)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def make_refs(dest: Path, spec: dict | None = None, side_spec: dict | None = None) -> dict:
    spec = spec or truth_spec()
    side_spec = side_spec or spec
    return {
        "front": fake_reference(spec, "front", dest / "front.png", 900, (1024, 1100), (10, 5)),
        "right": fake_reference(side_spec, "right", dest / "side.png", 760, (900, 1000), (-30, 20)),
        "back": fake_reference(spec, "back", dest / "back.png", 940, (1100, 1100), (0, -10)),
    }
