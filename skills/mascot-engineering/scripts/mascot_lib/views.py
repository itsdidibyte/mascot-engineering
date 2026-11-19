"""World axes, orthographic view definitions, canonical canvas and camera conversions.

WORLD CONVENTION (Blender-native, see reference/02_coordinates_and_cameras.md)
    +Z up, ground plane at Z = 0
    character faces -Y  (Blender "Front" view, Numpad 1, shows the face)
    +X = the CHARACTER'S LEFT  (so Blender's .L / X-mirror naming is correct)

VIEW KINDS (what the camera sees, orthographic)
    front : camera on -Y looking +Y. Image right = +X (character's left).
    back  : camera on +Y looking -Y. Image right = -X.
    left  : camera on +X looking -X (sees the character's LEFT side).
            Image right = +Y, so the character FACES IMAGE-LEFT.
    right : camera on -X looking +X (sees the character's RIGHT side).
            Image right = -Y, so the character FACES IMAGE-RIGHT.
Rule of thumb for side images: the direction the nose points in the picture
is the name of the view ("faces image-right" -> kind "right").

CANONICAL CANVAS
    Every reference view is normalised onto the same square canvas: the
    character's ground contact at z=0, its top at z=character_height (1.0 in
    relative mode), and the horizontal anchor at h=0. One world unit is the
    same number of pixels in every view, so front/side/back are directly
    comparable and Blender renders with the matching ortho camera land
    pixel-for-pixel on top of them.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

VIEW_KINDS = ("front", "back", "left", "right")

# Rows: image-right axis, image-up axis, toward-camera axis (all in world coords).
_VIEW_AXES = {
    "front": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
    "back": ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
    "left": ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
    "right": ((0, -1, 0), (0, 0, 1), (-1, 0, 0)),
}


THREE_QUARTER_KINDS = ("three_quarter_left", "three_quarter_right")


def yaw_axes(yaw_deg: float) -> np.ndarray:
    """Orthographic camera orbiting the character about +Z.

    yaw 0 = front, +90 = left view, -90 = right view, 180 = back. A positive yaw shows
    the character's LEFT side and the nose points to IMAGE-LEFT (three_quarter_left).
    """
    t = math.radians(float(yaw_deg))
    c, s = math.cos(t), math.sin(t)
    right = (c, s, 0.0)
    toward = (s, -c, 0.0)
    return np.array([right, (0.0, 0.0, 1.0), toward], dtype=float)


def view_axes(kind) -> np.ndarray:
    """3x3 matrix whose rows are (image_right, image_up, toward_camera) in world coords.

    `kind` is a view kind name or "yaw:<degrees>" for an arbitrary orbit angle.
    """
    if isinstance(kind, str) and kind.startswith("yaw:"):
        return yaw_axes(float(kind[4:]))
    if kind not in _VIEW_AXES:
        raise ValueError(f"Unknown view kind {kind!r}; expected one of {VIEW_KINDS} or 'yaw:<deg>'")
    return np.array(_VIEW_AXES[kind], dtype=float)


def blender_camera_rotation(kind: str) -> np.ndarray:
    """Camera-to-world rotation for a Blender camera (local -Z looks forward, +Y up, +X right).

    Columns are the camera's local X, Y, Z axes expressed in world coordinates.
    """
    a = view_axes(kind)
    return np.stack([a[0], a[1], a[2]], axis=1)


def blender_to_cv_world_to_camera(R_cam_to_world_blender: np.ndarray, cam_location) -> tuple[np.ndarray, np.ndarray]:
    """Convert a Blender camera pose into OpenCV world->camera (R_cw, t_cw).

    OpenCV camera frame: +X right, +Y DOWN, +Z forward (into the scene).
    Blender camera frame: +X right, +Y up, -Z forward.
    So cv_from_blender_cam = diag(1, -1, -1).
    """
    R_bc = np.asarray(R_cam_to_world_blender, dtype=float)
    C = np.asarray(cam_location, dtype=float).reshape(3)
    flip = np.diag([1.0, -1.0, -1.0])
    R_cw = flip @ R_bc.T
    t_cw = -R_cw @ C
    return R_cw, t_cw


def cv_to_blender_camera(R_cw: np.ndarray, t_cw) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of blender_to_cv_world_to_camera: returns (R_cam_to_world_blender, location)."""
    R_cw = np.asarray(R_cw, dtype=float)
    t_cw = np.asarray(t_cw, dtype=float).reshape(3)
    flip = np.diag([1.0, -1.0, -1.0])
    R_bc = (flip @ R_cw).T
    C = -R_cw.T @ t_cw
    return R_bc, C


