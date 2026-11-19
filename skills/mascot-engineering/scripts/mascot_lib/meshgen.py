"""Deterministic, closed, manifold meshes for every geometry type in build_spec v2.

The SAME functions feed the Blender builder (via mesh.from_pydata) and the
Blender-free preview rasteriser, so a numpy preview and a Blender render of a
spec describe identical geometry. numpy only.

Geometry types (local frame, metres or normalised units):
    ellipsoid        radii [rx, ry, rz]
    superellipsoid   radii [rx, ry, rz], exponents [e_horizontal, e_vertical] (2 = round, >2 boxier)
    box              dimensions [x, y, z]
    cylinder         radius, depth (along local Z, centred)
    capsule          radius, length (straight part, along local Z, centred); optional radius_top
    revolved_profile profile [[radius, z], ...] revolved around local Z (z strictly increasing)
    elliptical_loft  stations [[z, cx, a, cy, b], ...]: at height z a superellipse centred (cx, cy)
                     with half-width a along X and half-depth b along Y. Exponent "n" (default 2).
"""
from __future__ import annotations

import math

import numpy as np

EPS = 1e-9


# --------------------------------------------------------------------------- helpers

def _ring(n: int) -> np.ndarray:
    t = 2 * math.pi * np.arange(n) / n
    return np.stack([np.cos(t), np.sin(t)], axis=1)


def _superellipse_ring(n_seg: int, exponent: float) -> np.ndarray:
    """Unit superellipse |x|^n + |y|^n = 1 sampled at n_seg angles (n=2 -> circle)."""
    t = 2 * math.pi * np.arange(n_seg) / n_seg
    c, s = np.cos(t), np.sin(t)
    p = 2.0 / exponent
    return np.stack([np.sign(c) * np.abs(c) ** p, np.sign(s) * np.abs(s) ** p], axis=1)


def _stack_rings(rings: list[np.ndarray], bottom_pole=None, top_pole=None):
    """Connect equal-length rings (each Kx3, ordered counter-clockwise seen from +Z) into a closed mesh.

    If bottom_pole/top_pole is None the end is closed with a centre fan.
    Faces are quads between rings and triangles in fans, all wound outward.
    """
    k = len(rings[0])
    verts: list = []
    faces: list = []
    if bottom_pole is None:
        bottom_pole = rings[0].mean(axis=0)
        bottom_is_cap = True
    else:
        bottom_is_cap = False
    if top_pole is None:
        top_pole = rings[-1].mean(axis=0)
    verts.append(np.asarray(bottom_pole, dtype=float))
    base = 1
    for r in rings:
        verts.extend(np.asarray(r, dtype=float))
    top_index = len(verts)
    verts.append(np.asarray(top_pole, dtype=float))
    # bottom fan (outward = -Z, so clockwise seen from +Z)
    for i in range(k):
        j = (i + 1) % k
        faces.append((0, base + j, base + i))
    for ri in range(len(rings) - 1):
        a0 = base + ri * k
        b0 = base + (ri + 1) * k
        for i in range(k):
            j = (i + 1) % k
            faces.append((a0 + i, a0 + j, b0 + j, b0 + i))
    last = base + (len(rings) - 1) * k
    for i in range(k):
        j = (i + 1) % k
        faces.append((last + i, last + j, top_index))
    del bottom_is_cap
    return np.array(verts, dtype=float), faces


# --------------------------------------------------------------------------- primitives

def ellipsoid(radii, segments: int = 48, rings: int = 24):
    return superellipsoid(radii, (2.0, 2.0), segments, rings)


def superellipsoid(radii, exponents=(2.0, 2.0), segments: int = 48, rings: int = 24):
    rx, ry, rz = (float(v) for v in radii)
    e_h, e_v = (float(v) for v in exponents)
    ring_xy = _superellipse_ring(segments, e_h)
    rows = []
    p_v = 2.0 / e_v
    for i in range(1, rings):
        phi = -math.pi / 2 + math.pi * i / rings
        c, s = math.cos(phi), math.sin(phi)
        scale = abs(c) ** p_v
        z = math.copysign(abs(s) ** p_v, s) * rz
        rows.append(np.column_stack([ring_xy[:, 0] * rx * scale, ring_xy[:, 1] * ry * scale, np.full(segments, z)]))
    return _stack_rings(rows, bottom_pole=(0, 0, -rz), top_pole=(0, 0, rz))


