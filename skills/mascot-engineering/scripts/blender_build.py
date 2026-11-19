"""Deterministic Blender build of a build_spec v2, plus camera-matched renders.

Run (note --factory-startup and --python-exit-code: without the latter Blender
exits 0 even when this script raises):

    blender --background --factory-startup --python-exit-code 1 \
        --python blender_build.py -- WORKSPACE [--spec PATH] [--no-render] [--hull]
        [--no-ref-planes] [--export-gltf]

Outputs (inside WORKSPACE/04_build/):
    blender/<character_id>.blend           the scene (one object per component, named by id)
    renders/<view_id>_mask.png             flat silhouette (alpha) on the canonical canvas
    renders/<view_id>_shaded.png           Workbench preview, same camera
    blender/BUILD_LOG.json                 Blender version, geometry hash, objects, world bboxes
    blender/<character_id>.glb             with --export-gltf (glTF 2.0; Y-up conversion by the exporter)

The .blend also holds one camera per measured view (CAM_<view>) and, unless
--no-ref-planes, a camera-matched reference image (REF_<view>, an image empty that
shows only in that axis-aligned view and never renders): the professional setup for
modelling and sculpting over the drawings, aligned exactly with the build cameras.

Meshes come from mascot_lib.meshgen (same code as the numpy preview), so the two
renderers must agree; tests/test_blender_smoke.py checks that on your machine.
Tested API surface: bpy.data meshes/objects/materials/cameras, Workbench engine.
Target Blender 4.2 LTS or newer.
"""
import json
import math
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402

from mascot_lib import meshgen  # noqa: E402
from mascot_lib.views import Canvas, blender_camera_for_view  # noqa: E402
from mascot_lib.workspace import geometry_hash, load_spec, save_json, workspace_of  # noqa: E402


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("usage: blender -b --factory-startup --python-exit-code 1 --python blender_build.py -- WORKSPACE [--spec PATH] [--no-render] [--hull]")
    ws = Path(argv[0]).resolve()
    spec = None
    if "--spec" in argv:
        spec = Path(argv[argv.index("--spec") + 1]).resolve()
    return ws, spec, "--no-render" in argv, "--hull" in argv, "--no-ref-planes" in argv, "--export-gltf" in argv


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    return scene


def make_material(m):
    mat = bpy.data.materials.new(m["id"])
    rgba = tuple(float(v) for v in m["base_color_rgba"])
    mat.diffuse_color = rgba            # used by Workbench MATERIAL colour
    try:
        if mat.node_tree is None:
            mat.use_nodes = True
    except AttributeError:
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = float(m.get("roughness", 0.5))
        bsdf.inputs["Metallic"].default_value = float(m.get("metallic", 0.0))
    mat["evidence_status"] = m.get("evidence_status", "unknown")
    return mat


def make_object(comp, collection):
    verts, faces = meshgen.component_mesh(comp)
    mesh = bpy.data.meshes.new(comp["id"] + "_mesh")
    mesh.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(int(i) for i in f) for f in faces])
    if mesh.validate(verbose=False):
        raise RuntimeError(f"{comp['id']}: mesh needed repair; meshgen output is invalid")
    try:
        mesh.shade_smooth()
    except AttributeError:
        for p in mesh.polygons:
            p.use_smooth = True
    obj = bpy.data.objects.new(comp["id"], mesh)
    collection.objects.link(obj)
    obj.rotation_mode = "XYZ"
    obj.location = tuple(float(v) for v in comp["location"])
    obj.rotation_euler = tuple(math.radians(float(v)) for v in comp.get("rotation_euler_deg", [0, 0, 0]))
    obj.scale = tuple(float(v) for v in comp.get("scale", [1, 1, 1]))
    obj["component_id"] = comp["id"]
    obj["geometry_type"] = comp["geometry"]["type"]
    obj["evidence_status"] = comp["evidence"]["status"]
    if comp.get("_mirror_of"):
        obj["mirror_of"] = comp["_mirror_of"]
    levels = comp.get("smooth", {}).get("subdivision_levels", 0)
    if levels:
        mod = obj.modifiers.new("subdivision", "SUBSURF")
        mod.levels = levels
        mod.render_levels = levels
    return obj


def setup_render(scene, canvas, shaded):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = canvas.resolution_px
    scene.render.resolution_y = canvas.resolution_px
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    sh = scene.display.shading
    if shaded:
        sh.light = "STUDIO"
        sh.color_type = "MATERIAL"
        scene.display.render_aa = "8"
    else:
        sh.light = "FLAT"
        sh.color_type = "SINGLE"
        sh.single_color = (1.0, 1.0, 1.0)
        scene.display.render_aa = "OFF"


