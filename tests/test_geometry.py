"""Unit tests: axis conventions, cameras, meshes, transforms, mirroring, migration."""
import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic import SKILL, truth_spec  # noqa: E402

from mascot_lib import meshgen, views  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402
import migrate_v1_to_v2  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"


class TestViews(unittest.TestCase):
    def test_camera_rotations_are_proper(self):
        for k in views.VIEW_KINDS:
            R = views.blender_camera_rotation(k)
            np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)
            self.assertAlmostEqual(np.linalg.det(R), 1.0, places=12)

    def test_front_camera_matches_blender_numpad1(self):
        loc, R, _ = views.blender_camera_for_view("front", Canvas())
        self.assertLess(loc[1], 0)                                   # camera on -Y
        np.testing.assert_allclose(-R[:, 2], [0, 1, 0])            # looks toward +Y
        np.testing.assert_allclose(R[:, 0], [1, 0, 0])             # image right = +X = character's LEFT

    def test_side_view_facing_rule(self):
        # character faces -Y. In "right" view the face must appear on IMAGE-RIGHT (h > 0)
        h, _, _ = views.world_to_view_hz(np.array([[0, -1.0, 0]]), "right")
        self.assertGreater(h[0], 0)
        h, _, _ = views.world_to_view_hz(np.array([[0, -1.0, 0]]), "left")
        self.assertLess(h[0], 0)
        # "right" view camera sits on the character's right side (-X)
        loc, _, _ = views.blender_camera_for_view("right", Canvas())
        self.assertLess(loc[0], 0)

    def test_cv_blender_round_trip_and_projection(self):
        loc, R, _ = views.blender_camera_for_view("front", Canvas())
        R_cw, t_cw = views.blender_to_cv_world_to_camera(R, loc)
        R2, C2 = views.cv_to_blender_camera(R_cw, t_cw)
        np.testing.assert_allclose(R2, R, atol=1e-12)
        np.testing.assert_allclose(C2, loc, atol=1e-12)
        target = np.array([[0.0, 0.0, 0.5]])                          # what the camera looks at
        uv, z = views.project_pinhole_cv(target, R_cw, t_cw, 1000, 1000, 512, 512)
        np.testing.assert_allclose(uv[0], [512, 512], atol=1e-9)
        self.assertGreater(z[0], 0)
        up = views.project_pinhole_cv(np.array([[0.0, 0.0, 0.9]]), R_cw, t_cw, 1000, 1000, 512, 512)[0]
        self.assertLess(up[0][1], 512)                                # world up -> smaller v (OpenCV y down)
        left = views.project_pinhole_cv(np.array([[0.3, 0.0, 0.5]]), R_cw, t_cw, 1000, 1000, 512, 512)[0]
        self.assertGreater(left[0][0], 512)                           # +X appears on image right in front view

    def test_yaw_orbit_matches_named_views(self):
        for yaw, kind in ((0, "front"), (90, "left"), (-90, "right"), (180, "back")):
            np.testing.assert_allclose(views.yaw_axes(yaw), views.view_axes(kind), atol=1e-12)
        # positive yaw: nose (-Y) points to image-left
        h, _, _ = views.world_to_view_hz(np.array([[0, -1.0, 0]]), "yaw:45")
        self.assertLess(h[0], 0)

    def test_canvas_round_trip(self):
        c = Canvas()
        col, row = c.to_pixel(0.25, 0.75)
        h, z = c.to_world(col, row)
        self.assertAlmostEqual(float(h), 0.25)
        self.assertAlmostEqual(float(z), 0.75)

    def test_euler_xyz_decomposition(self):
        for deg in ([10, 20, 30], [-45, 5, 170], [0, 0, 90]):
            a, b, c = views.rotation_to_euler_xyz(meshgen.euler_xyz_matrix(deg))
            np.testing.assert_allclose(np.degrees([a, b, c]), deg, atol=1e-9)