def box(dimensions):
    x, y, z = (float(v) / 2 for v in dimensions)
    verts = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z],
                      [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]], dtype=float)
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return verts, faces


def cylinder(radius, depth, vertices: int = 48):
    r = float(radius)
    h = float(depth) / 2
    ring = _ring(vertices) * r
    rows = [np.column_stack([ring, np.full(vertices, -h)]), np.column_stack([ring, np.full(vertices, h)])]
    return _stack_rings(rows)


def capsule(radius, length, segments: int = 32, cap_rings: int = 8, radius_top=None):
    r0 = float(radius)
    r1 = float(radius_top) if radius_top is not None else r0
    half = float(length) / 2
    ring = _ring(segments)
    rows = []
    for i in range(1, cap_rings + 1):  # bottom hemisphere, excluding pole
        phi = -math.pi / 2 + (math.pi / 2) * i / cap_rings
        rows.append(np.column_stack([ring * r0 * math.cos(phi), np.full(segments, -half + r0 * math.sin(phi))]))
    for i in range(0, cap_rings):  # top hemisphere, excluding pole
        phi = (math.pi / 2) * i / cap_rings
        rows.append(np.column_stack([ring * r1 * math.cos(phi), np.full(segments, half + r1 * math.sin(phi))]))
    return _stack_rings(rows, bottom_pole=(0, 0, -half - r0), top_pole=(0, 0, half + r1))


def revolved_profile(profile, segments: int = 48):
    prof = [(float(r), float(z)) for r, z in profile]
    ring = _ring(segments)
    bottom_pole = top_pole = None
    if prof[0][0] <= EPS:
        bottom_pole = (0.0, 0.0, prof[0][1])
        prof = prof[1:]
    if prof[-1][0] <= EPS:
        top_pole = (0.0, 0.0, prof[-1][1])
        prof = prof[:-1]
    if not prof:
        raise ValueError("revolved_profile needs at least one station with radius > 0")
    rows = [np.column_stack([ring * r, np.full(segments, z)]) for r, z in prof]
    return _stack_rings(rows, bottom_pole=bottom_pole, top_pole=top_pole)


def elliptical_loft(stations, n: float = 2.0, segments: int = 64):
    st = [tuple(float(v) for v in s) for s in stations]
    ring = _superellipse_ring(segments, n)
    bottom_pole = top_pole = None
    if st[0][2] <= EPS and st[0][4] <= EPS:
        bottom_pole = (st[0][1], st[0][3], st[0][0])
        st = st[1:]
    if st and st[-1][2] <= EPS and st[-1][4] <= EPS:
        top_pole = (st[-1][1], st[-1][3], st[-1][0])
        st = st[:-1]
    if not st:
        raise ValueError("elliptical_loft needs at least one station with a,b > 0")
    rows = [np.column_stack([cx + ring[:, 0] * max(a, EPS), cy + ring[:, 1] * max(b, EPS), np.full(segments, z)])
            for z, cx, a, cy, b in st]
    return _stack_rings(rows, bottom_pole=bottom_pole, top_pole=top_pole)


def build_geometry(geo: dict):
    t = geo["type"]
    if t == "ellipsoid":
        return ellipsoid(geo["radii"], geo.get("segments", 48), geo.get("rings", 24))
    if t == "superellipsoid":
        return superellipsoid(geo["radii"], geo.get("exponents", [2.0, 2.0]), geo.get("segments", 48), geo.get("rings", 24))
    if t == "box":
        return box(geo["dimensions"])
    if t == "cylinder":
        return cylinder(geo["radius"], geo["depth"], geo.get("vertices", 48))
    if t == "capsule":
        return capsule(geo["radius"], geo["length"], geo.get("segments", 32), geo.get("cap_rings", 8), geo.get("radius_top"))
    if t == "revolved_profile":
        return revolved_profile(geo["profile"], geo.get("segments", 48))
    if t == "elliptical_loft":
        return elliptical_loft(geo["stations"], geo.get("n", 2.0), geo.get("segments", 64))
    raise ValueError(f"Unsupported geometry type {t!r}")


# --------------------------------------------------------------------------- transforms