def main():
    ws, spec_override, no_render, with_hull, no_refs, export_gltf = parse_args()
    spec, spec_file = load_spec(spec_override or ws)
    ws = workspace_of(spec_file) if spec_override else ws
    if spec.get("schema_version") != "2.0.0":
        raise ValueError("build_spec schema_version must be 2.0.0 (migrate v1 specs with migrate_v1_to_v2.py)")
    if not spec["components"]:
        raise ValueError("spec has no components")
    canvas = Canvas.from_dict(spec.get("canvas"))
    scene = reset_scene()
    col = bpy.data.collections.new(spec["character_id"])
    scene.collection.children.link(col)
    mats = {m["id"]: make_material(m) for m in spec["materials"]}
    comps = meshgen.expand_components(spec["components"])
    meshgen.world_matrices(comps)  # raises on cycles / unknown parents before touching bpy objects
    objs = {}
    for c in comps:
        o = make_object(c, col)
        o.data.materials.append(mats[c["material_id"]])
        objs[c["id"]] = o
    for c in comps:
        if c.get("parent_id"):
            o = objs[c["id"]]
            o.parent = objs[c["parent_id"]]
            o.matrix_parent_inverse = Matrix.Identity(4)   # location/rotation are LOCAL to the parent
    if with_hull:
        import numpy as np
        hp = ws / "03_geometry" / "visual_hull.npz"
        if hp.exists():
            d = np.load(hp)
            me = bpy.data.meshes.new("REF_visual_hull_mesh")
            me.from_pydata(d["verts"].tolist(), [], d["faces"].tolist())
            ho = bpy.data.objects.new("REF_visual_hull", me)
            scene.collection.objects.link(ho)
            ho.display_type = "WIRE"
            ho.hide_render = True
    bpy.context.view_layer.update()

    out_blend = ws / "04_build" / "blender" / f"{spec['character_id']}.blend"
    out_blend.parent.mkdir(parents=True, exist_ok=True)
    renders = []
    views = [v for v in spec["views"] if v["kind"] in ("front", "back", "left", "right") and v.get("role") != "rejected"]
    if not views:
        views = [{"id": k, "kind": k} for k in ("front", "right")]
    cams = {}
    for v in views:
        loc, R, ortho = blender_camera_for_view(v["kind"], canvas)
        cd = bpy.data.cameras.new(f"CAM_{v['id']}")
        cd.type = "ORTHO"
        cd.ortho_scale = ortho
        cd.clip_start, cd.clip_end = 0.01, 100.0
        co = bpy.data.objects.new(f"CAM_{v['id']}", cd)
        scene.collection.objects.link(co)
        M = Matrix([[float(R[i][j]) for j in range(3)] for i in range(3)]).to_4x4()
        M.translation = tuple(float(t) for t in loc)
        co.matrix_world = M
        cams[v["id"]] = (co, v)
        ref_png = ws / "02_views" / f"{v['id']}_ref.png"
        if not no_refs and ref_png.exists():
            img = bpy.data.images.load(str(ref_png), check_existing=True)
            try:
                img.pack()          # keep the .blend self-contained
            except RuntimeError:
                pass
            ref = bpy.data.objects.new(f"REF_{v['id']}", None)
            ref.empty_display_type = "IMAGE"
            ref.data = img
            ref.empty_display_size = canvas.world_size
            ref.empty_image_offset = (-0.5, -0.5)
            ref.empty_image_depth = "BACK"
            ref.empty_image_side = "FRONT"
            ref.show_empty_image_only_axis_aligned = True
            ref.show_empty_image_perspective = False
            ref.use_empty_image_alpha = True
            ref.color[3] = 0.6
            RM = M.copy()
            RM.translation = tuple(float(c) for c in (loc - R[:, 2] * (10.0 + canvas.world_size)))
            ref.matrix_world = RM
            ref.hide_render = True
            scene.collection.objects.link(ref)
    if not no_render:
        rdir = ws / "04_build" / "renders"
        rdir.mkdir(parents=True, exist_ok=True)
        for vid, (co, v) in cams.items():
            scene.camera = co
            for shaded, suffix in ((False, "mask"), (True, "shaded")):
                setup_render(scene, canvas, shaded)
                scene.render.filepath = str(rdir / f"{vid}_{suffix}.png")
                bpy.ops.render.render(write_still=True)
                renders.append(f"04_build/renders/{vid}_{suffix}.png")
    scene["character_id"] = spec["character_id"]
    scene["geometry_hash"] = geometry_hash(spec)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
    glb = None
    if export_gltf:
        glb = out_blend.with_suffix(".glb")
        for o in bpy.data.objects:
            o.select_set(o.name in objs)
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True)
    bboxes = {}
    for cid, o in objs.items():
        pts = [o.matrix_world @ v.co for v in o.data.vertices]
        bboxes[cid] = [[round(min(p[i] for p in pts), 5) for i in range(3)], [round(max(p[i] for p in pts), 5) for i in range(3)]]
    log = {"status": "SUCCESS", "blender_version": bpy.app.version_string, "geometry_hash": geometry_hash(spec),
           "spec_file": str(spec_file.relative_to(ws)) if spec_file.is_relative_to(ws) else str(spec_file),
           "blend_file": str(out_blend.relative_to(ws)), "objects": len(objs), "world_bboxes": bboxes, "renders": renders,
           "reference_planes": not no_refs, "gltf": str(glb.relative_to(ws)) if glb else None}
    save_json(ws / "04_build" / "blender" / "BUILD_LOG.json", log)
    print("BUILD_SUCCESS", out_blend, "objects=", len(objs), "renders=", len(renders))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        print("BUILD_ERROR", file=sys.stderr)
        sys.exit(1)
