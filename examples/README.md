# Examples

`blobby/refs/` front, side (nose toward image-right = `right` view) and back images of a
synthetic mascot, rendered from `blobby/truth_spec.json` and pasted at different sizes and
offsets on white backgrounds, like an AI turnaround. Because the 3D truth is known, you can
check the pipeline's numbers against it (head width 0.48, body width at z = 0.18 is 0.54).

`blobby_inconsistent_side/side_head_too_low.png` is the same mascot with the head drawn
0.08 lower in the side view, the kind of drift AI turnarounds produce. `consistency.py`
reports it as CONFLICT (head bulge at 0.78 in front vs 0.70 in side).
