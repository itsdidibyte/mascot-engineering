# 02 Coordinates, views and cameras

## World axes (Blender-native; do not change)

- `+Z` up, ground at `Z = 0` (lowest silhouette point).
- The character **faces `-Y`**: Blender's Front view (Numpad 1) shows the face.
- `+X` is the **character's LEFT**. Blender's `.L` naming and X-mirror therefore
  put `_l` / `.L` parts at `+X`, which is what Rigify and most rigs expect.
- `coordinate_system` in the spec: `BLENDER_Z_UP_FACING_NEG_Y_X_LEFT`.
- Relative scale: character height = `scale.character_height` (1.0 by default).
  Metres only when a real size is known (`scale.mode = metric`, `unit = m`).
- Origin: X = 0 on the front-view bbox centre, Y = 0 on the side-view bbox centre
  (recorded in `views[].normalization.anchor_rule`; override with `--anchor-col`).

## View kinds (orthographic)

| kind | camera at | looks toward | image right is | character faces |
|---|---|---|---|---|
| front | -Y | +Y | +X (character's left) | the viewer |
| back | +Y | -Y | -X | away |
| left | +X | -X | +Y | image-LEFT |
| right | -X | +X | -Y | image-RIGHT |
| three_quarter_left | orbit yaw +15..+75 (estimated) | - | - | image-LEFT; held-out check only |
| three_quarter_right | orbit yaw -15..-75 (estimated) | - | - | image-RIGHT; held-out check only |
| other | - | - | - | close-ups, expressions: visual reference only, never measured |

Orbit angle convention (`views.yaw_axes`): yaw 0 = front, +90 = left, -90 = right, 180 = back.

**Side-view rule:** the direction the nose points in the picture is the name of the
view. Nose toward image-right = `right` view (you see the character's right side).
Getting this wrong mirrors every depth, so confirm with the user when unsure.

## Canonical canvas

All measured views and all renders share one square canvas (`spec.canvas`):
default 1024 px covering 1.4 units, centre at (h = 0, z = 0.5). Reference images are
scaled so the character spans exactly z = 0..character_height; therefore front,
side, back and Blender renders overlay pixel-for-pixel.

Pixel <-> world: `col = (h - h_min) * px_per_unit`, `row = (z_max - z) * px_per_unit`,
`px_per_unit = resolution_px / world_size`.

This normalisation assumes each view shows the whole character in the same pose
and that every view's top and bottom are the same physical points (true for a
neutral-pose turnaround). If an ear is hidden in one view, the top differs: record
it, or use `--exclude` / `--anchor-col` and a decision.

## Blender cameras

`blender_build.py` creates one orthographic camera per measured view:
`ortho_scale = canvas.world_size`, centred on the canvas centre, rotation from
`mascot_lib.views.blender_camera_rotation(kind)` (columns = camera X, Y, Z in world;
Blender cameras look down their local -Z).

## OpenCV interop (only when a real calibrated camera is known)

OpenCV camera frame: +X right, +Y down, +Z forward. Blender camera frame: +X right,
+Y up, -Z forward. `R_world_to_cv = diag(1, -1, -1) @ R_cam_to_world_blender^T`,
`t = -R_world_to_cv @ C`. Implemented and tested in `views.blender_to_cv_world_to_camera`
and `views.cv_to_blender_camera`. Store in `views[].camera_cv` only when the
intrinsics really are known; never "fit" a pinhole camera to an AI illustration and
call it calibrated.

## Perspective images

Views marked `perspective_unknown` are not measured (`silhouettes.py` skips them).
If an image is only mildly perspective, the owner may accept `orthographic_assumed`;
record that decision, and expect a few percent error at the top and bottom.
