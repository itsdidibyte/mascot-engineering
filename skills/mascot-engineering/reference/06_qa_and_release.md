# 06 QA, release and benchmarks

## QA statuses

Each requirement: `PASS` (executed, evidence path given), `FAIL`, `INCONCLUSIVE`
(executed but the data cannot decide), `NOT_TESTED` (not executed, say why).
Never PASS from reading a document.

## QA checklist (auditor fills QA_REPORT.md)

| # | Requirement | How to check |
|---|---|---|
| 1 | spec valid | `check_spec.py WS` exit 0 |
| 2 | references untouched | `check_spec` checksums |
| 3 | every view labelled correctly | overlay images: side view nose direction vs kind |
| 4 | masks clean | `*_overlay.png`: no shadow/text/floor inside the red outline |
| 5 | cross-view conflicts resolved | `CONSISTENCY.md` has no CONFLICT without a decision |
| 6 | numbers traceable | sample 5 component parameters back to MEASUREMENTS or decisions |
| 7 | depth honesty | no `observed` depth without a side view |
| 8 | mirroring justified | no check_spec mirror warnings without a decision |
| 9 | silhouettes match | `COMPARE_blender.json` (or preview if no Blender: say so) |
| 10 | build reproducible | BUILD_LOG geometry hash == current spec; Blender version recorded |
| 11 | release claim honest | package_mode matches evidence; open blocking issues = 0 |
| 12 | tests | `python3 -m unittest discover -s tests` in the kit (if available) |

## Release checklist (orchestrator)

1. QA report has no FAIL on claimed items.
2. Set `package_mode` and `release_evidence` (`blender_build_log`, `compare_report`).
3. `check_spec.py` PASS.
4. Update `HANDOFF.md`: status, how to rebuild (exact commands), what is proposed vs
   observed, open questions, next stage.
5. `pack.py WS OUT.zip` -> give the user the path. The ZIP contains `manifest.json`
   with file hashes, geometry hash and the claim.

## Package layout

```
<character>/
  00_intake/       SOURCE_REGISTER.json, INTAKE_LOG.md
  01_references/   original images (immutable)
  02_views/        masks, normalised refs, overlays, profiles, CONSISTENCY.*, TURNAROUND.png
  03_geometry/     MEASUREMENTS.json, PART_PLAN.md, visual_hull.*
  04_build/        build_spec.json, CHANGELOG.md, preview/, blender/, renders/
  05_validation/   COMPARE_*.md|json, *_diff.png, QA_REPORT.md
  06_surface_motion/ (optional) MATERIALS.md, RIG_PLAN.md
  DECISIONS.md  OPEN_ISSUES.md  HANDOFF.md  manifest.json
```

## Benchmark (does the kit save time?)

Keep a small set: (a) 3+ synthetic characters with known 3D truth (see
`tests/synthetic.py`), (b) 3+ real approved turnarounds, (c) 2+ deliberately
inconsistent AI turnarounds. Track per character: minutes of human time to G3, number
of iterations, final IoU per view, conflicts caught at G1, false PASS claims (target 0).
Compare against the old "prompt and eyeball" workflow on the same characters.
