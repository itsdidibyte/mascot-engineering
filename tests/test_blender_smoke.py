"""Blender smoke test: builds the synthetic mascot headlessly and checks that Blender's
camera-matched masks agree with the numpy preview (proves axes, cameras and canvas
match on YOUR Blender version). Skipped when `blender` is not on PATH
(or set BLENDER=/path/to/blender).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from synthetic import SKILL, make_refs, truth_spec  # noqa: E402

import intake  # noqa: E402
import render_preview  # noqa: E402
import silhouettes  # noqa: E402
from mascot_lib import silhouette  # noqa: E402
from mascot_lib.workspace import geometry_hash, save_json  # noqa: E402

BLENDER = os.environ.get("BLENDER") or shutil.which("blender")


@unittest.skipUnless(BLENDER, "Blender not found on PATH (set BLENDER=/path/to/blender to run)")
class BlenderSmoke(unittest.TestCase):
    def test_build_and_renders_agree_with_preview(self):
        tmp = Path(tempfile.mkdtemp())
        refs = make_refs(tmp / "refs")
        ws = tmp / "ws"
        assert intake.main([str(ws), "--id", "blobby", "--view", f"front={refs['front']}",
                            "--view", f"right={refs['right']}", "--view", f"back={refs['back']}"]) == 0
        assert silhouettes.main([str(ws)]) == 0
        spec = json.loads((ws / "04_build" / "build_spec.json").read_text())
        t = truth_spec()
        spec["components"], spec["materials"], spec["decisions"] = t["components"], t["materials"], t["decisions"]
        save_json(ws / "04_build" / "build_spec.json", spec)
        cmd = [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", str(SKILL / "scripts" / "blender_build.py"), "--", str(ws), "--export-gltf"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        log = json.loads((ws / "04_build" / "blender" / "BUILD_LOG.json").read_text())
        self.assertEqual(log["status"], "SUCCESS")
        self.assertEqual(log["geometry_hash"], geometry_hash(spec))
        self.assertTrue((ws / "04_build" / "blender" / "blobby.blend").exists())
        self.assertTrue((ws / "04_build" / "blender" / "blobby.glb").exists())
        self.assertTrue(log["reference_planes"])   # REF_ image empties exist and (masks below) do not render
        assert render_preview.main([str(ws)]) == 0
        for vid in ("front", "right", "back"):
            b = np.array(Image.open(ws / "04_build" / "renders" / f"{vid}_mask.png").convert("RGBA"))[..., 3] >= 128
            p = np.array(Image.open(ws / "04_build" / "preview" / f"{vid}_mask.png")) >= 128
            self.assertGreater(silhouette.iou(b, p), 0.98, f"{vid}: Blender and preview disagree - axis or camera bug")
        shutil.rmtree(tmp, ignore_errors=True)

    def test_failing_build_returns_nonzero(self):
        tmp = Path(tempfile.mkdtemp())
        ws = tmp / "ws"
        (ws / "04_build").mkdir(parents=True)
        (ws / "04_build" / "build_spec.json").write_text('{"schema_version": "1.0.0"}')
        cmd = [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1",
               "--python", str(SKILL / "scripts" / "blender_build.py"), "--", str(ws)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        self.assertNotEqual(r.returncode, 0)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
