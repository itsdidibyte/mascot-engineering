# Review of the ChatGPT "2D-to-3D Character Engineering Kit" v1.0.0

Reviewer: Claude (independent pass, as requested by `docs/06_CLAUDE_REVIEW_BRIEF.md`).
Scope: every file in `BlackTale_2D3D_Engineering_Kit_v1.zip`, the handbook PDF and SKILL.md.
The v1 baseline was not modified; all changes are in this separate v2 kit.

## Verdict

v1 is a careful **process document** with a strong honesty culture, but it has **no
measuring instrument**. None of its tools reads a size from a reference image, and nothing
renders the model from the reference angles to compare. The agents would still have to guess
proportions by looking at pictures, which is the exact failure behind ten days on one mascot.
It also chose an axis convention that fights Blender. v2 keeps v1's governance ideas and adds
the missing measurement, comparison and Blender-native conventions, with tests that prove them.

## What v1 got right (kept in v2)

- **Truth labels** `observed / inferred / approved_design / proposed / unknown`: excellent;
  v2 extends them to individual parameters (`evidence.parameters`).
- **Gates G0-G6 and "stop instead of inventing"** rules.
- **PASS / FAIL / INCONCLUSIVE / NOT_TESTED** and "never PASS what you did not run".
- **Immutable, hashed references**, decision log, deterministic byte-repeatable ZIP.
- **JSON spec as single source of truth**; local-to-parent transforms; parent-cycle checks.
- **Honest TEST_RESULTS.md** that marks Blender and agent orchestration NOT_TESTED.
- Correct warnings: AI multi-view images may not describe one 3D object; IoU is not 3D truth.

## Findings (severity-ranked)

| # | Sev | Where (v1) | Finding | v2 fix |
|---|---|---|---|---|
| 1 | Critical | `tools/derive_measurements.py:4`, `tools/annotate_landmarks.py:4-5`, `docs/08...md:126` | No tool extracts anything from an image. Landmarks must be "provided"; segmentation is listed as a v2 extension. The agents would eyeball proportions: the root cause of the user's problem. | `silhouettes.py` (masks, normalisation, 101-height profiles), `propose_spec.py` (measured loft) |
| 2 | Critical | `tools/blender_blockout.py:119-125`, `tools/compare_masks.py:2-5` | No reference-matched cameras: one 3/4 "technical preview" only. `compare_masks.py` needs aligned masks that nothing in the kit produces, so the build-render-compare loop cannot run. | canonical canvas + matched ortho cameras in Blender and numpy preview; `compare.py` with per-height, per-edge findings in world axes |
| 3 | High | `docs/02_GEOMETRIC_STANDARD.md:7`, `CLAUDE.md`, schema `coordinate_system` | Axes `+X = character's right, +Y = forward`. In Blender the Front view (Numpad 1) looks along +Y, so it shows the mascot's **back**; X-mirror and Rigify put `.L` on +X, so left/right names are swapped. | Blender-native: faces -Y, +X = character's left; migration rotates v1 specs by conjugation (tested) |
| 4 | High | `.claude/skills/mascot-engineering/SKILL.md:13`, `README.md:30` | Skill depends on `docs/`, `tools/`, `schemas/` at the project root, so it cannot be installed per user for reuse; and it orders reading 6 docs at every session start (defeats on-demand loading; docs recommend SKILL.md + supporting files loaded when needed). | self-contained skill folder using `${CLAUDE_SKILL_DIR}`; SKILL.md routes to 7 reference docs only when needed |
| 5 | High | `docs/04...md:23`, `README.md:41`, `docs/08...md:66` | Blender command lacks `--python-exit-code 1`; Blender returns 0 even when the script raises, so "return nonzero status on error" (`docs/04` §2) is not true as documented. No `--factory-startup` either (user add-ons/startup file change results). | both flags in every command and in the smoke test |
| 6 | High | `docs/01_SYSTEM_AND_GATES.md:38` | G0 **STOP for unclear rights**. AI-generated images always have "unclear" rights, so the pipeline would block the owner's own mascot every time. | rights recorded (`origin`, `rights_note`) and flagged before commercial use; not a modelling blocker |
| 7 | Medium | `tools/check_spec.py:125-128` | `BLOCKOUT_READY` is only a warning; any spec can claim it. | requires a Blender BUILD_LOG whose geometry hash equals the current spec (tested) |
| 8 | Medium | schema `components.evidence` | One evidence status per component, while real parts mix observed widths with proposed depths. Rotation order not stated. | `evidence.parameters`; `rotation_mode: XYZ` (Blender order Rz·Ry·Rx), tested |
| 9 | Medium | `tools/blender_blockout.py:47-61` | Revolved profiles with radius 0 at an end create a ring of coincident vertices and zero-area quads (non-manifold pole), bad for subdivision/remesh. | `meshgen` closes ends with a single pole vertex or a fan; every mesh tested closed, manifold, outward, with analytic volumes |
| 10 | Medium | primitives list | Only ellipsoid/box/cylinder/revolve: mascots need lofts, capsules (limbs), superellipsoids (boxy-round heads) and mirroring. | added all four; `mirror: {id}` with exact reflection (tested) |
| 11 | Medium | `tests/test_pipeline.py` | 9 tests cover bookkeeping only; the IoU test uses all-white vs all-black images; nothing tests geometry, axes, cameras or measurement accuracy. | 31 tests incl. synthetic ground truth (measured widths within 0.006 of truth), axes/camera tests, 9 red-team cases |
| 12 | Medium | `docs/02...md` §1-2, brief Q2 | CV-to-Blender camera conversion is described but implemented nowhere. | `views.blender_to_cv_world_to_camera` / `cv_to_blender_camera`, round-trip and projection tests |
| 13 | Low | `.claude/agents/mascot-qa-auditor.md:4` | The "independent, read-only" QA agent has Write and Edit; nothing enforces independence. | QA: `disallowedTools: Edit`; builder has no Write |
| 14 | Low | 7 agents | Appearance, motion and cloth agents are scheduled in the default pipeline before the shape is even right. | 5 agents; surface/motion planner runs only on request |
| 15 | Low | handbook PDF + 10 docs | The same content in two places (PDF generated from HTML, plus markdown) will drift. | one set of reference docs; no PDF |
| 16 | Low | `requirements.txt` | Lists PyYAML (unused); jsonschema missing makes `check_spec` fail, which is right, but the docs do not say so. | requirements trimmed and explained |

