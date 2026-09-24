"""
D4C for the Hotel: a posed, static D4C that the Hotel debuff effect floats next to the player
while someone is checked in (see particles/ in addon_files/).

Needs a D4C already fitted to Doorman's skeleton, which fv_build.py makes when pointed at D4C
instead of Valentine (use a scratch copy of the hero folder, it writes funny_valentine.dmx there):

    blender -b -P fv_build.py -- --model "<D4C blend>" --hero-dir <scratch copy of doorman_v2> \
        --pick Armature.001 --exclude icosphere --keep-mats none --save-blend d4c_fit.blend

then poses it with one frame of a Doorman animation and writes the prop into the addon:

    blender -b -P d4c_prop.py -- --fitted d4c_fit.blend \
        --anim <decompiled doorman_v2>/doorman_generic_cast_channeling_loop.dmx --addon <CSDK12 addon folder>

Output (relative to --addon): models/heroes_wip/doorman_v2/fv_d4c_hotel.dmx + .vmdl and
materials/funny_valentine/fv_d4c.vmat + fv_d4c_color.png.
"""
import argparse
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fv_build as fv  # noqa: E402  (helpers only; its main() doesn't run on import)

# the VMDL Compiler only lists models sitting in a hero folder, so it goes next to doorman.vmdl
PROP_DIR = "models/heroes_wip/doorman_v2"
PROP_NAME = "fv_d4c_hotel"

VMDL = """<!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:modeldoc28:version{fb63b6ca-f435-4aa0-a2c7-c66ddc651dca} -->
{
	rootNode =
	{
		_class = "RootNode"
		children =
		[
			{
				_class = "RenderMeshList"
				children =
				[
					{
						_class = "RenderMeshFile"
						name = "d4c"
						filename = "%s"
						import_translation = [ 0.0, 0.0, 0.0 ]
						import_rotation = [ 0.0, 0.0, 0.0 ]
						import_scale = 1.0
						align_origin_x_type = "None"
						align_origin_y_type = "None"
						align_origin_z_type = "None"
						parent_bone = ""
						import_filter =
						{
							exclude_by_default = false
							exception_list = [  ]
						}
					},
				]
			},
		]
	}
}
"""


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description="Pose the fitted D4C and write it out as a static prop")
    p.add_argument("--fitted", required=True, help="blend saved by fv_build.py --save-blend with D4C on the hero skeleton")
    p.add_argument("--anim", required=True, help="a decompiled Doorman animation .dmx to take the pose from")
    p.add_argument("--frame", type=float, default=0.5, help="where in the animation, 0..1")
    p.add_argument("--addon", required=True, help="CSDK12 content/citadel_addons/<addon> folder")
    # beside the left shoulder, a little behind and floating: the camera sits over the right shoulder,
    # so anywhere behind or to the right puts him between the camera and the crosshair
    p.add_argument("--offset", default="-18,52,22",
                   help="where D4C floats relative to the player's feet: back(-)/front, right(-)/left, up")
    p.add_argument("--scale", type=float, default=1.0)
    return p.parse_args(argv)


def main():
    a = parse_args()
    fv.ensure_bst()
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(a.fitted))
    fv.ensure_bst()
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    body = next(o for o in bpy.data.objects if o.type == "MESH" and o.find_armature() == arm)

    # one frame of the animation, without its root motion
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.import_scene.smd(filepath=os.path.abspath(a.anim), append="APPEND")
    act = arm.animation_data.action if arm.animation_data else None
    if not act:
        fv.die("no animation in " + a.anim)
    lo, hi = act.frame_range
    bpy.context.scene.frame_set(int(round(lo + (hi - lo) * a.frame)))
    pose = {pb.name: pb.matrix_basis.copy() for pb in arm.pose.bones}
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix() if pb.name == "root_motion" else pose[pb.name]
    bpy.context.view_layer.update()

    # bake the pose into a plain mesh
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(body.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    me.transform(body.matrix_world)
    mats = [m for m in body.data.materials]
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    prop = bpy.data.objects.new(PROP_NAME, me)
    col = bpy.data.collections.new(PROP_NAME)
    bpy.context.scene.collection.children.link(col)
    col.objects.link(prop)

    # place it relative to the player: feet `up` above theirs, body centre at (back, side)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * a.scale
    off = np.array([float(x) for x in a.offset.split(",")])
    shift = np.array([off[0] - co[:, 0].mean(), off[1] - co[:, 1].mean(), off[2] - co[:, 2].min()])
    me.vertices.foreach_set("co", (co + shift).ravel())
    me.update()
    co = co + shift
    fv.log("D4C prop: %.0f tall, spans %s .. %s" % (np.ptp(co[:, 2]), np.round(co.min(0)), np.round(co.max(0))))

    # material -> vmat + png
    out_mat_dir = os.path.join(a.addon, fv.MAT_DIR)
    os.makedirs(out_mat_dir, exist_ok=True)
    img, rgba = fv.base_color_source(mats[0]) if mats and mats[0] else (None, (0.8, 0.8, 0.9, 1))
    png = os.path.join(out_mat_dir, "fv_d4c_color.png")
    if not (img and fv.save_image(img, png)):
        fv.write_png(png, 4, 4, [rgba[0], rgba[1], rgba[2], 1.0] * 16)
    vmat_rel = "%s/fv_d4c.vmat" % fv.MAT_DIR
    with open(os.path.join(a.addon, vmat_rel), "w", encoding="utf-8") as f:
        f.write(fv.VMAT_TEMPLATE.format(color="%s/fv_d4c_color.png" % fv.MAT_DIR, backfaces=1))
    me.materials.clear()
    me.materials.append(bpy.data.materials.new(vmat_rel))
    for p in me.polygons:
        p.material_index = 0
    # exactly one UV map, named like the rest of the mod's meshes
    main = next((l.name for l in me.uv_layers if l.active_render), me.uv_layers.active.name)
    for name in [l.name for l in me.uv_layers if l.name != main]:
        me.uv_layers.remove(me.uv_layers[name])
    me.uv_layers[0].name = "UVMap"
    fv.check_uvs(prop)

    out_dir = os.path.join(a.addon, PROP_DIR)
    os.makedirs(out_dir, exist_ok=True)
    sc = bpy.context.scene
    sc.vs.export_path = out_dir + os.sep
    sc.vs.export_format = "DMX"
    sc.vs.dmx_encoding = "9"
    sc.vs.dmx_format = "22_modeldoc"
    sc.vs.material_path = ""
    col.vs.subdir = ""
    r = bpy.ops.export_scene.smd(collection=PROP_NAME)
    dmx = os.path.join(out_dir, PROP_NAME + ".dmx")
    if "FINISHED" not in r or not os.path.isfile(dmx):
        fv.die("DMX export failed (see Blender Source Tools output above)")
    with open(os.path.join(out_dir, PROP_NAME + ".vmdl"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(VMDL % ("%s/%s.dmx" % (PROP_DIR, PROP_NAME)))
    fv.log("wrote", dmx, "and", PROP_NAME + ".vmdl")


if __name__ == "__main__":
    main()
