# Changelog

## 0.2.0-alpha (2026-11-19) - first public release (internal build "v2.1")

Repository layout: plugin + marketplace at the repo root (`.claude-plugin/`, `skills/`, `agents/`). MIT license. CI runs the test suite.


Added
- `check_three_quarter.py`: held-out 3/4-view check with orbit-angle sweep, angle
  uncertainty, and `--tune-n` to fit loft cross-section roundness (recovers n = 2 and the
  40 deg angle within 5 deg on synthetic truth). New view kinds three_quarter_left/right.
- `fit_limb.py`: tilted capsule fit for arms/legs/ears from free silhouette rows
  (synthetic arm: radius +0.002, tilt -3 deg, position within 0.012).
- `features.py`: eyes/nose/patches found by colour inside the silhouette, shading flagged,
  placed on the measured surface (synthetic eyes within 0.002).
- Blender: packed camera-matched reference image planes per view; `--export-gltf`.
Changed
- `propose_spec.py --despike` now removes only outward bulges (attached appendages) by
  interpolation, leaving necks and waists untouched.

## 0.1.0 (2026-11-19, unreleased; internal build "v2.0") - review rebuild of the ChatGPT v1.0.0 kit

Added
- Deterministic measurement: silhouette extraction (alpha / border-colour flood fill, hole
  fill, speck removal, crop detection), canonical-canvas normalisation, 101-height run profiles.
- Cross-view consistency check (front/back widths, left/right depths, feature heights,
  symmetry bands) and TURNAROUND.png contact sheet.
- Measured `elliptical_loft` from front x side silhouettes (`propose_spec.py`) with
  per-parameter truth labels, slicing, seeds, jump warnings, despike.
- Feedback loop: numpy preview renderer + `compare.py` (IoU, per-height edge errors in world
  axes, diff images). Blender builder renders the same camera-matched views.
- Visual hull (voxel carving) as an instant 3D envelope and a view-agreement check.
- New primitives: superellipsoid, capsule (tapered), elliptical_loft; explicit `mirror`.
- `check_spec`: mesh closed/outward checks, evidence-link resolution, decision-backed
  `approved_design`, mirror-vs-asymmetry warning, BLOCKOUT_READY bound to the Blender build's
  geometry hash.
- `migrate_v1_to_v2.py` preserving ids and world shape (tested).
- 31 tests: unit, synthetic ground truth end-to-end, 9 red-team cases, Blender smoke test.

Changed
- Axes are Blender-native (faces -Y, +X = character's left). v1 used +Y forward / +X right,
  which shows the back in Blender's Front view and swaps .L/.R.
- Skill is self-contained under `.claude/skills/mascot-engineering/` and uses
  `${CLAUDE_SKILL_DIR}`, so it can be installed per user; SKILL.md loads reference docs on demand.
- 7 agents -> 5 with tool limits (QA cannot Edit; builder cannot Write).
- Rights/provenance is recorded, not a modelling blocker for the owner's own designs.
- Blender build: `--factory-startup`, `--python-exit-code 1`, meshes via `bpy.data`
  (no object operators), Workbench renders, BUILD_LOG.json.

Removed
- 25-page PDF handbook and duplicated docs (single source: reference/ docs).
- Box bevel (use superellipsoid); `PRODUCTION_READY` cannot be reached without an owner decision.
