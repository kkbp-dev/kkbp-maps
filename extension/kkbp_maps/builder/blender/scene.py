"""Map Variants, their Worlds and suns, and the Prop and Structure assets, as Blender data.

- A **Map Variant** is a collection asset holding every node it shows: an object per node (an empty
  where the node has no renderer or draws nothing), named as the game names it and parented as the
  bundle does, so transforms stay exact. Its clouds or stars come with it; nodes it hides don't. Its sun
  is in the collection and its World is a World asset of the same name (ADR 0020).
- A **Prop or Structure** is a collection asset of its first Placement's nodes, its root at the origin.
- Objects carry `kkbp_maps_*` properties: the asset a Placement root stands for, and each renderer's
  lightmap tile, scale-offset and UV set and its reflection probe, which the Variant Materials read.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from .. import shaders
from ..games import light_convention
from ..plan import LibraryPlan, MapPlan, VariantPlan, asset_nodes
from . import materials as mats
from .meshes import Meshes
from .nodes import Graph

SOFT_SHADOW_ANGLE = math.radians(0.5)
PROP_ASSET, PROP_KIND = "kkbp_maps_asset", "kkbp_maps_kind"


def local_matrix(node: dict) -> Matrix:
    return Matrix.LocRotScale(Vector(node["translation"]), Quaternion(node["rotation"]), Vector(node["scale"]))


def world_matrices(bundle) -> list[Matrix]:
    out: list[Matrix] = []
    for n in bundle.nodes:
        m = local_matrix(n)
        out.append(out[n["parent"]] @ m if n["parent"] is not None else m)
    return out


class FileBuilder:
    """Everything one .blend file of the Map Library is built from: its images, meshes, Base Materials."""

    def __init__(self, images: mats.Images):
        self.images = images
        self.meshes: dict[str, Meshes] = {}
        self.mesh_by_id: dict[str, bpy.types.Mesh] = {}
        self.grades: dict[str, bpy.types.ShaderNodeTree] = {}

    def mesh(self, bundle, mesh_id):
        """A Content Hash names the same mesh in every Map, so a file builds each once."""
        if mesh_id not in self.mesh_by_id:
            self.mesh_by_id[mesh_id] = self.meshes.setdefault(bundle.key, Meshes(bundle)).get(mesh_id)
        return self.mesh_by_id[mesh_id]

    def grade(self, bundle, grade: dict | None):
        if not grade:
            return None
        tid = grade["lut"]
        if tid not in self.grades:
            img = self.images.get(bundle, tid)
            img.colorspace_settings.name = "Non-Color"
            self.grades[tid] = mats.grade_group(f".KKM Grade {bundle.textures[tid]['name']}", img)
        return self.grades[tid]

    def make_object(self, bundle, node: dict, tiers, collection, parent, material_for) -> bpy.types.Object:
        """An object for a node: a mesh object if it draws something, else an empty."""
        r = node.get("renderer")
        drawn = r is not None and any(t.level != shaders.SKIPPED for t in tiers)
        mesh = self.mesh(bundle, r["mesh"]) if drawn else None
        obj = bpy.data.objects.new(node["name"], mesh)
        if mesh is None:
            obj.empty_display_type = "PLAIN_AXES"
            obj.empty_display_size = 0.25
        obj.rotation_mode = "QUATERNION"
        obj.location = node["translation"]
        obj.rotation_quaternion = node["rotation"]
        obj.scale = node["scale"]
        collection.objects.link(obj)
        if parent is not None:
            obj.parent = parent
        if mesh is not None:
            _check_draws(bundle, node)
            for slot, (draw, tier) in zip(obj.material_slots, zip(r["draws"], tiers)):
                slot.link = "OBJECT"
                slot.material = mats.left_out_material() if tier.level == shaders.SKIPPED else material_for(draw["material"])
            obj.visible_shadow = r["cast_shadows"]
        return obj


def _check_draws(bundle, node):
    """Each submesh drawn once, in order: what a Blender mesh's material slots can hold. KK's Golden Maps
    are all like this; a Map that isn't stops the build rather than drawing wrongly."""
    r = node["renderer"]
    subs = [d["submesh"] for d in r["draws"]]
    if subs != list(range(len(bundle.meshes[r["mesh"]]["index_counts"]))):
        raise NotImplementedError(f"{bundle.key}: node {node['id']} ({node['name']}) draws submeshes {subs}; "
                                  "the Builder needs each submesh drawn once, in order")


