# Contributing

This repository holds the mascot-engineering kit (skill, agents, tests). For 2D-to-3D
character work, use the `mascot-engineering` skill and its scripts; never estimate
proportions by eye. World axes: Z up, character faces -Y, +X is the character's left.
Run `python3 -m unittest discover -s tests` after changing anything in
`skills/mascot-engineering/scripts/`. Do not modify files in `examples/` or
`tests/fixtures/` without saying why.

Open an issue with: Blender version, OS, the command you ran, and (if you can share them)
the reference images or the workspace's `02_views/*_overlay.png` and `05_validation/*.md`.
Pull requests: keep `python -m unittest discover -s tests` green and add a test for
every bug you fix.
