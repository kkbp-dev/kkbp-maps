"""Asset previews (D18): Map Variants show the game's own thumbnail; Props and Structures get an EEVEE
render from a fixed three-quarter camera, in a grey world with one sun."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

from ... import compat

PREVIEW_SIZE = 256
VIEW = Vector((1.0, -1.2, 0.8)).normalized()   # from the front right, above
LENS_FOV = math.radians(39.6)                  # a 50 mm lens on a 36 mm sensor


def set_pixels(idblock, width: int, height: int, pixels):
    p = idblock.preview_ensure()
    p.image_size = (width, height)
    p.image_pixels_float = pixels


def from_image_file(idblock, path: Path) -> bool:
    img = bpy.data.images.load(str(path), check_existing=False)
    try:
        w, h = img.size
        if not w or not h:
            return False
        set_pixels(idblock, w, h, img.pixels[:])
        return True
    finally:
        bpy.data.images.remove(img)


def _world_matrix(obj) -> Matrix:
    m = obj.matrix_basis
    while obj.parent is not None:
        m = obj.parent.matrix_basis @ obj.matrix_parent_inverse @ m
        obj = obj.parent
    return m


def _bounds(coll):
    lo, hi = Vector((math.inf,) * 3), Vector((-math.inf,) * 3)
    for obj in coll.all_objects:
        if obj.type != "MESH" or not len(obj.data.vertices):
            continue
        m = _world_matrix(obj)
        for corner in _mesh_box(obj.data):
            p = m @ corner
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
    return (lo, hi) if lo.x <= hi.x else None


def _mesh_box(mesh):
    import numpy as np
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    a, b = co.min(0), co.max(0)
    return [Vector((x, y, z)) for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])]


def render(collections: list) -> int:
    """Renders a preview for each collection. Returns how many got one."""
    scene = bpy.data.scenes.new(".KKM preview")
    scene.render.engine = compat.eevee_engine()
    scene.render.resolution_x = scene.render.resolution_y = PREVIEW_SIZE
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.eevee.taa_render_samples = 16
    world = bpy.data.worlds.new(".KKM preview")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.3, 0.3, 0.3, 1.0)
    scene.world = world
    sun = bpy.data.objects.new(".KKM preview sun", bpy.data.lights.new(".KKM preview sun", "SUN"))
    sun.data.energy = math.pi
    sun.rotation_euler = (math.radians(50), 0.0, math.radians(30))
    cam = bpy.data.objects.new(".KKM preview camera", bpy.data.cameras.new(".KKM preview camera"))
    cam.data.lens_unit = "FOV"
    cam.data.angle = LENS_FOV
    scene.collection.objects.link(sun)
    scene.collection.objects.link(cam)
    scene.camera = cam
    done = 0
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "preview.png"
        for coll in collections:
            box = _bounds(coll)
            if box is None:
                continue
            centre = (box[0] + box[1]) / 2
            radius = max((box[1] - box[0]).length / 2, 0.01)
            distance = radius / math.sin(LENS_FOV / 2) * 1.05
            cam.location = centre + VIEW * distance
            cam.rotation_euler = (-VIEW).to_track_quat("-Z", "Y").to_euler()
            cam.data.clip_start = max(distance - radius * 2, 0.001)
            cam.data.clip_end = distance + radius * 2
            scene.collection.children.link(coll)
            try:
                scene.render.filepath = str(out)
                with bpy.context.temp_override(scene=scene):
                    bpy.ops.render.render(write_still=True, scene=scene.name)
            finally:
                scene.collection.children.unlink(coll)
            if from_image_file(coll, out):
                done += 1
    for obj in (sun, cam):
        data = obj.data
        bpy.data.objects.remove(obj)
        (bpy.data.lights if isinstance(data, bpy.types.Light) else bpy.data.cameras).remove(data)
    bpy.data.scenes.remove(scene)
    bpy.data.worlds.remove(world)
    return done
