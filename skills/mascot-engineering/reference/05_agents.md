# 05 Agents and delegation

Subagents start with a fresh context: they do not see this conversation, the skill
text or files you have read. Every delegation must carry the packet below.
Agents come with the plugin install, or are copied to `.claude/agents/` (one project) or
`~/.claude/agents/` (all projects). Installed as a plugin, their names carry the plugin
prefix, e.g. `mascot-engineering:mascot-geometry-architect`.

## Who does what

| Agent | Gates | Writes (only) | Runs |
|---|---|---|---|
| `mascot-reference-analyst` | G0, G1 | `00_intake/`, `01_references/`, `02_views/`, `views[]` in the spec | intake, silhouettes, consistency |
| `mascot-geometry-architect` | G2, G3 loop | `03_geometry/`, `components[]`/`materials[]` in the spec, `04_build/preview/`, `04_build/CHANGELOG.md`, `05_validation/COMPARE_preview.*` | propose_spec, visual_hull, check_spec, render_preview, compare |
| `mascot-blender-builder` | G3 milestones | `04_build/blender/`, `04_build/renders/`, `05_validation/COMPARE_blender.*` | blender_build, compare --source blender |
| `mascot-qa-auditor` | G6 | `05_validation/QA_REPORT.md`, `05_validation/QA_ISSUES.json` | read-only checks, check_spec, tests |
| `mascot-surface-motion-planner` | G4, G5 (on request) | `06_surface_motion/` | none required |
| orchestrator (you, with this skill) | all | `DECISIONS.md`, `OPEN_ISSUES.md`, `HANDOFF.md`, `decisions[]`, `package_mode`, `release_evidence`, ZIP | pack |

Order: analyst -> (owner G1) -> architect -> (owner G2 plan) -> architect loop with
builder at milestones -> (owner G3) -> optional planner -> QA -> (owner G6) -> pack.
Never run two agents that write `build_spec.json` at the same time.
The QA auditor must not be the agent (or session turn) that produced what it audits.

## Delegation packet (put all of it in the prompt)

```
task_id: G2-001
agent: mascot-geometry-architect
skill_dir: <absolute path of this skill>       # scripts at <skill_dir>/scripts
workspace: <absolute path>
goal: measured part plan + components for head/body; preview loop until compare PASS or 6 iterations
inputs: 02_views/CONSISTENCY.md, *_profile.json, decisions D-001..D-002
must_not: change views[] or decisions[]; mirror parts in asymmetric bands; eyeball sizes
thresholds: IoU >= 0.95, edge <= 0.02 H
return: status (complete|blocked|partial), files written, commands run with exit codes,
        per-view IoU, open questions for the owner (max 3), proposed decisions
```

## What to do with returns

- Verify claims cheaply yourself: re-run `check_spec.py` and read the compare JSON
  before telling the user anything passed.
- Turn the agent's questions into one short owner question with the relevant image.
- If an agent returns `blocked`, do not paper over it; report it.

## No agents available

Do the same roles yourself in the same order and say "ran sequentially without
subagents". For QA without a separate agent, state that the audit is not independent.