class TestMeshes(unittest.TestCase):
    CASES = [
        ({"type": "ellipsoid", "radii": [0.3, 0.2, 0.4], "segments": 96, "rings": 48}, 4 / 3 * math.pi * 0.3 * 0.2 * 0.4, 0.01),
        ({"type": "superellipsoid", "radii": [0.3, 0.2, 0.4], "exponents": [2, 2]}, 4 / 3 * math.pi * 0.3 * 0.2 * 0.4, 0.03),
        ({"type": "box", "dimensions": [0.2, 0.3, 0.4]}, 0.024, 1e-9),
        ({"type": "cylinder", "radius": 0.1, "depth": 0.5, "vertices": 128}, math.pi * 0.01 * 0.5, 0.005),
        ({"type": "capsule", "radius": 0.1, "length": 0.4, "segments": 96, "cap_rings": 24},
         math.pi * 0.01 * 0.4 + 4 / 3 * math.pi * 0.001, 0.01),
        ({"type": "revolved_profile", "profile": [[0, 0], [0.1, 0.05], [0.1, 0.45], [0, 0.5]], "segments": 128}, None, None),
        ({"type": "elliptical_loft", "stations": [[0, 0.1, 0.2, 0, 0.1], [1, 0.1, 0.2, 0, 0.1]], "segments": 128},
         math.pi * 0.2 * 0.1 * 1.0, 0.005),
    ]

    def test_closed_manifold_outward_and_volume(self):
        for geo, vol, rtol in self.CASES:
            v, f = meshgen.build_geometry(geo)
            self.assertTrue(meshgen.is_closed_manifold(f), geo["type"])
            V = meshgen.mesh_volume(v, f)
            self.assertGreater(V, 0, geo["type"])
            if vol is not None:
                self.assertAlmostEqual(V / vol, 1.0, delta=rtol, msg=geo["type"])

    def test_loft_with_poles_is_closed(self):
        v, f = meshgen.build_geometry({"type": "elliptical_loft", "stations": [[0, 0, 0, 0, 0], [0.5, 0, 0.2, 0, 0.1], [1, 0, 0, 0, 0]]})
        self.assertTrue(meshgen.is_closed_manifold(f))
        self.assertGreater(meshgen.mesh_volume(v, f), 0)

    def test_parenting_is_local(self):
        spec = truth_spec()
        W = meshgen.world_matrices(meshgen.expand_components(spec["components"]))
        head = W["head"][:3, 3]
        ear = W["ear_l"][:3, 3]
        np.testing.assert_allclose(ear, head + np.array([0.15, 0.0, 1.0 - 0.09 - 0.78]))

    def test_mirror_twin_is_exact_reflection(self):
        spec = truth_spec()
        meshes = {c["id"]: vw for c, vw, _ in meshgen.scene_meshes(spec)}
        np.testing.assert_allclose(meshes["arm_r"], meshes["arm_l"] * np.array([-1, 1, 1]), atol=1e-12)
        np.testing.assert_allclose(meshes["eye_r"], meshes["eye_l"] * np.array([-1, 1, 1]), atol=1e-12)
        for c in meshgen.expand_components(spec["components"]):
            v, f = meshgen.component_mesh(c)
            self.assertGreater(meshgen.mesh_volume(v, f), 0, c["id"])

    def test_cycle_detection(self):
        comps = [{"id": "a", "parent_id": "b", "location": [0, 0, 0]}, {"id": "b", "parent_id": "a", "location": [0, 0, 0]}]
        with self.assertRaises(ValueError):
            meshgen.world_matrices(comps)


class TestMigration(unittest.TestCase):
    def test_v1_to_v2_preserves_ids_and_world_shape(self):
        v1 = json.loads((FIX / "v1_generic_mascot_spec.json").read_text())
        v2, log = migrate_v1_to_v2.migrate(copy.deepcopy(v1))
        self.assertEqual([c["id"] for c in v1["components"]], [c["id"] for c in v2["components"]])
        # v1 world: same transform math (v1 used local parenting too), in v1 axes
        v1_like = {"components": [dict(c, rotation_mode="XYZ") for c in v1["components"]]}
        Rz = np.diag([-1.0, -1.0, 1.0])
        old = {c["id"]: np.round(vw @ Rz.T, 9) for c, vw, _ in meshgen.scene_meshes(v1_like)}
        new = {c["id"]: np.round(vw, 9) for c, vw, _ in meshgen.scene_meshes(v2)}
        for cid in old:
            a = old[cid][np.lexsort(old[cid].T)]
            b = new[cid][np.lexsort(new[cid].T)]
            np.testing.assert_allclose(a, b, atol=1e-7, err_msg=cid)
        # the eye that v1 called "left" must be on the character's left (+X) in v2
        eye_left = next(c for c in v2["components"] if c["id"] == "eye_left")
        self.assertGreater(eye_left["location"][0], 0)
        self.assertTrue(any("eye_left" in line for line in log))

    def test_migrated_spec_passes_check(self):
        import check_spec
        with tempfile.TemporaryDirectory() as tmp:
            v1 = json.loads((FIX / "v1_generic_mascot_spec.json").read_text())
            v2, _ = migrate_v1_to_v2.migrate(v1)
            p = Path(tmp) / "spec.json"
            p.write_text(json.dumps(v2))
            errors, _ = check_spec.evaluate(p)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