## Answers to the brief's ten questions

1. **Observation vs inference vs decision**: the labels are sufficient; the gap was granularity
   (per component) and enforcement. v2 adds per-parameter labels and `check_spec` enforces
   `observed` -> cites a view/measurement and `approved_design` -> cites a decision.
2. **CV <-> Blender camera transforms**: correctly *described*, never *implemented*. v2
   implements and tests them; for orthographic turnarounds v2 uses exact canvas cameras.
3. **Scale ambiguity**: handled correctly in principle (relative vs metric). v2 makes it
   operational: every view is normalised to character height = 1 on a shared canvas.
4. **Agent feasibility**: v1's agent frontmatter is valid for Claude Code. Subagents start with
   fresh context, so the delegation packet matters (kept, made concrete). Permissions were too
   broad (finding 13).
5. **Do tests validate what their names claim?** Yes, but the claims were small. The real risks
   (measurement, axes, Blender) were untested.
6. **Is the Blender adapter deterministic?** Mostly (no randomness), but it used operators on the
   active object, no factory startup and no exit code. v2 builds meshes from data
   (`bpy.data` + `from_pydata`), same code as the numpy preview.
7. **Component interfaces / UV / materials buildable without guesswork?** Hierarchy yes; UVs,
   rigs and clearances were prose only. v2 keeps those as explicit later-stage plans and does
   not pretend a blockout is rig-ready.
8. **Other 3D apps**: the spec is app-neutral JSON; the visual hull exports OBJ with correct
   Y-up conversion. A glTF exporter is a sensible next step.
9. **Deterministic vs human**: deterministic = masks, normalisation, profiles, lofts, renders,
   comparisons, hashes. Human = canonical view in conflicts, part plan, accepting residual
   differences, everything identity-critical inside the silhouette.