def euler_xyz_matrix(deg) -> np.ndarray:
    """Blender 'XYZ' Euler (degrees) -> 3x3. Matrix = Rz @ Ry @ Rx (X applied first)."""
    a, b, c = (math.radians(float(v)) for v in deg)
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz = np.array([[cc, -sc, 0], [sc, cc, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def local_matrix(component: dict) -> np.ndarray:
    mode = component.get("rotation_mode", "XYZ")
    if mode != "XYZ":
        raise ValueError(f"Only rotation_mode 'XYZ' is supported, got {mode!r}")
    M = np.eye(4)
    S = np.diag([float(v) for v in component.get("scale", [1, 1, 1])])
    M[:3, :3] = euler_xyz_matrix(component.get("rotation_euler_deg", [0, 0, 0])) @ S
    M[:3, 3] = [float(v) for v in component["location"]]
    return M


MIRROR_X = np.diag([-1.0, 1.0, 1.0, 1.0])


def mirrored_component(component: dict) -> dict:
    """Return the explicit mirrored twin (across the PARENT-LOCAL X=0 plane) of a component.

    Location (x,y,z) -> (-x,y,z); XYZ Euler (a,b,c) -> (a,-b,-c); mesh mirrored in X.
    """
    m = component["mirror"]
    twin = {k: v for k, v in component.items() if k != "mirror"}
    twin["id"] = m["id"]
    twin["name"] = m.get("name", component.get("name", "") + " (mirror)")
    x, y, z = component["location"]
    twin["location"] = [-float(x), float(y), float(z)]
    a, b, c = component.get("rotation_euler_deg", [0, 0, 0])
    twin["rotation_euler_deg"] = [float(a), -float(b), -float(c)]
    twin["_mesh_mirror_x"] = True
    twin["_mirror_of"] = component["id"]
    return twin


def expand_components(components: list[dict]) -> list[dict]:
    """Components plus generated mirror twins, in a stable order (twin right after its source)."""
    out = []
    for c in components:
        out.append(c)
        if c.get("mirror"):
            out.append(mirrored_component(c))
    return out


def component_mesh(component: dict):
    verts, faces = build_geometry(component["geometry"])
    if component.get("_mesh_mirror_x"):
        verts = verts * np.array([-1.0, 1.0, 1.0])
        faces = [tuple(reversed(f)) for f in faces]
    return verts, faces


def world_matrices(components: list[dict]) -> dict[str, np.ndarray]:
    """World 4x4 for every (expanded) component. Raises on unknown parents or cycles."""
    by_id = {c["id"]: c for c in components}
    cache: dict[str, np.ndarray] = {}

    def resolve(cid, stack=()):
        if cid in cache:
            return cache[cid]
        if cid in stack:
            raise ValueError(f"Parenting cycle through {cid}")
        c = by_id[cid]
        L = local_matrix(c)
        pid = c.get("parent_id")
        if pid:
            if pid not in by_id:
                raise ValueError(f"{cid}: unknown parent {pid}")
            L = resolve(pid, stack + (cid,)) @ L
        cache[cid] = L
        return L

    for c in components:
        resolve(c["id"])
    return cache


def scene_meshes(spec: dict):
    """Yield (component, world_vertices Nx3, faces) for every expanded component of a spec."""
    comps = expand_components(spec["components"])
    W = world_matrices(comps)
    for c in comps:
        v, f = component_mesh(c)
        M = W[c["id"]]
        vw = v @ M[:3, :3].T + M[:3, 3]
        yield c, vw, f


def triangulate(faces):
    tris = []
    for f in faces:
        for i in range(1, len(f) - 1):
            tris.append((f[0], f[i], f[i + 1]))
    return np.array(tris, dtype=np.int64)


def mesh_volume(verts, faces) -> float:
    """Signed volume (positive when faces are wound outward)."""
    t = triangulate(faces)
    a, b, c = verts[t[:, 0]], verts[t[:, 1]], verts[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def is_closed_manifold(faces) -> bool:
    """Every undirected edge used exactly twice, each direction exactly once."""
    directed = {}
    for f in faces:
        for i in range(len(f)):
            e = (f[i], f[(i + 1) % len(f)])
            directed[e] = directed.get(e, 0) + 1
    for (a, b), n in directed.items():
        if n != 1 or directed.get((b, a), 0) != 1:
            return False
    return True
