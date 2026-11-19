#!/usr/bin/env python3
"""Silhouette-consistent envelope ("visual hull") from the orthographic reference masks.

    python visual_hull.py WORKSPACE [--res 160]

A voxel is kept only if it falls inside EVERY canonical measured silhouette
(front, back, left, right). The result is the largest shape the drawings allow:
the true character lies inside it, concavities (e.g. between arms and body seen
from no view) are NOT carved. Use it as (1) an instant 3D look at the references,
(2) a reference object in Blender, (3) a sanity check that views agree (if the hull
reprojects with low IoU in some view, the views contradict each other).

Writes 03_geometry/visual_hull.npz (verts, faces; Blender Z-up world coords),
visual_hull.obj (OBJ Y-up convention: imports upright in Blender with default
settings) and HULL_REPORT.json with reprojection IoU per view.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from mascot_lib import raster, silhouette  # noqa: E402
from mascot_lib.views import Canvas, view_axes  # noqa: E402
from mascot_lib.workspace import load_spec, save_json, view_by_kind  # noqa: E402


def voxel_surface(occ: np.ndarray, origin, step):
    """Boxy surface quads of an occupancy grid (fallback when scikit-image is missing)."""
    verts, faces, index = [], [], {}

    def vid(p):
        if p not in index:
            index[p] = len(verts)
            verts.append(p)
        return index[p]
    nx, ny, nz = occ.shape
    pad = np.pad(occ, 1)
    dirs = [((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]), ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
            ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]), ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]),
            ((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]), ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)])]
    for (dx, dy, dz), corners in dirs:
        nb = pad[1 + dx:1 + dx + nx, 1 + dy:1 + dy + ny, 1 + dz:1 + dz + nz]
        for i, j, k in zip(*np.nonzero(occ & ~nb)):
            faces.append(tuple(vid((int(i + c[0]), int(j + c[1]), int(k + c[2]))) for c in corners))
    v = np.array(verts, dtype=float) * step + origin
    return v, faces


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workspace", type=Path)
    ap.add_argument("--res", type=int, default=160, help="voxels along the canvas edge")
    a = ap.parse_args(argv)
    ws = a.workspace.resolve()
    spec, _ = load_spec(ws)
    canvas = Canvas.from_dict(spec.get("canvas"))
    masks = {}
    for k in ("front", "back", "left", "right"):
        v = view_by_kind(spec, k)
        p = ws / "02_views" / f"{v['id']}_mask.png" if v else None
        if p and p.exists():
            masks[k] = (v["id"], np.array(Image.open(p).convert("L")) >= 128)
    if not ({"front", "back"} & masks.keys()) or not ({"left", "right"} & masks.keys()):
        print("ERROR: need a measured front/back AND a measured side view", file=sys.stderr)
        return 2
    n = a.res
    step = canvas.world_size / n
    c = (np.arange(n) + 0.5) * step
    xs = canvas.center_h - canvas.world_size / 2 + c
    ys = canvas.center_h - canvas.world_size / 2 + c
    zs = canvas.center_z - canvas.world_size / 2 + c
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing="ij")
    occ = np.ones(X.shape, dtype=bool)
    pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    for k, (_, m) in masks.items():
        ax = view_axes(k)
        h = pts @ ax[0]
        zz = pts @ ax[1]
        col, row = canvas.to_pixel(h, zz)
        col = np.clip(np.floor(col).astype(int), 0, m.shape[1] - 1)
        row = np.clip(np.floor(row).astype(int), 0, m.shape[0] - 1)
        occ &= m[row, col].reshape(X.shape)
    origin = np.array([xs[0], ys[0], zs[0]]) - step / 2
    try:
        from skimage import measure
        vol = np.pad(occ.astype(np.float32), 1)
        verts, faces, _, _ = measure.marching_cubes(vol, 0.5)
        verts = (verts - 1) * step + origin + step / 2
        faces = [tuple(int(i) for i in f[::-1]) for f in faces]
        method = "marching_cubes (scikit-image)"
    except ImportError:
        verts, faces = voxel_surface(occ, origin, step)
        method = "voxel faces (install scikit-image for a smooth surface)"
    out = ws / "03_geometry"
    out.mkdir(parents=True, exist_ok=True)
    flat = np.array([list(f) for f in faces], dtype=np.int64)
    np.savez_compressed(out / "visual_hull.npz", verts=verts, faces=flat)
    with open(out / "visual_hull.obj", "w", encoding="utf-8") as f:
        f.write("# visual hull; OBJ Y-up (Blender default import restores Z-up)\n")
        for x, y, z in verts:
            f.write(f"v {x:.5f} {z:.5f} {-y:.5f}\n")
        for face in faces:
            f.write("f " + " ".join(str(i + 1) for i in face) + "\n")
    hull_spec = {"components": [{"id": "hull", "parent_id": None, "location": [0, 0, 0], "rotation_euler_deg": [0, 0, 0],
                                 "material_id": "x", "geometry": {"type": "_mesh"}}], "materials": []}
    report = {"method": method, "voxels": int(occ.sum()), "voxel_size": step,
              "volume_units3": float(occ.sum() * step ** 3), "reprojection_iou": {}}
    # reprojection check with the generic rasteriser
    from mascot_lib import meshgen
    orig_build = meshgen.build_geometry

    def build(geo):
        if geo["type"] == "_mesh":
            return verts, faces
        return orig_build(geo)
    meshgen.build_geometry = build
    try:
        for k, (vid, m) in masks.items():
            rm, _ = raster.render_view(hull_spec, k, canvas, shaded=False)
            report["reprojection_iou"][vid] = round(silhouette.iou(m, rm >= 128), 4)
    finally:
        meshgen.build_geometry = orig_build
    save_json(out / "HULL_REPORT.json", report)
    print(f"HULL {method}: {report['voxels']} voxels, reprojection IoU {report['reprojection_iou']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
