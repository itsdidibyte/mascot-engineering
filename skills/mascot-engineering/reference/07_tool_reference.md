# 07 Tool reference (what each script really does)

All scripts: `python3 $S/<name>.py --help`. Exit code 0 = success.

| Script | Does | Does NOT |
|---|---|---|
| `intake.py` | creates the workspace, copies + hashes images, registers views (kind, assumed orthographic) | guess view kinds, rights or cameras |
| `silhouettes.py` | background/alpha mask, hole fill, speck removal, crop detection, normalisation to the canonical canvas, overlays, 101-height run profiles | remove ground shadows automatically (use `--exclude`), measure perspective views |
| `consistency.py` | front-vs-back widths, left-vs-right depths, neck/bulge heights across views, front symmetry bands, TURNAROUND.png; exit 3 on CONFLICT | decide which view is right |
| `propose_spec.py` | measured `elliptical_loft` per part (front widths x side depths), slice by height, seed per part, jump warnings, `--despike` removes bulges where appendages touch; writes MEASUREMENTS.json | invent depth (uses `proposed` + issue when no side view), fit angled limbs (use fit_limb.py) |
| `fit_limb.py` | tilted capsule (radius, length, angle, position) from rows where a limb/ear/tail is its own silhouette run; optional side-view tilt; mirror twin | see the hidden attached end (pushed `--embed` radii into the body, `proposed`) |
| `features.py` | colour blobs inside the front silhouette (eyes, nose, patches) with centre, size, colour, surface depth; shading flagged; `--add` makes ellipsoids | decide which blobs are real features (look at FEATURES.png) |
| `check_three_quarter.py` | held-out 3/4-view IoU with orbit-angle sweep; `--tune-n` fits loft roundness from that view | trust an off-model AI 3/4 picture; it only reports |
| `visual_hull.py` | voxel carving of all measured silhouettes -> mesh (.npz/.obj) + reprojection IoU | carve concavities no view shows |
| `render_preview.py` | numpy orthographic masks + flat-shaded previews from the spec | simulate subdivision; replace Blender |
| `compare.py` | IoU, per-height edge errors in world axes, merged BOTH-edge findings, diff images; exit 4 on FAIL | judge features inside the silhouette (eyes, mouth) |
| `check_spec.py` | schema, ids, parents, cycles, materials, evidence links, closed/outward meshes, checksums, mirror vs asymmetry, honest package_mode | judge artistic quality |
| `blender_build.py` | deterministic .blend from the spec (bpy.data, no operators on objects), matched ortho cameras, packed camera-matched reference image planes, Workbench mask + shaded renders, optional .glb, BUILD_LOG.json | rig, UV, retopology, final materials |
| `migrate_v1_to_v2.py` | converts v1 (ChatGPT kit) specs: axes rotated by conjugation, ids kept, every change logged | migrate v1 bevels (dropped, logged) |
| `pack.py` | refuses failing specs, manifest with hashes + geometry hash + claim, byte-reproducible ZIP | certify legal rights or quality |

`mascot_lib/`: `views.py` (axes, canvas, cameras, OpenCV conversion), `meshgen.py`
(all primitives, transforms, mirroring), `silhouette.py`, `analysis.py`, `raster.py`,
`drawing.py`, `workspace.py`. `meshgen.py` and `views.py` need only numpy so Blender
can import them.

Geometry types (local frame): `ellipsoid {radii}`, `superellipsoid {radii, exponents}`,
`box {dimensions}`, `cylinder {radius, depth}` (along Z), `capsule {radius, length,
radius_top?}` (along Z), `revolved_profile {profile [[r,z]..]}` (z increasing),
`elliptical_loft {stations [[z,cx,a,cy,b]..], n}`. Transforms: `location`,
`rotation_euler_deg` (XYZ order, Blender default), optional `scale`; local to
`parent_id`. `mirror: {id}` creates the twin mirrored across the parent's X = 0 plane.
