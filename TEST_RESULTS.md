# Verification record (0.2.0-alpha): 2026-11-19 (build environment: Linux, Python 3.13, numpy 2.5, scipy 1.18, Pillow 12.3, scikit-image 0.26, no Blender)

| Check | Result | Evidence |
|---|---|---|
| Full test suite | PASS: 34 passed, 2 skipped (Blender) | `python3 -m unittest discover -s tests -v` |
| Axis/camera conventions (front = Numpad 1, side facing rule, proper rotations, OpenCV round trip) | PASS | `tests/test_geometry.py::TestViews` |
| Every primitive closed, manifold, outward; volumes vs analytic formulas | PASS (ellipsoid within 1 %, box exact) | `TestMeshes.test_closed_manifold_outward_and_volume` |
| Mirror twins are exact reflections | PASS | `test_mirror_twin_is_exact_reflection` |
| v1 -> v2 migration keeps ids and world shape | PASS | `TestMigration` |
| Measurement accuracy vs synthetic truth (900 px image) | PASS: head and body widths within 0.006 of truth | `test_measured_widths_match_ground_truth` |
| Normalisation: ground at z = 0, top at z = 1 (+/- 2 px) | PASS | `test_normalisation_puts_ground_at_0_and_top_at_1` |
| Measured body + compare loop finds missing arms; adding them gives front IoU > 0.97 | PASS | `test_measured_body_and_feedback_loop` |
| Visual hull reprojection IoU > 0.95 every view | PASS (0.987-0.988 at res 160) | `test_visual_hull_reprojects` |
| 9 red-team cases | PASS | `test_redteam_*` |
| Limb fit vs truth arm (r 0.045, tilt 35 deg) | PASS: r 0.0466, tilt 32.1 deg, centre within 0.012; front IoU > 0.975 with arms + ears | `test_limb_fit_recovers_ground_truth_arm` |
| Eye finder vs truth (X +-0.08, Z 0.80) | PASS: within 0.002; shading blobs flagged | `test_feature_finder_locates_eyes` |
| 3/4 held-out view (truth yaw 40, n 2; start n 4) | PASS: picks n = 2, angle 40-45, IoU 0.989 | `test_three_quarter_view_estimates_angle_and_roundness` |
| Despike removes arm bulge, keeps neck | PASS | `test_despike_removes_attached_arm_bulge` |
| Reproducible ZIP; refuses failing spec | PASS | `test_pack_is_reproducible_and_refuses_failing_spec` |
| README example commands, run verbatim on a fresh copy | PASS (consistency CONSISTENT; compare FAIL as expected: arms/ears/feet missing; check_spec PASS; ZIP packed) | manual run |
| `blender_build.py` with real Blender | **NOT_TESTED** (no Blender here) | run `tests/test_blender_smoke.py` with `BLENDER=/path/to/blender` |
| `blender_build.py` control flow incl. reference planes and glTF branch | exercised with a mocked `bpy` (finds Python errors only, not Blender API errors) | not shipped |
| Claude Code skill discovery | PASS: the harness discovered and listed `mascot-engineering` (frontmatter parsed) | session skill listing |
| Plugin + marketplace | PASS: `claude plugin validate .` passed with no warnings; installed from a local clone with Claude Code 2.1.328 (1 skill, 5 agents loaded) | `claude plugin marketplace add ./ && claude plugin install mascot-engineering@didibyte-3d` |
| Subagent dispatch | NOT_TESTED here | agent frontmatter uses documented fields (name, description, tools, disallowedTools, model) |
| Real (non-synthetic) AI turnaround images | NOT_TESTED | first real character is the acceptance test |