# --- Map Variants ------------------------------------------------------------------------------------

def build_map(plan: LibraryPlan, m: MapPlan, fb: FileBuilder) -> list[bpy.types.Collection]:
    b = m.bundle
    world = world_matrices(b)
    lm = {}
    out = []
    base: dict[str, bpy.types.ShaderNodeTree] = {}

    def base_of(material_id):
        if material_id not in base:
            base[material_id] = mats.base_material(b, material_id, fb.images)
        return base[material_id]

    for v, vp in zip(b.variants, m.variants):
        coll = bpy.data.collections.new(vp.name)
        grade = fb.grade(b, v["grade"])
        light = mats.variant_light(b, v, vp.name, fb.images, grade)
        variant_mats: dict[str, bpy.types.Material] = {}

        def material_for(material_id, vname=vp.name, light=light, variant_mats=variant_mats):
            if material_id not in variant_mats:
                variant_mats[material_id] = mats.variant_material(b, material_id, vname, base_of(material_id), light)
            return variant_mats[material_id]

        lm = {a["node"]: a for a in b.lightmap_sets[v["lightmap_set"]]["assignments"]} if v["lightmap_set"] else {}
        shown = _shown_nodes(b, v)
        objects: dict[int, bpy.types.Object] = {}
        for n in b.nodes:
            i = n["id"]
            if i not in shown:
                continue
            parent = objects.get(n["parent"]) if n["parent"] is not None else None
            obj = fb.make_object(b, n, m.draws.get(i, ()), coll, parent, material_for)
            objects[i] = obj
            if i in m.roots:
                asset = plan.assets.get(m.roots[i]) or plan.left_out_assets.get(m.roots[i])
                obj[PROP_ASSET] = m.roots[i]
                obj[PROP_KIND] = asset.kind
                obj["kkbp_maps_asset_name"] = asset.name
            if obj.type == "MESH":
                a = lm.get(i)
                obj[mats.PROP_TILE] = mats.udim(a["lightmap"]) if a else 0
                obj[mats.PROP_SCALE_OFFSET] = list(a["scale_offset"]) if a else [1.0, 1.0, 0.0, 0.0]
                obj[mats.PROP_UV] = a["uv"] if a else 1
                obj[mats.PROP_PROBE] = _probe_of(v, world[i], obj.data)
        for k, light_record in enumerate(v["lights"]):
            coll.objects.link(_light_object(plan.game, light_record, f"{vp.name} {light_record['type'].title()}"))
        w = build_world(b, v, vp, fb, grade)
        coll["kkbp_maps_world"] = w.name
        coll["kkbp_maps_map"] = m.key
        coll["kkbp_maps_variant"] = v["id"]
        coll["kkbp_maps_times_of_day"] = list(v["times_of_day"])
        out.append(coll)
    return out


def _shown_nodes(b, v) -> set[int]:
    """The nodes a Map Variant shows: all but its hidden ones, and of the sky nodes only its own Sky's."""
    hidden = b.hidden_in(v)
    sky = set()
    if v["sky"]:
        for g in v["sky"]["geometry"]:
            sky.update(b.subtree(g))
    return {n["id"] for n in b.nodes if n["id"] not in hidden and (not n.get("sky") or n["id"] in sky)}


def _probe_of(v, world: Matrix, mesh) -> int:
    """The reflection probe Unity would pick for a renderer: the first whose box holds its bounds' centre
    (1-based), or 0 for the Map's own reflection."""
    if not v["reflection"]["probes"] or not len(mesh.vertices):
        return 0
    import numpy as np
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    centre = world @ Vector(((co.min(0) + co.max(0)) / 2).tolist())
    for k, p in enumerate(v["reflection"]["probes"], start=1):
        if all(abs(centre[a] - p["position"][a]) <= p["box_size"][a] / 2 for a in range(3)):
            return k
    return 0


