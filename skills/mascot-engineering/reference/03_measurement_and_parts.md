# 03 Measurement and part decomposition

## What the measurements are

`silhouettes.py` writes `02_views/<view>_profile.json`: for 101 heights
z = 0.00..1.00 (x character height) the list of silhouette **runs** `[h_left, h_right]`
in world units. One run = one solid span in that row. Several runs = separate parts
in that row (arms beside the body, two feet, two ears).

Convert runs to world axes with the view table in `02_coordinates_and_cameras.md`:
front `X = h`; back `X = -h`; left `Y = h`; right `Y = -h`.

Silhouettes give the **outer extent** only. Cross-section shape between views,
concavities (eye sockets, mouth, belly button) and anything hidden in every view are
not measurable: label them `proposed` and resolve visually or by owner decision.

## Step 1: measured base body

`propose_spec.py WS --id body_hull` builds an `elliptical_loft`: at each height an
ellipse (or superellipse, `--n`) with half-width/centre from the front view and
half-depth/centre from the side view. For blob, bean, egg, ghost, plush and
round-animal mascots this is often 85-95 % of the shape in one step.

Read its warnings:
- `sudden width/depth jumps near z=[...]`: another part merges into the silhouette
  there (arm touching the body, ears on the head, feet). Split at those heights.
- `gaps`: rows where the tracked part is absent (top of head, between feet). Normal.

## Step 2: split into parts

Use `CONSISTENCY.json` extrema: width **minima** (`min`) are natural part boundaries
(neck, waist, ankle). Typical split:

```
python3 $S/propose_spec.py WS --id body --z-range 0.03 0.62 --replace
python3 $S/propose_spec.py WS --id head --z-range 0.58 1.0
```
Overlap neighbouring slices by ~0.02-0.04 so no gap shows at the seam.
Delete `body_hull` once the split parts reproduce it (compare before and after).

## Step 3: appendages (primitive guide)

| Part | Primitive | Parameters from |
|---|---|---|
| Head/torso masses | `elliptical_loft` (measured) or `ellipsoid` | front + side runs |
| Boxy heads, robots | `superellipsoid` (exponents 3-6) or loft `--n 3..4` | widths + owner choice of roundness |
| Arms, legs, tails, antennae | `capsule` (`radius_top` for taper) | run centres along the limb (fit below) |
| Ears, horns | `ellipsoid` / `capsule` / loft with `--front-seed` | front runs at ear heights; side often shows only the base |
| Feet, hands (blockout) | `ellipsoid` / `superellipsoid` | bottom rows (two runs) + side length |
| Eyes, nose, buttons | `ellipsoid` parented to the head | front-view features (inside the silhouette: see below) |
| Rings, collars, bases | `cylinder` / `revolved_profile` | widths + heights |

Limbs, ears, tails: `fit_limb.py` fits a tilted capsule to the rows where the part is a
separate silhouette run (straight rows only, so rounded tips and body-clipped rows do not
bias the angle). On the synthetic test mascot it recovers the arm radius within 0.002,
tilt within 3 deg and position within 0.012 of the truth.
```
python3 $S/fit_limb.py WS --id arm_l --x-seed 0.3 --z-range 0.30 0.56 --mirror-id arm_r
python3 $S/fit_limb.py WS --id ear_l --x-seed 0.15 --z-range 0.85 1.0 --mirror-id ear_r --embed 2
```
`--x-seed` = world X near the part (+X = character's left); `--z-range` = heights where it
is visible; `--y-seed` only if the side view shows it separate from the body (otherwise Y
is taken from the body centre and labelled `inferred`). Use `--dry-run` to see the fit first.
Use `--mirror-id` only if the front is symmetric there. The part must be a separate run in
the front/back view for at least 3 heights; a tail hidden behind the body in front view is
built by hand from the side-view runs (capsule, `inferred`) and checked with compare. Feet and hands are often better as
ellipsoids sized from the bottom rows (two runs) and the side length.

## Features inside the silhouette (eyes, mouth, belly patch)

They do not change the silhouette, so compare.py cannot check them. `features.py WS`
finds colour blobs inside the front silhouette, prints their centre/size/colour and the
surface depth Y at that point (from the measured cross-section), flags blobs with the body's
hue as probable shading, and draws `03_geometry/FEATURES.png`. Check the picture, then
`features.py WS --add eye:1,2` turns chosen blobs into ellipsoids: X/Z/size `observed`,
surface Y `inferred`, protrusion `proposed`. On the test mascot the eyes land within 0.002.

## Truth labels

| Label | Meaning | Required |
|---|---|---|
| observed | measured from a named view | view or measurement id in `reference_ids` |
| inferred | derived (symmetry, fit, other view at that height) | `uncertainty_note` |
| approved_design | owner decided the value | `decision_id` |
| proposed | a suggestion waiting for the owner | `uncertainty_note` |
| unknown | not determinable | leave out or null; log an issue |

Use `evidence.parameters` for mixed cases, e.g. a loft whose widths are observed and
whose depths are proposed.

## PART_PLAN.md template (owner approves this at G2)

```
| id | part | primitive | parent | mirror | width/height source | depth source | notes |
|----|------|-----------|--------|--------|---------------------|--------------|-------|
| body | body | elliptical_loft | - | no | front (observed) | right (observed) | z 0.03-0.62 |
| head | head | elliptical_loft | - | no | front (observed) | right (observed) | z 0.58-1.0 |
| arm_l | arm | capsule | - | arm_r | front fit (inferred) | side base (inferred) | tilt 35 deg |
| eye_l | eye | ellipsoid | head | eye_r | front_ref (observed) | proposed 0.02 | protrudes 0.005 |
Thresholds: IoU >= 0.95, edge <= 0.02 H (decision D-003)
Questions for the owner: ...
```