def project_pinhole_cv(points_world, R_cw, t_cw, fx, fy, cx, cy):
    """Project Nx3 world points with an OpenCV pinhole model. Returns Nx2 pixels and depth."""
    P = np.asarray(points_world, dtype=float) @ np.asarray(R_cw, dtype=float).T + np.asarray(t_cw, dtype=float)
    z = P[:, 2]
    if np.any(z <= 0):
        raise ValueError("Point behind camera (z_cv <= 0)")
    u = fx * P[:, 0] / z + cx
    v = fy * P[:, 1] / z + cy
    return np.stack([u, v], axis=1), z


@dataclass(frozen=True)
class Canvas:
    """Square canonical canvas shared by all normalised views and all renders."""

    world_size: float = 1.4      # world units covered by the canvas edge
    center_h: float = 0.0        # world horizontal value at canvas centre
    center_z: float = 0.5        # world Z at canvas centre
    resolution_px: int = 1024

    @property
    def px_per_unit(self) -> float:
        return self.resolution_px / self.world_size

    @property
    def h_min(self) -> float:
        return self.center_h - self.world_size / 2

    @property
    def z_max(self) -> float:
        return self.center_z + self.world_size / 2

    def to_pixel(self, h, z):
        """World (h, z) -> continuous pixel (col, row). Pixel centres sit at integer+0.5."""
        col = (np.asarray(h, dtype=float) - self.h_min) * self.px_per_unit
        row = (self.z_max - np.asarray(z, dtype=float)) * self.px_per_unit
        return col, row

    def to_world(self, col, row):
        h = np.asarray(col, dtype=float) / self.px_per_unit + self.h_min
        z = self.z_max - np.asarray(row, dtype=float) / self.px_per_unit
        return h, z

    def row_of_z(self, z) -> int:
        _, row = self.to_pixel(0.0, z)
        return int(math.floor(float(row)))

    def as_dict(self) -> dict:
        return {"world_size": self.world_size, "center_h": self.center_h,
                "center_z": self.center_z, "resolution_px": self.resolution_px}

    @staticmethod
    def from_dict(d: dict | None) -> "Canvas":
        if not d:
            return Canvas()
        return Canvas(float(d.get("world_size", 1.4)), float(d.get("center_h", 0.0)),
                      float(d.get("center_z", 0.5)), int(d.get("resolution_px", 1024)))


def world_to_view_hz(points_world, kind: str):
    """Orthographic projection of Nx3 world points to (h, z_up, depth_toward_camera)."""
    a = view_axes(kind)
    P = np.asarray(points_world, dtype=float)
    return P @ a[0], P @ a[1], P @ a[2]


def view_h_to_world_axis(kind: str) -> tuple[int, float]:
    """For a view, which world axis the image-horizontal maps to and with which sign.

    Returns (axis_index, sign) so that world[axis_index] = sign * h.
    """
    right = view_axes(kind)[0]
    idx = int(np.argmax(np.abs(right)))
    return idx, float(right[idx])


def blender_camera_for_view(kind: str, canvas: Canvas, distance: float = 10.0):
    """Location, camera->world rotation and ortho_scale for a Blender ortho camera matching the canvas."""
    a = view_axes(kind)
    centre = a[0] * canvas.center_h + np.array([0.0, 0.0, canvas.center_z])
    location = centre + a[2] * distance
    return location, blender_camera_rotation(kind), canvas.world_size


def rotation_to_euler_xyz(R: np.ndarray) -> tuple[float, float, float]:
    """Decompose R = Rz(c) @ Ry(b) @ Rx(a) (Blender 'XYZ' Euler order). Returns radians (a, b, c)."""
    R = np.asarray(R, dtype=float)
    sy = -R[2, 0]
    sy = max(-1.0, min(1.0, sy))
    b = math.asin(sy)
    if abs(math.cos(b)) > 1e-9:
        a = math.atan2(R[2, 1], R[2, 2])
        c = math.atan2(R[1, 0], R[0, 0])
    else:  # gimbal lock
        a = math.atan2(-R[1, 2], R[1, 1])
        c = 0.0
    return a, b, c