def _light_object(game: str, light: dict, name: str) -> bpy.types.Object:
    if light["type"] != "directional":
        raise NotImplementedError(f"{light['type']} lights come with KKS and SVS")
    data = bpy.data.lights.new(name, "SUN")
    color, strength = mats.sun_strength(light["color"], light["intensity"],
                                        light_convention(game).lights_use_linear_intensity)
    data.color = color
    data.energy = strength
    data.use_shadow = light["shadows"] != "none"
    data.angle = SOFT_SHADOW_ANGLE if light["shadows"] == "soft" else 0.0
    obj = bpy.data.objects.new(name, data)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = light["rotation"]
    return obj


def build_world(b, v: dict, vp: VariantPlan, fb: FileBuilder, grade) -> bpy.types.World:
    """The Map Variant's World: in EEVEE the Sky for camera rays only, graded; black to every other ray,
    since the Variant Materials hold the indirect light (ADR 0020). In Cycles the Sky, ungraded, for all."""
    w = bpy.data.worlds.new(vp.name)
    w.use_nodes = True
    w.node_tree.nodes.clear()
    g = Graph(w.node_tree)
    sky = v["sky"]
    if sky and sky["kind"] == "cubemap":
        img = fb.images.get(b, sky["texture"])
        coords = g.node("ShaderNodeTexCoord")
        rotate = g.node("ShaderNodeMapping", vector_type="POINT", Vector=(coords, "Generated"),
                        Rotation=(0.0, 0.0, math.radians(sky["rotation"])))
        env = g.node("ShaderNodeTexEnvironment", image=img, interpolation="Linear", Vector=rotate)
        # Skybox/Cubemap: texture · _Tint · unity_ColorSpaceDouble · _Exposure
        k = mats.COLOR_SPACE_DOUBLE * sky["exposure"]
        tint = tuple(k * c for c in mats.linear_rgb(sky["tint"]))
        color = g.mix(1.0, (env, "Color"), (*tint, 1.0), blend_type="MULTIPLY")
    else:
        color = (g.rgb((0.0, 0.0, 0.0)), "Color")  # a procedural skybox isn't rebuilt yet; no KK Golden Map shows one
    graded = (g.group(grade, Color=color), "Color") if grade is not None else color
    camera = (g.node("ShaderNodeLightPath"), "Is Camera Ray")
    eevee = g.node("ShaderNodeBackground", Color=g.mix(camera, (0.0, 0.0, 0.0, 1.0), graded), Strength=1.0)
    g.link(eevee, (g.node("ShaderNodeOutputWorld", target="EEVEE", is_active_output=True), "Surface"))
    cycles = g.node("ShaderNodeBackground", Color=color, Strength=1.0)
    g.link(cycles, (g.node("ShaderNodeOutputWorld", target="CYCLES"), "Surface"))
    w["kkbp_maps_sky"] = sky["kind"] if sky else "none"
    return w


# --- Props and Structures --------------------------------------------------------------------------

def build_asset(plan: LibraryPlan, asset, fb: FileBuilder, base_cache: dict, grade) -> bpy.types.Collection:
    key, root = asset.source
    m = plan.map_of(key)
    b = m.bundle
    coll = bpy.data.collections.new(asset.name)

    def material_for(material_id):  # a Content Hash: the same material in every Map
        if material_id not in base_cache:
            base = mats.base_material(b, material_id, fb.images)
            base_cache[material_id] = mats.asset_material(b, material_id, base, grade)
        return base_cache[material_id]

    objects: dict[int, bpy.types.Object] = {}
    for i in asset_nodes(b, root):
        n = b.nodes[i]
        parent = objects.get(n["parent"]) if i != root else None
        obj = fb.make_object(b, n, m.draws.get(i, ()), coll, parent, material_for)
        if i == root:
            obj.location = (0.0, 0.0, 0.0)
            obj.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
            obj.scale = (1.0, 1.0, 1.0)
            obj[PROP_ASSET] = asset.hash
            obj[PROP_KIND] = asset.kind
        objects[i] = obj
    coll[PROP_ASSET] = asset.hash
    coll[PROP_KIND] = asset.kind
    return coll


def mark_asset(idblock, catalog_id: str, tags: list[str], description: str):
    idblock.asset_mark()
    idblock.asset_data.catalog_id = catalog_id
    idblock.asset_data.description = description
    for t in tags:
        idblock.asset_data.tags.new(t, skip_if_exists=True)