10. **Benchmark**: synthetic ground truth (already in `tests/synthetic.py`), real approved
    turnarounds, deliberately inconsistent AI sheets; measure human minutes to G3, iterations,
    final IoU, conflicts caught, false PASS claims (see reference/06).

## Red-team cases

| Case | v2 behaviour | Test |
|---|---|---|
| Single front view, no profile | depths `proposed`, issue logged | `test_redteam_single_front_view_depth_is_proposed` |
| AI side view inconsistent with front | CONFLICT: head bulge 0.78 vs 0.70 | `test_redteam_inconsistent_ai_side_view` |
| Perspective misread as geometry | `perspective_unknown` views are not measured | `test_redteam_perspective_view_not_measured` |
| Inconsistent scale / cropped references | normalisation removes scale differences; cropped silhouettes refused | `test_normalisation...`, `test_redteam_cropped_reference_is_refused` |
| White/reflective regions punching holes | border-connected background + hole fill | `test_redteam_white_belly_on_white_background_stays_solid` |
| Asymmetric detail wrongly mirrored | check_spec warns using measured symmetry bands | `test_redteam_asymmetric_part_wrongly_mirrored` |
| Hidden back invented without label | `observed` requires evidence; no-side-view depths forced to `proposed` | `test_redteam_structural_errors`, single-view test |
| Parenting cycle, missing material | errors | `test_redteam_structural_errors` |
| Silent change after approval | geometry hash mismatch blocks BLOCKOUT_READY | `test_redteam_blockout_claim_needs_matching_build` |
| Reference image edited | checksum mismatch | `test_redteam_reference_tampering_detected` |
| Version migration changes shape | migration proven shape-preserving | `test_v1_to_v2_preserves_ids_and_world_shape` |
| Rig passes 4 static frames | out of blockout scope; planner must specify in-between pose tests | (planning only) |
| Third-party mesh / unclear derivation | `origin: third_party` + `rights_note` recorded, flagged | check_spec warning |

## Migration plan (v1 -> v2)

1. `python3 scripts/migrate_v1_to_v2.py old/07_blender/build_spec.json new/04_build/build_spec.json`
   (ids kept; axes converted by conjugation; every changed number in MIGRATION_LOG.md;
   `package_mode` reset to SPEC_ONLY; v1 `approved_design` values linked to a decision
   `D-MIGRATED-V1` that says they were not re-confirmed).
2. Set each migrated view's `kind` by hand (v1 had no view kinds), then run silhouettes and
   consistency on the original images.
3. Rebuild in Blender and re-compare before any status above SPEC_ONLY.

## What was actually tested here (evidence) vs not

| Item | Status | Evidence |
|---|---|---|
| v1 unit tests | PASS (9/9) | `python -m unittest discover -s tests` in v1 |
| v2 unit + pipeline + red-team tests | PASS (29 run, 2 skipped) | `python3 -m unittest discover -s tests -v`, see TEST_RESULTS.md |
| Measurement accuracy on synthetic truth | PASS (widths within 0.006 of truth at 900 px) | `test_measured_widths_match_ground_truth` |
| Blender build in a real Blender | **NOT_TESTED** (no Blender in the review environment) | `tests/test_blender_smoke.py` provided; run it once |
| Blender script control flow | exercised with a mocked `bpy` only (catches Python errors, not API errors) | not shipped as a test |
| Claude Code skill discovery | PASS | the harness listed `mascot-engineering` after the files were written |
| Claude Code agent dispatch | NOT_TESTED here | agent files follow the documented frontmatter fields |
| Real AI turnaround images | NOT_TESTED | synthetic only; first real character is the real test |

## Next improvements worth doing

1. Run the Blender smoke test on the target machine and fix any API drift.
2. Limb fitter script (the reference doc gives the numpy recipe; automate it).
3. Interior feature measurement tool (eyes/mouth positions from `front_ref.png` colours).
4. glTF export and a camera-matched reference-image setup in the .blend for sculpting.
5. Benchmark on 3 real mascots against the old prompt-only workflow.
