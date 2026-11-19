---
name: mascot-engineering
description: Turn 2D mascot/character reference images (front, side, back turnaround) into a measured, versioned 3D spec and a Blender blockout that matches the drawings, using deterministic silhouette measurement, camera-matched renders and specialist subagents. Use when the user wants a 3D model, Blender build, proportions, turnaround check or 3D documentation package from 2D character art.
---

# Mascot engineering: 2D references -> measured spec -> matching Blender blockout

You are the technical director. The job is to make a 3D blockout whose silhouettes
match the approved 2D views, and to prove it with numbers, not adjectives.

**Core rule: never eyeball proportions.** Every size and position comes from
`scripts/` measurements of the reference pixels, from an owner decision, or is
labelled `proposed`. Models are fixed by reading `compare.py` findings, never by
"it looks a bit wide".

Scripts live in `${CLAUDE_SKILL_DIR}/scripts` (call it `$S`). Run them with
`python3 $S/<script>.py --help` for options. Requirements: Python 3.10+, numpy,
Pillow, scipy, jsonschema (scikit-image optional). Blender 4.2+ only for the build step.

## Load reference docs only when needed

| When | Read |
|---|---|
| Starting a project, deciding gates, stop rules | `reference/01_pipeline_and_gates.md` |
| Anything about axes, view kinds, left/right, cameras | `reference/02_coordinates_and_cameras.md` |
| Measuring, splitting into parts, choosing primitives | `reference/03_measurement_and_parts.md` |
| Building in Blender, iterating, refining | `reference/04_build_and_iterate.md` |
| Delegating to subagents | `reference/05_agents.md` |
| QA, release, ZIP | `reference/06_qa_and_release.md` |
| What each script does and does not do | `reference/07_tool_reference.md` |

## Workflow (one workspace folder per character)

**G0 Intake.** Ask the user which image is front / side / back if filenames do not
say. For a side image ask, or look: **the way the nose points names the view**
(nose toward image-right -> `right`). Then:
`python3 $S/intake.py WS --id <slug> --origin ai_generated --view front=... --view right=... --view back=...`

**G1 Reference lock.**
`python3 $S/silhouettes.py WS` then `python3 $S/consistency.py WS`.
Open every `02_views/*_overlay.png` and `TURNAROUND.png` yourself (Read tool).
Fix bad masks (shadows, text, floor) with `--exclude VIEW:x0,y0,x1,y1`.
If CONSISTENCY is `CONFLICT`, STOP and ask the owner which view rules each listed
height band. Record the answer in `DECISIONS.md` and `decisions[]`. Never average.

**G2 Measured spec + part plan.**
`python3 $S/propose_spec.py WS --id body_hull --despike` gives a measured base body
(`--despike` removes bulges where arms/ears touch it). Then measure the rest instead of
guessing: `fit_limb.py` (arms, legs, ears, tails as tilted capsules) and `features.py`
(eyes, nose, patches inside the outline, placed on the surface).
Write `03_geometry/PART_PLAN.md` (parts, primitive per part, parent, mirrored
or not, which numbers are observed vs proposed), using
`reference/03_measurement_and_parts.md`. **Show the plan to the owner and get a yes**
before building parts. Optional: `visual_hull.py WS` for an instant 3D envelope.

**G3 Blockout loop** (repeat until PASS or the owner accepts the listed differences):
1. Edit ONE component group in `04_build/build_spec.json`.
2. `python3 $S/check_spec.py WS`
3. `python3 $S/render_preview.py WS && python3 $S/compare.py WS`
4. Read `05_validation/COMPARE_preview.md` and the `*_diff.png` images
   (red = model missing, blue = model excess). Fix the largest finding next.
5. Log the change in `04_build/CHANGELOG.md` (component, parameter, old -> new, why).
If a 3/4 picture exists, run the held-out check `python3 $S/check_three_quarter.py WS`
(add `--tune-n <loft_id>` to fit the cross-section roundness that front/side cannot show).
At milestones and before any release, build in Blender (if installed and the user agrees):
`blender --background --factory-startup --python-exit-code 1 --python $S/blender_build.py -- WS`
then `python3 $S/compare.py WS --source blender`. The .blend contains camera-matched
reference image planes for modelling/sculpting over the drawings; add `--export-gltf`
for a .glb.

**G4/G5 (only when asked).** Materials, UV, rig and motion planning go to the
surface-motion planner. A blockout is not a rig.

**G6 Release.** Independent QA (`mascot-qa-auditor`), then
`python3 $S/pack.py WS OUT.zip`. Give the user the ZIP path.

## Non-negotiables

1. Reference images are immutable (hashed at intake; `check_spec` detects edits).
2. Truth labels on every number: `observed`, `inferred`, `approved_design` (needs a
   decision id), `proposed`, `unknown`. No side view means every depth is `proposed`.
3. `build_spec.json` is the single source of truth. Prose and images derive from it.
4. One parameter group per iteration; no hand edits in Blender that are not in the spec.
5. Never write PASS for something not executed. `NOT_TESTED` and `INCONCLUSIVE` are fine.
6. `BLOCKOUT_READY` only with a Blender `BUILD_LOG.json` whose geometry hash matches the
   current spec (`check_spec` enforces it). `PRODUCTION_READY` needs the owner's G6 decision.
7. Mirror a part only where `CONSISTENCY.md` shows the front is symmetric, or with a decision.
8. Ask the owner only questions that block progress (canonical view, part plan, accept
   differences). Keep each question short and show the image it is about.

## Agents

If the Agent tool and the project/user agents exist, delegate per
`reference/05_agents.md`: `mascot-reference-analyst` (G0-G1),
`mascot-geometry-architect` (G2-G3 spec + preview loop), `mascot-blender-builder`
(Blender builds), `mascot-qa-auditor` (independent G6), `mascot-surface-motion-planner`
(G4/G5, on request); when installed as a plugin the names carry the prefix
`mascot-engineering:`. Run stages in order, never two writers on `build_spec.json` at
once. If agents are unavailable, do the roles yourself in order and say so.

## Final report to the user

Status (`SPEC_ONLY` / `BLOCKOUT_READY`), per-view IoU and remaining findings, what was
actually run (commands) vs not, open decisions for the owner, file/ZIP paths.
