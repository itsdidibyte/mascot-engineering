# 04 Build, compare, iterate, refine

## Two renderers, one geometry

- `render_preview.py` (numpy, seconds, no Blender): use it inside the iteration loop.
- `blender_build.py` (Blender, authoritative .blend + renders): use it at milestones,
  before release, and whenever subdivision modifiers are in the spec (the preview
  does not simulate them).
Both use `mascot_lib/meshgen.py`, so they draw the same meshes.
`tests/test_blender_smoke.py` proves they agree on the user's Blender version; run it
once per new Blender install (`BLENDER=/path/to/blender python3 -m unittest tests.test_blender_smoke`).

## Blender command

```
blender --background --factory-startup --python-exit-code 1 \
  --python $S/blender_build.py -- WS [--no-render] [--hull]
```
- `--factory-startup`: ignore user add-ons and startup files (reproducible).
- `--python-exit-code 1`: without it Blender exits 0 even when the script fails.
- `--hull`: also loads `03_geometry/visual_hull.npz` as a wireframe reference (not rendered).
- reference planes (default; `--no-ref-planes` to skip): one image empty `REF_<view>` per
  measured view, showing `02_views/<view>_ref.png` behind the character, scaled and placed
  exactly on the build canvas, visible only in that axis-aligned view, never rendered,
  packed into the .blend. This is the standard professional modelling setup, but aligned
  by measurement instead of by hand.
- `--export-gltf`: also writes `<id>.glb` of the components (for engines, web viewers).
Outputs `04_build/blender/<id>.blend`, `04_build/renders/<view>_mask.png|_shaded.png`,
`04_build/blender/BUILD_LOG.json` (Blender version, geometry hash, objects, world bboxes).
Then: `python3 $S/compare.py WS --source blender`.

Ask the user before running Blender the first time in a session (it may be slow or
not installed). If `blender` is not on PATH, ask for its path; do not search the disk.

## Held-out 3/4 view

Front + side fix widths and depths, not the cross-section shape between them. If the
owner has a 3/4 picture (register it as `three_quarter_left` / `three_quarter_right`, named
by where the nose points), `check_three_quarter.py WS` sweeps the orbit angle, reports the
best-matching angle and IoU, and with `--tune-n <loft_id> --apply` picks the loft exponent
`n` that explains the 3/4 view (labelled `inferred`). A round body makes the angle hard to
pin down; the report says so. If the 3/4 picture disagrees badly, it may simply be off-model:
ask the owner.

## Reading compare results

`05_validation/COMPARE_<source>.md` lists findings like
`z 0.39-0.51 (lower body): model TOO NARROW (missing) by 0.182 on BOTH edges`.
- `BOTH edges`, same sign -> change the part's SIZE (radius, half-width).
- One edge excess, opposite edge missing -> the part is SHIFTED toward the excess side.
- Missing over a band with no part there -> a part is absent (arm, ear, tail).
- Diff image: grey = match, RED = reference only (add material), BLUE = model only (remove).
Map the edge to a parameter: front/back edges are X (`+X` = character's left), side
edges are Y (`-Y` = front). Then change that component's parameter.

## Iteration rules

1. One component group per change; write it to `04_build/CHANGELOG.md`:
   `ITER-07 | head | radii[0] 0.24 -> 0.22 | front z 0.70-0.86 BOTH edges excess 0.021 | IoU front 0.951 -> 0.962`
2. Keep the change only if the target band improves and no other view gets worse by
   more than 0.005 IoU.
3. Never hand-edit the .blend. If the owner sculpts in Blender, that is a new stage
   (see Refinement) and the spec stays the record of the blockout.
4. After 3 non-improving iterations on the same band: stop and ask the owner (the
   references probably disagree, or the part needs a different primitive).

## Refinement after an approved blockout (G3 passed)

The blockout is a measured scaffold, not final topology. Typical next steps, done
as separate, logged stages in Blender:
1. Join body parts and voxel-remesh (or Boolean union) for one clean surface.
2. Subdivision + shrink/smooth to remove primitive seams; re-run compare to confirm
   silhouettes stayed within tolerance.
3. Sculpt features that silhouettes cannot show, using the normalised
   `02_views/*_ref.png` images as camera-matched background references
   (same canvas as the render cameras).
4. Retopology for animation, UVs, materials (G4), rig (G5).
Each stage keeps the previous approved file and is checked with the same cameras.
