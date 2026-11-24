"""Renders the Capture Views of one built Map file in EEVEE, for the look check (ADR 0006, D4).

    blender -b <map.blend> --python tests/blender/render_views.py -- <views.json> <look.json> <out folder>

Each Map Variant is shown alone with its own World, and each of its Capture Views is rendered with the
Standard view transform, no look, exposure 0 and gamma 1, at the capture's size, to
<out>/<map>/<variant>/<view>.png. Unity's field of view is vertical, so the camera fits its sensor
vertically. The renders are game content and go to an ignored folder (ADR 0007).
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "extension"))
from kkbp_maps import compat  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
views = json.loads(Path(args[0]).read_text())["views"]
look = json.loads(Path(args[1]).read_text())
out = Path(args[2])
scene = bpy.context.scene
map_key = scene["kkbp_maps_map"]

scene.render.engine = compat.eevee_engine()
scene.render.resolution_x = look["width"]
scene.render.resolution_y = look["height"]
scene.render.resolution_percentage = 100
scene.render.filter_size = 0.5
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.render.image_settings.color_depth = "8"
vs = scene.view_settings
vs.view_transform = "Standard"
vs.look = "None"
vs.exposure = 0.0
vs.gamma = 1.0
scene.display_settings.display_device = "sRGB"
scene.sequencer_colorspace_settings.name = "sRGB"
scene.eevee.taa_render_samples = look.get("samples", 32)

cam = bpy.data.objects.new("look camera", bpy.data.cameras.new("look camera"))
scene.collection.objects.link(cam)
cam.data.sensor_fit = "VERTICAL"
cam.data.clip_start = 0.06   # Studio camera's near and far planes
cam.data.clip_end = 1000.0
scene.camera = cam

layers = {lc.collection.name: lc for lc in bpy.context.view_layer.layer_collection.children}
done = 0
for coll in [c for c in bpy.data.collections if c.get("kkbp_maps_map") == map_key]:
    mine = [v for v in views if v["map"] == map_key and v["variant"] == coll["kkbp_maps_variant"]]
    if not mine:
        continue
    for name, lc in layers.items():
        lc.exclude = name != coll.name
    scene.world = bpy.data.worlds[coll["kkbp_maps_world"]]
    for v in mine:
        pos, target = Vector(v["position"]), Vector(v["target"])
        cam.location = pos
        cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()
        cam.data.angle = __import__("math").radians(v["fov"])
        path = out / map_key / v["variant"] / f"{v['name']}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        done += 1
print(f"render_views: {done} views of {map_key}")
