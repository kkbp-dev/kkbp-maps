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
from ..games import camera_profile, light_convention
from ..plan import LibraryPlan, MapPlan, VariantPlan, asset_nodes, passes
from . import materials as mats
from .meshes import Meshes
from .nodes import Graph

SOFT_SHADOW_ANGLE = math.radians(0.5)   # Unity's soft shadows have no angle; the look check sees no difference
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
        self.twins: dict[str, bpy.types.Material] = {}

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

    def two_sided(self, mat: bpy.types.Material) -> bpy.types.Material:
        """The material for a `two_sided` renderer: one that casts shadows from both faces, a twin of
        `mat` where `mat` casts from its front only (Blender culls shadows per material, ADR 0024)."""
        if not mat.use_backface_culling_shadow:
            return mat
        twin = self.twins.get(mat.name)
        if twin is None:
            twin = self.twins[mat.name] = mat.copy()
            twin.name = f"{mat.name}, two-sided shadow"
            twin.use_backface_culling_shadow = False
        return twin

    def make_object(self, bundle, node: dict, tiers, collection, parent, material_for) -> list[bpy.types.Object]:
        """The objects for a node: a mesh object if it draws something, else an empty; and one more for
        each further pass over a submesh. The first object comes first."""
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
        if mesh is None:
            return [obj]
        out = [obj]
        for k, assigned in enumerate(passes(r["draws"], tiers)):
            target = obj
            if k:
                target = bpy.data.objects.new(f"{node['name']} pass {k + 1}", mesh)
                collection.objects.link(target)
                target.parent = obj
                target["kkbp_maps_pass"] = k + 1
                out.append(target)
            for i, slot in enumerate(target.material_slots):
                slot.link = "OBJECT"
                draw, tier = assigned.get(i, (None, None))
                slot.material = material_for(draw["material"]) if draw and tier.level != shaders.SKIPPED \
                    else mats.left_out_material()
                if r["shadows"] == "two_sided":
                    slot.material = self.two_sided(slot.material)
            target.visible_shadow = r["shadows"] != "off" and k == 0
            if r["shadows"] == "shadows_only":   # a hidden caster (ADR 0024)
                target.visible_camera = target.visible_diffuse = target.visible_glossy = False
                target.visible_transmission = target.visible_volume_scatter = False
                target.hide_select = True
        return out


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
        grade = fb.grade(*plan.grade_of(m, v))
        light = mats.variant_light(b, _as_shown(plan, m, v), vp.name, fb.images, grade)
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
            made = fb.make_object(b, n, m.draws.get(i, ()), coll, parent, material_for)
            obj = objects[i] = made[0]
            if i in m.roots:
                asset = plan.assets.get(m.roots[i]) or plan.left_out_assets.get(m.roots[i])
                obj[PROP_ASSET] = m.roots[i]
                obj[PROP_KIND] = asset.kind
                obj["kkbp_maps_asset_name"] = asset.name
            if obj.type == "MESH":
                a = lm.get(i)
                probe = _probe_of(v, world[i], obj.data)
                for o in made:  # every pass is lit as the renderer is
                    o[mats.PROP_TILE] = mats.udim(a["lightmap"]) if a else 0
                    o[mats.PROP_SCALE_OFFSET] = list(a["scale_offset"]) if a else [1.0, 1.0, 0.0, 0.0]
                    o[mats.PROP_UV] = a["uv"] if a else 1
                    o[mats.PROP_PROBE] = probe
                    o[mats.PROP_REALTIME_GI] = int(n["renderer"]["realtime_gi"])
        for k, light_record in enumerate(v["lights"]):
            coll.objects.link(_light_object(plan.game, light_record, f"{vp.name} {light_record['type'].title()}"))
        w = build_world(b, v, vp, fb, grade)
        coll["kkbp_maps_world"] = w.name
        coll["kkbp_maps_map"] = m.key
        coll["kkbp_maps_variant"] = v["id"]
        coll["kkbp_maps_times_of_day"] = list(v["times_of_day"])
        out.append(coll)
    return out


def _as_shown(plan: LibraryPlan, m: MapPlan, v: dict) -> dict:
    """The Map Variant as its Camera Profile shows it: without the Map's fog where the camera replaces it."""
    if camera_profile(plan.game, plan.camera_of(m)).map_fog:
        return v
    return {**v, "fog": {**v["fog"], "enabled": False}}


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
        obj = fb.make_object(b, n, m.draws.get(i, ()), coll, parent, material_for)[0]
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
