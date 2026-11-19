"""End-to-end and red-team tests on synthetic ground truth (no Blender needed)."""
import contextlib
import copy
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic import fake_reference, make_refs, truth_spec  # noqa: E402

import check_spec  # noqa: E402
import check_three_quarter  # noqa: E402
import compare  # noqa: E402
import features  # noqa: E402
import fit_limb  # noqa: E402
import consistency  # noqa: E402
import intake  # noqa: E402
import pack  # noqa: E402
import propose_spec  # noqa: E402
import render_preview  # noqa: E402
import silhouettes  # noqa: E402
import visual_hull  # noqa: E402
from mascot_lib import silhouette  # noqa: E402
from mascot_lib.views import Canvas  # noqa: E402
from mascot_lib.workspace import geometry_hash, save_json  # noqa: E402


def quiet(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        code = fn(*args)
    return code, buf.getvalue()


def spec_of(ws):
    return json.loads((ws / "04_build" / "build_spec.json").read_text())


def write_spec(ws, spec):
    save_json(ws / "04_build" / "build_spec.json", spec)


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        refs = make_refs(cls.tmp / "refs")
        cls.refs = refs
        cls.ws = cls.tmp / "ws"
        code, out = quiet(intake.main, [str(cls.ws), "--id", "blobby", "--origin", "render_3d",
                                        "--view", f"front={refs['front']}", "--view", f"right={refs['right']}",
                                        "--view", f"back={refs['back']}"])
        assert code == 0, out
        code, out = quiet(silhouettes.main, [str(cls.ws)])
        assert code == 0, out

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def fresh(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        shutil.copytree(self.ws, d / "ws")
        return d / "ws"

    # ------------------------------------------------------------------ measurement accuracy
    def test_normalisation_puts_ground_at_0_and_top_at_1(self):
        c = Canvas()
        for vid in ("front", "right", "back"):
            m = np.array(Image.open(self.ws / "02_views" / f"{vid}_mask.png")) > 127
            ys = np.nonzero(m.any(axis=1))[0]
            _, z_top = c.to_world(0, ys[0])
            _, z_bot = c.to_world(0, ys[-1] + 1)
            self.assertAlmostEqual(float(z_top), 1.0, delta=2 / c.px_per_unit, msg=vid)
            self.assertAlmostEqual(float(z_bot), 0.0, delta=2 / c.px_per_unit, msg=vid)

    def test_measured_widths_match_ground_truth(self):
        """Head width (2 x 0.24) at its equator and body width at z=0.18 (2 x 0.27), measured from a 900px image."""
        prof = json.loads((self.ws / "02_views" / "front_profile.json").read_text())["stations"]
        main = silhouette.main_run_profile(prof, 0.0)
        z = np.array([s["z"] for s in prof])
        for zq, truth in ((0.78, 0.48), (0.18, 0.54)):
            r = main[int(np.argmin(np.abs(z - zq)))]
            self.assertAlmostEqual(r[1] - r[0], truth, delta=0.006, msg=f"z={zq}")

    def test_views_are_consistent(self):
        ws = self.fresh()
        code, out = quiet(consistency.main, [str(ws)])
        self.assertEqual(code, 0, out)
        res = json.loads((ws / "02_views" / "CONSISTENCY.json").read_text())
        self.assertEqual(res["overall"], "CONSISTENT")
        self.assertTrue((ws / "02_views" / "TURNAROUND.png").exists())

    def test_measured_body_and_feedback_loop(self):
        ws = self.fresh()
        code, out = quiet(propose_spec.main, [str(ws), "--id", "body_hull"])
        self.assertEqual(code, 0, out)
        self.assertIn("jumps near", out)                       # warns where the arms join
        quiet(render_preview.main, [str(ws)])
        code, out = quiet(compare.main, [str(ws)])
        rep = json.loads((ws / "05_validation" / "COMPARE_preview.json").read_text())
        v = {r["view_id"]: r for r in rep["views"]}
        self.assertGreater(v["right"]["iou"], 0.97)             # arms hide inside the side silhouette
        arm = [f for f in v["front"]["findings"] if f["z_from"] <= 0.45 <= f["z_to"]]
        self.assertTrue(arm and arm[0]["error"] < 0 and arm[0]["edge"] == "BOTH", v["front"]["findings"])
        # an architect adds the arms, ears and feet -> front matches
        spec = spec_of(ws)
        truth = {c["id"]: c for c in truth_spec()["components"]}
        for cid in ("arm_l", "ear_l", "foot_l"):
            c = copy.deepcopy(truth[cid])
            c["parent_id"] = None
            if cid == "ear_l":
                c["location"] = [0.15, 0.0, 0.91]
            c["evidence"] = {"status": "inferred", "method": "test", "reference_ids": ["front"], "uncertainty_note": "test"}
            spec["components"].append(c)
        write_spec(ws, spec)
        quiet(render_preview.main, [str(ws)])
        quiet(compare.main, [str(ws)])
        rep = json.loads((ws / "05_validation" / "COMPARE_preview.json").read_text())
        front = next(r for r in rep["views"] if r["view_id"] == "front")
        self.assertGreater(front["iou"], 0.97)
        code, out = quiet(check_spec.main, [str(ws)])
        self.assertEqual(code, 0, out)

    def test_visual_hull_reprojects(self):
        ws = self.fresh()
        code, out = quiet(visual_hull.main, [str(ws), "--res", "96"])
        self.assertEqual(code, 0, out)
        rep = json.loads((ws / "03_geometry" / "HULL_REPORT.json").read_text())
        for vid, iou in rep["reprojection_iou"].items():
            self.assertGreater(iou, 0.95, vid)

    def test_compare_reports_direction_in_world_axes(self):
        ws = self.fresh()
        ref = np.array(Image.open(ws / "02_views" / "front_mask.png")) > 127
        (ws / "04_build" / "preview").mkdir(parents=True, exist_ok=True)
        shifted = np.roll(ref, 30, axis=1)                       # model moved toward image-right = +X
        Image.fromarray((shifted * 255).astype(np.uint8)).save(ws / "04_build" / "preview" / "front_mask.png")
        quiet(compare.main, [str(ws)])
        rep = json.loads((ws / "05_validation" / "COMPARE_preview.json").read_text())
        f = rep["views"][0]["findings"]
        self.assertTrue(any(x["edge"].startswith("+X") and x["error"] > 0 for x in f))
        self.assertTrue(any(x["edge"].startswith("-X") and x["error"] < 0 for x in f))

    # ------------------------------------------------------------------ v2.1 tools
    def test_despike_removes_attached_arm_bulge(self):
        ws = self.fresh()
        quiet(propose_spec.main, [str(ws), "--id", "raw"])
        quiet(propose_spec.main, [str(ws), "--id", "clean", "--despike"])
        comps = {c["id"]: c for c in spec_of(ws)["components"]}
        a_at = lambda c, zq: min(c["geometry"]["stations"], key=lambda s: abs(s[0] - zq))[2]
        self.assertGreater(a_at(comps["raw"], 0.37) - a_at(comps["clean"], 0.37), 0.02)   # half-width bulge removed
        self.assertAlmostEqual(a_at(comps["raw"], 0.62), a_at(comps["clean"], 0.62), places=4)   # neck untouched

    def test_limb_fit_recovers_ground_truth_arm(self):
        ws = self.fresh()
        quiet(propose_spec.main, [str(ws), "--id", "body_hull", "--despike"])
        code, out = quiet(fit_limb.main, [str(ws), "--id", "arm_l", "--x-seed", "0.3", "--z-range", "0.3", "0.56", "--mirror-id", "arm_r"])
        self.assertEqual(code, 0, out)
        arm = next(c for c in spec_of(ws)["components"] if c["id"] == "arm_l")
        self.assertAlmostEqual(arm["geometry"]["radius"], 0.045, delta=0.006)        # truth 0.045
        self.assertAlmostEqual(arm["rotation_euler_deg"][1], 35.0, delta=5.0)        # truth 35 deg
        self.assertAlmostEqual(arm["location"][0], 0.30, delta=0.02)
        self.assertAlmostEqual(arm["location"][2], 0.40, delta=0.03)
        quiet(fit_limb.main, [str(ws), "--id", "ear_l", "--x-seed", "0.15", "--z-range", "0.85", "1.0", "--mirror-id", "ear_r", "--embed", "2"])
        quiet(render_preview.main, [str(ws)])
        quiet(compare.main, [str(ws)])
        rep = json.loads((ws / "05_validation" / "COMPARE_preview.json").read_text())
        self.assertGreater(next(r for r in rep["views"] if r["view_id"] == "front")["iou"], 0.975)
        self.assertEqual(check_spec.evaluate(ws)[0], [])

    def test_feature_finder_locates_eyes(self):
        ws = self.fresh()
        code, out = quiet(features.main, [str(ws), "--add", "eye:1,2"])
        self.assertEqual(code, 0, out)
        feats = json.loads((ws / "03_geometry" / "FEATURES.json").read_text())["features"]
        eyes = [f for f in feats if not f["likely_shading"]]
        self.assertEqual(len(eyes), 2, feats)
        for f in eyes:                                                           # truth: X +-0.08, Z 0.80, half 0.03 x 0.05
            self.assertAlmostEqual(abs(f["centre_xz"][0]), 0.08, delta=0.01)
            self.assertAlmostEqual(f["centre_xz"][1], 0.80, delta=0.01)
            self.assertAlmostEqual(f["half_size_xz"][1], 0.05, delta=0.008)
        self.assertTrue(all(f["likely_shading"] for f in feats if f not in eyes))
        self.assertEqual(check_spec.evaluate(ws)[0], [])

    def test_three_quarter_view_estimates_angle_and_roundness(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        t = truth_spec()
        t["components"] = [c for c in t["components"] if c["id"] in ("body", "head")]
        refs = {k: fake_reference(t, kind, d / f"{k}.png", px) for k, kind, px in
                (("front", "front", 900), ("side", "right", 760), ("q34", "yaw:40", 880))}
        ws = d / "ws"
        quiet(intake.main, [str(ws), "--id", "t", "--view", f"front={refs['front']}", "--view", f"right={refs['side']}",
                            "--view", f"three_quarter_left={refs['q34']}"])
        quiet(silhouettes.main, [str(ws)])
        quiet(propose_spec.main, [str(ws), "--id", "body_hull", "--n", "4"])      # deliberately too boxy
        code, out = quiet(check_three_quarter.main, [str(ws), "--tune-n", "body_hull", "--apply"])
        self.assertEqual(code, 0, out)
        rep = json.loads((ws / "05_validation" / "THREE_QUARTER.json").read_text())["views"][0]
        self.assertIn(rep["n_tuning"]["best"]["n"], (1.5, 2.0, 2.5))               # truth: round (n = 2)
        self.assertLessEqual(abs(rep["best_yaw_deg"] - 40), 10)                     # truth: 40 deg
        self.assertEqual(rep["status"], "PASS")
        self.assertEqual(next(c for c in spec_of(ws)["components"] if c["id"] == "body_hull")["geometry"]["n"],
                         rep["n_tuning"]["best"]["n"])

    # ------------------------------------------------------------------ red-team cases
    def test_redteam_inconsistent_ai_side_view(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        side = fake_reference(truth_spec(head_z=0.70), "right", d / "bad_side.png", 760)
        ws = d / "ws"
        quiet(intake.main, [str(ws), "--id", "blobby", "--view", f"front={self.refs['front']}", "--view", f"right={side}"])
        quiet(silhouettes.main, [str(ws)])
        code, out = quiet(consistency.main, [str(ws)])
        res = json.loads((ws / "02_views" / "CONSISTENCY.json").read_text())
        feat = next(c for c in res["checks"] if c["check"].startswith("feature_heights"))
        self.assertIn(feat["status"], ("CHECK", "CONFLICT"), feat)

    def test_redteam_single_front_view_depth_is_proposed(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        ws = d / "ws"
        quiet(intake.main, [str(ws), "--id", "blobby", "--view", f"front={self.refs['front']}"])
        quiet(silhouettes.main, [str(ws)])
        quiet(propose_spec.main, [str(ws), "--id", "body"])
        spec = spec_of(ws)
        p = spec["components"][0]["evidence"]["parameters"]["stations[*].b,cy"]
        self.assertEqual(p["status"], "proposed")
        self.assertTrue(any("PROPOSED" in i["text"] for i in spec["unresolved_issues"] if isinstance(i, dict)))

    def test_redteam_cropped_reference_is_refused(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        im = Image.open(self.refs["front"])
        cropped = im.crop((0, 300, im.width, im.height))                 # head cut off
        cropped.save(d / "crop.png")
        ws = d / "ws"
        quiet(intake.main, [str(ws), "--id", "blobby", "--view", f"front={d / 'crop.png'}"])
        code, out = quiet(silhouettes.main, [str(ws)])
        self.assertEqual(code, 1)
        self.assertIn("cropped", out)

    def test_redteam_white_belly_on_white_background_stays_solid(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        im = Image.new("RGB", (400, 600), (255, 255, 255))
        dr = ImageDraw.Draw(im)
        dr.ellipse((100, 100, 300, 550), fill=(255, 255, 255), outline=(20, 20, 20), width=4)
        m, rep = silhouette.extract_mask(im)
        self.assertGreater(m[325, 200], 0)                               # interior white kept
        self.assertEqual(rep["method"], "border_color")

    def test_redteam_perspective_view_not_measured(self):
        ws = self.fresh()
        spec = spec_of(ws)
        for v in spec["views"]:
            if v["id"] == "back":
                v["projection"] = "perspective_unknown"
        write_spec(ws, spec)
        (ws / "02_views" / "back_mask.png").unlink()
        code, out = quiet(silhouettes.main, [str(ws)])
        self.assertIn("SKIP back", out)
        self.assertFalse((ws / "02_views" / "back_mask.png").exists())

    def test_redteam_asymmetric_part_wrongly_mirrored(self):
        d = Path(tempfile.mkdtemp(dir=self.tmp))
        t = truth_spec()
        t["components"] = [c for c in t["components"] if c["id"] != "ear_l"] + [
            {"id": "ear_one", "name": "single ear", "parent_id": None, "geometry": {"type": "ellipsoid", "radii": [0.05, 0.03, 0.09]},
             "location": [0.15, 0, 0.91], "rotation_euler_deg": [0, 0, 0], "material_id": "body",
             "evidence": {"status": "approved_design", "method": "t", "reference_ids": [], "decision_id": "D-TRUTH"}}]
        front = fake_reference(t, "front", d / "front.png", 900)
        side = fake_reference(t, "right", d / "side.png", 760)
        ws = d / "ws"
        quiet(intake.main, [str(ws), "--id", "blobby", "--view", f"front={front}", "--view", f"right={side}"])
        quiet(silhouettes.main, [str(ws), "--anchor-col", "front:512"])
        quiet(consistency.main, [str(ws)])
        quiet(propose_spec.main, [str(ws), "--id", "body"])
        spec = spec_of(ws)
        spec["components"].append({"id": "ear_l", "name": "ear", "parent_id": None, "geometry": {"type": "ellipsoid", "radii": [0.05, 0.03, 0.09]},
                                   "location": [0.15, 0, 0.91], "rotation_euler_deg": [0, 0, 0], "material_id": "body",
                                   "mirror": {"id": "ear_r"}, "evidence": {"status": "inferred", "method": "t", "reference_ids": ["front"], "uncertainty_note": "t"}})
        write_spec(ws, spec)
        errors, warnings = check_spec.evaluate(ws)
        self.assertTrue(any("mirrored, but the front view is asymmetric" in w for w in warnings), warnings)

    def test_redteam_structural_errors(self):
        ws = self.fresh()
        quiet(propose_spec.main, [str(ws), "--id", "body"])
        base = spec_of(ws)
        cases = {
            "cycle": lambda s: s["components"].extend([
                {**copy.deepcopy(s["components"][0]), "id": "a", "parent_id": "b"},
                {**copy.deepcopy(s["components"][0]), "id": "b", "parent_id": "a"}]),
            "unknown material": lambda s: s["components"][0].update(material_id="ghost"),
            "status 'observed' but no view": lambda s: s["components"][0]["evidence"].update(reference_ids=[]),
            "needs evidence.decision_id": lambda s: s["components"][0]["evidence"].update(status="approved_design"),
            "without release_evidence": lambda s: s.update(package_mode="BLOCKOUT_READY"),
            "duplicate component ids": lambda s: s["components"][0].update(mirror={"id": "body"}),
        }
        for needle, mutate in cases.items():
            s = copy.deepcopy(base)
            mutate(s)
            write_spec(ws, s)
            errors, _ = check_spec.evaluate(ws)
            self.assertTrue(any(needle in e for e in errors), (needle, errors))

    def test_redteam_blockout_claim_needs_matching_build(self):
        ws = self.fresh()
        quiet(propose_spec.main, [str(ws), "--id", "body"])
        s = spec_of(ws)
        log = ws / "04_build" / "blender" / "BUILD_LOG.json"
        save_json(log, {"status": "SUCCESS", "geometry_hash": geometry_hash(s)})
        s["package_mode"] = "BLOCKOUT_READY"
        s["release_evidence"] = {"blender_build_log": "04_build/blender/BUILD_LOG.json"}
        write_spec(ws, s)
        errors, _ = check_spec.evaluate(ws)
        self.assertEqual(errors, [])
        s["components"][0]["geometry"]["stations"][5][2] += 0.01          # silent edit after the build
        write_spec(ws, s)
        errors, _ = check_spec.evaluate(ws)
        self.assertTrue(any("DIFFERENT spec" in e for e in errors), errors)

    def test_redteam_reference_tampering_detected(self):
        ws = self.fresh()
        p = ws / "01_references" / "front.png"
        im = Image.open(p).convert("RGB")
        im.putpixel((0, 0), (1, 2, 3))
        im.save(p)
        errors, _ = check_spec.evaluate(ws)
        self.assertTrue(any("checksum mismatch" in e for e in errors))

    # ------------------------------------------------------------------ packaging
    def test_pack_is_reproducible_and_refuses_failing_spec(self):
        ws = self.fresh()
        quiet(propose_spec.main, [str(ws), "--id", "body"])
        out = ws.parent
        pack.pack(ws, out / "a.zip")
        pack.pack(ws, out / "b.zip")
        h = [hashlib.sha256((out / n).read_bytes()).hexdigest() for n in ("a.zip", "b.zip")]
        self.assertEqual(h[0], h[1])
        s = spec_of(ws)
        s["components"][0]["material_id"] = "ghost"
        write_spec(ws, s)
        with self.assertRaises(ValueError):
            pack.pack(ws, out / "c.zip")


if __name__ == "__main__":
    unittest.main()
