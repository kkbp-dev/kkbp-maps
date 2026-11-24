"""A survey of a built Map file for placing Capture Views: each Map Variant's bounds, and a top-down
Workbench render with a 10 m grid. Game content, so it goes to an ignored folder (ADR 0007).

    blender -b <map.blend> --python tests/blender/survey.py -- <out folder>
"""

import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

out = Path(sys.argv[sys.argv.index("--") + 1])
out.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
report = {}

for coll in bpy.data.collections:
    if not coll.asset_data:
        continue
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for ob in coll.all_objects:
        if ob.type != "MESH" or "sky" in ob.name.lower():
            continue
        for c in ob.bound_box:
            p = ob.matrix_world @ Vector(c)
            if p.length > 400:   # sky domes and their clouds
                continue
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    report[coll.name] = {"min": list(lo), "max": list(hi)}

    inst = bpy.data.objects.new("survey", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = coll
    scene.collection.objects.link(inst)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    centre, size = (lo + hi) / 2, hi - lo
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(size.x, size.y) * 1.05
    cam.data.clip_end = 2000
    cam.location = (centre.x, centre.y, hi.z + 50)
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = scene.render.resolution_y = 1600
    scene.render.filepath = str(out / f"{coll.name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(inst)
    bpy.data.objects.remove(cam)

(out / f"bounds-{Path(bpy.data.filepath).stem}.json").write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
