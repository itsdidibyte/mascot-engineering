# 01 Pipeline, gates and stop rules

## What this pipeline can and cannot do

Can do: measure orthographic reference silhouettes exactly, build a 3D blockout
whose front/side/back silhouettes match them within a stated tolerance, prove it
with renders and numbers, and keep every number traceable.

Cannot do: recover what no view shows (concave details, the exact cross-section
between front and side, hidden undersides), invent true physical size, or make
inconsistent AI views agree. Those stay `proposed` until the owner decides.

## Getting good inputs (tell the user this at G0 when inputs are weak)

Best: one turnaround sheet or separate images of the SAME design version with
- front, side (profile), back; plus one 3/4 view, which is not used to build but to TEST
  the model from an angle it was not built from (the professional "held-out view");
- orthographic look (no strong perspective), neutral pose (A- or T-pose, mouth closed);
- whole character visible with a margin (nothing cropped), feet on one ground line;
- plain flat background, no ground shadow, no text, no props overlapping the body.
When generating with an image model, ask for "orthographic character turnaround sheet,
front view, side view, back view, same character, neutral A-pose, plain white
background, flat lighting, no shadow, full body". Then still run the consistency check:
AI turnarounds often move the neck, eyes or ears between views.

## Gates

| Gate | Owner | Output | Pass condition | Human checkpoint |
|---|---|---|---|---|
| G0 Intake | reference analyst | `00_intake/`, `01_references/`, views in spec | each image labelled with a kind; hashes recorded | confirm which image is which view |
| G1 Reference lock | reference analyst | masks, overlays, profiles, `CONSISTENCY.md`, `TURNAROUND.png` | masks clean; no `CONFLICT` (or owner decided) | **owner picks canonical view for every CONFLICT band** |
| G2 Measured spec | geometry architect | `MEASUREMENTS.json`, `PART_PLAN.md`, components | `check_spec` PASS; every number labelled | **owner approves the part plan** |
| G3 Blockout | architect (preview loop) + builder (Blender) | `.blend`, renders, `COMPARE_*.md` | all canonical views PASS thresholds, or owner accepts listed differences | **owner approves renders** |
| G4 Surface | surface-motion planner | `06_surface_motion/MATERIALS.md`, palette | on request only | owner approves colours |
| G5 Motion plan | surface-motion planner | `06_surface_motion/RIG_PLAN.md` | on request only | owner approves pivots |
| G6 Release | QA auditor + orchestrator | `QA_REPORT.md`, `manifest.json`, ZIP | QA has no FAIL on claimed items | **owner signs the release claim** |

Default thresholds (agree project values at G2, record them as a decision):
silhouette IoU >= 0.95 per canonical view, edge error <= 0.02 x character height.

## Package modes

- `SPEC_ONLY` (default): measurements and spec exist; no Blender proof.
- `BLOCKOUT_READY`: `check_spec` PASS, Blender `BUILD_LOG.json` geometry hash equals the
  current spec, compare report linked in `release_evidence`, no blocking issues.
- `PRODUCTION_READY`: never set by an agent alone; needs the owner's G6 decision.

## Stop rules (stop, report, ask)

- A view's silhouette touches the image border (cropped) and the owner did not accept it.
- CONSISTENCY `CONFLICT` without an owner decision.
- No front/back view (widths unmeasurable).
- `check_spec` FAIL.
- Three iterations in a row that make a previously passing view worse: revert, then ask.

Non-blocking (proceed, label, log an issue): no side view (depth `proposed`), no back
view, unknown image origin or rights (record `origin` and `rights_note`; flag before
commercial use; it does not block modelling your own mascot).

## Iteration protocol

change one named component group -> `check_spec` -> preview render -> compare ->
keep only if the target band improves and no other view regresses -> log in
`04_build/CHANGELOG.md`. Re-open a frozen gate only with a written decision.

## Decisions

Every owner answer that changes geometry gets an entry in `build_spec.json`
`decisions[]` (`id`, `gate`, `summary`, `decided_by`, `date`, `affects`) and a line in
`DECISIONS.md`. Silence or "looks close" is not approval.
