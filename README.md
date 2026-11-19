# mascot-engineering: measured 2D-to-3D for Claude Code + Blender

> **Status: alpha (0.2.0-alpha).** The measurement pipeline is tested on synthetic mascots
> with known 3D truth (36 tests, CI). The Blender build step has **not yet been verified in
> real Blender**, and the pipeline has not yet been run on real AI-generated turnarounds.
> Please report what breaks. Community project; not affiliated with Anthropic or the Blender Foundation.

A Claude Code skill and five subagents that turn your mascot's front, side and back
pictures into a **measured** 3D blockout in Blender, and **prove it matches** by
rendering the model from the same angles as your pictures and reporting exactly where
it is too wide, too narrow or missing a part.

It started as a ChatGPT-drafted kit, reviewed and rebuilt with Claude. See
`REVIEW_OF_CHATGPT_V1.md` for what was kept, what was wrong and what changed.

## Why this exists

Prompting "make this mascot in Blender" makes the AI guess proportions from looking at a
picture, and you go round in circles. This kit:
1. measures the silhouettes in your images (pixels, not guesses),
2. builds a base body whose front and side outlines match the drawings by construction,
3. fits limbs, ears and tails, and finds eyes and other drawn features, from the same pixels,
4. renders the model with cameras matched to your images and reports, for example,
   `z 0.39-0.51: model TOO NARROW by 0.18 on BOTH edges` (arms missing),
5. tests it against a 3/4 view it was NOT built from (and tunes roundness from it),
6. iterates one part at a time, with every change logged, and gives you a .blend with
   camera-matched reference image planes for refining by hand (plus optional .glb).

## Install

Python packages (once):
```bash
pip install numpy pillow scipy jsonschema scikit-image   # scikit-image optional
```

**As a Claude Code plugin (recommended):** in Claude Code run
```
/plugin install mascot-engineering --marketplace itsdidibyte/mascot-engineering
```
(older Claude Code: `/plugin marketplace add itsdidibyte/mascot-engineering`, then
`/plugin install mascot-engineering@didibyte-3d`). The skill is then
`/mascot-engineering:mascot-engineering` and the agents are `mascot-engineering:<agent>`.

**Without the plugin system:** copy `skills/mascot-engineering` to `~/.claude/skills/` and
`agents/*.md` to `~/.claude/agents/` (all projects), or to `.claude/skills/` and
`.claude/agents/` inside one project.

Blender 4.2 or newer is needed only for the `.blend` build step (`blender` on PATH, or tell
Claude the path).

Check the install (from a clone of this repo):
```bash
python3 -m unittest discover -s tests -v                # 36 tests, Blender ones skip if not installed
BLENDER=/path/to/blender python3 -m unittest tests.test_blender_smoke -v   # once per Blender version
```

## Use

In Claude Code, from your project:
```
/mascot-engineering:mascot-engineering Make a 3D blockout of my mascot. Front: refs/front.png, side (looking right): refs/side.png, back: refs/back.png. Workspace: work/mymascot
```
(Use `/mascot-engineering` if you copied the skill instead of installing the plugin.)
Claude will ask you only things it cannot measure:
- **G1**: if your views disagree (for example, the neck is lower in the side view), which
  view is right for that part. You get `02_views/TURNAROUND.png` to look at.
- **G2**: approve the part plan (which parts, which primitive, what is mirrored).
- **G3**: approve the Blender renders, or accept the listed remaining differences.

## Try it on the example first

```bash
S=skills/mascot-engineering/scripts
python3 $S/intake.py work/blobby --id blobby --origin render_3d \
  --view front=examples/blobby/refs/front.png --view right=examples/blobby/refs/side.png \
  --view back=examples/blobby/refs/back.png
python3 $S/silhouettes.py work/blobby
python3 $S/consistency.py work/blobby          # CONSISTENT
python3 $S/propose_spec.py work/blobby --id body_hull --despike
python3 $S/render_preview.py work/blobby
python3 $S/compare.py work/blobby              # reports missing arms, ears, feet
python3 $S/fit_limb.py work/blobby --id arm_l --x-seed 0.3 --z-range 0.3 0.56 --mirror-id arm_r
python3 $S/fit_limb.py work/blobby --id ear_l --x-seed 0.15 --z-range 0.85 1.0 --mirror-id ear_r --embed 2
python3 $S/features.py work/blobby --add eye:1,2   # eyes found by colour, placed on the surface
python3 $S/render_preview.py work/blobby && python3 $S/compare.py work/blobby   # front IoU ~0.98, only feet left
python3 $S/visual_hull.py work/blobby          # instant 3D envelope: 03_geometry/visual_hull.obj
# held-out 3/4 check:
python3 $S/intake.py work/blobby --id blobby --add --view three_quarter_left=examples/blobby/refs/three_quarter_left.png
python3 $S/silhouettes.py work/blobby --view three_quarter_left
python3 $S/check_three_quarter.py work/blobby
```
`compare.py` exits with code 4 while findings remain; that is expected during iteration.
Swap in `examples/blobby_inconsistent_side/side_head_too_low.png` as the side view to
see the consistency check catch an AI-style drawing error (head 0.08 lower in the side view).

## What you get per character

```
00_intake/ 01_references/ 02_views/ 03_geometry/ 04_build/ 05_validation/ 06_surface_motion/
DECISIONS.md  OPEN_ISSUES.md  HANDOFF.md  manifest.json   (+ a ZIP from pack.py)
```
`04_build/build_spec.json` is the single source of truth; the .blend is rebuilt from it.

## Honest limits

- Silhouettes give outlines. The exact cross-section between the front and side views,
  and dents no view shows (eye sockets, mouth), are labelled `proposed` and refined by eye
  or sculpting after the blockout.
- Inconsistent AI views cannot be made consistent by maths: the kit detects the conflict
  and asks you which view wins.
- The Blender step was written against the Blender 4.2+ Python API but **has not been run
  in the environment where this kit was built** (no Blender there). Run
  `tests/test_blender_smoke.py` once: it builds the example in Blender and checks that
  Blender's renders match the numpy preview pixel for pixel.
- A blockout is not a rig, UV layout or final topology. Those are later stages.

## Repository layout

```
.claude-plugin/        plugin.json, marketplace.json, icon
skills/mascot-engineering/   SKILL.md, reference/ (7 docs), schemas/, scripts/ (+ mascot_lib/)
agents/                5 subagents
tests/                 36 tests incl. synthetic ground truth + red-team cases (CI: .github/workflows)
examples/              synthetic mascot "blobby" turnaround, 3/4 view, inconsistent side view
REVIEW_OF_CHATGPT_V1.md  CHANGELOG.md  TEST_RESULTS.md  CONTRIBUTING.md  LICENSE (MIT)
```

## Roadmap to 1.0

1. Blender smoke test passing on 4.2 LTS and the current release.
2. Three real mascots taken from AI turnaround to an approved blockout, with timings.
3. Then: tag 1.0.

## License

MIT, see `LICENSE`. Example images are synthetic renders made for this project.
