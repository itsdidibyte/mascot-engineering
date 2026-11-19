"""Blender-free orthographic preview renderer (numpy + Pillow).

Renders a build spec onto the canonical canvas for a view kind, giving a
binary silhouette mask (for compare.py) and a simple flat-shaded colour
preview (painter's algorithm, Lambert). It is a fast stand-in for Blender
during iteration and in tests; the Blender build remains the authority for
the .blend file. Subdivision modifiers are NOT simulated.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from . import meshgen
from .views import Canvas, view_axes, world_to_view_hz


def _material_colors(spec):
    out = {}
    for m in spec.get("materials", []):
        r, g, b = m.get("base_color_rgba", [0.8, 0.8, 0.8, 1])[:3]
        out[m["id"]] = np.array([r, g, b], dtype=float)
    return out


def render_view(spec: dict, kind: str, canvas: Canvas, shaded: bool = True):
    """Return (mask uint8 HxW {0,255}, rgba uint8 HxWx4 or None)."""
    n = canvas.resolution_px
    mask = Image.new("L", (n, n), 0)
    mdraw = ImageDraw.Draw(mask)
    colors = _material_colors(spec)
    tri_records = []
    toward = view_axes(kind)[2]
    light = toward * 0.75 + np.array([0.0, 0.0, 0.66])
    light /= np.linalg.norm(light)
    for comp, vw, faces in meshgen.scene_meshes(spec):
        h, z, d = world_to_view_hz(vw, kind)
        col, row = canvas.to_pixel(h, z)
        tris = meshgen.triangulate(faces)
        for t in tris:
            pts = [(float(col[i]), float(row[i])) for i in t]
            mdraw.polygon(pts, fill=255)
        if shaded:
            a, b, c = vw[tris[:, 0]], vw[tris[:, 1]], vw[tris[:, 2]]
            nrm = np.cross(b - a, c - a)
            ln = np.linalg.norm(nrm, axis=1, keepdims=True)
            nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 0)
            facing = nrm @ toward
            depth = (d[tris[:, 0]] + d[tris[:, 1]] + d[tris[:, 2]]) / 3
            base = colors.get(comp.get("material_id"), np.array([0.8, 0.8, 0.8]))
            lam = np.clip(nrm @ light, 0, 1) * 0.75 + 0.25
            for k in np.nonzero(facing > 0)[0]:
                tri_records.append((float(depth[k]), [(float(col[i]), float(row[i])) for i in tris[k]],
                                    tuple(int(round(255 * min(1.0, v))) for v in base * lam[k])))
    mask_np = np.array(mask, dtype=np.uint8)
    if not shaded:
        return mask_np, None
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    tri_records.sort(key=lambda r: r[0])  # far (most negative toward-camera depth) first
    for _, pts, rgb in tri_records:
        draw.polygon(pts, fill=rgb + (255,))
    rgba = np.array(img, dtype=np.uint8)
    rgba[..., 3] = np.maximum(rgba[..., 3], 0)
    return mask_np, rgba
