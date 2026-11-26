"""Map Variants, their Worlds and suns, and the Prop and Structure assets, as Blender data.

- A **Map Variant** is a collection asset holding every node it shows: an object per node (an empty
  where the node has no renderer or draws nothing), named as the game names it and parented as the
  bundle does, so transforms stay exact. Its clouds or stars come with it; nodes it hides don't. Its sun
  is in the collection and its World is a World asset of the same name (ADR 0020).
- A **Prop or Structure** is a collection asset of its first Placement's nodes, its root at the origin.
- A renderer that draws a blended material draws through a child object at the centre of its bounds,
  where Unity sorts it among the transparent renderers (ADR 0027); its node's object is then an empty.
- Objects carry `kkbp_maps_*` properties: the asset a Placement root stands for, and each renderer's
  lightmap tile, scale-offset and UV set and its reflection probe, which the Variant Materials read.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from .. import look, shaders
from ..games import light_convention
from ..plan import LibraryPlan, MapPlan, VariantPlan, asset_nodes, koikano_tint, passes
from . import materials as mats
from . import sky as skystudio
from .meshes import Meshes
from .nodes import Graph

SOFT_SHADOW_ANGLE = math.radians(0.5)   # Unity's soft shadows have no angle; the look check sees no difference
PROP_ASSET, PROP_KIND = "kkbp_maps_asset", "kkbp_maps_kind"
PROP_LAYER = "kkbp_maps_layer"   # a renderer's Unity layer, which a light's culling mask names
BLENDED = ("alpha", "additive")


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
        self.centred_by_id: dict[str, tuple[bpy.types.Mesh, Vector]] = {}
        self.grades: dict[str, bpy.types.ShaderNodeTree] = {}
        self.twins: dict[str, bpy.types.Material] = {}

    def mesh(self, bundle, mesh_id):
        """A Content Hash names the same mesh in every Map, so a file builds each once."""
        if mesh_id not in self.mesh_by_id:
            self.mesh_by_id[mesh_id] = self.meshes.setdefault(bundle.key, Meshes(bundle)).get(mesh_id)
        return self.mesh_by_id[mesh_id]

    def centred(self, bundle, mesh_id) -> tuple[bpy.types.Mesh, Vector]:
        """A copy of a mesh moved so its bounds' centre is at the origin, and that centre (ADR 0027).
        The centre of a box's bounds moves with the box, so an object at the centre, under the node,
        stands where Unity's renderer bounds have theirs."""
        if mesh_id not in self.centred_by_id:
            mesh = self.mesh(bundle, mesh_id)
            centre = Vector((0.0, 0.0, 0.0))
            if len(mesh.vertices):
                import numpy as np
                co = np.empty(len(mesh.vertices) * 3, np.float32)
                mesh.vertices.foreach_get("co", co)
                co = co.reshape(-1, 3)
                centre = Vector(((co.min(0) + co.max(0)) / 2).tolist())
            copy = mesh.copy()
            copy.name = f"{mesh.name} centred"
            copy.transform(Matrix.Translation(-centre))
            self.centred_by_id[mesh_id] = (copy, centre)
        return self.centred_by_id[mesh_id]

    def grade(self, bundle, grade: dict | None):
        if not grade:
            return None
        tid = grade["lut"]
        blend = grade.get("blend")
        key = (tid, blend["lut"], blend["amount"]) if blend else tid
        if key not in self.grades:
            img = self.images.get(bundle, tid)
            img.colorspace_settings.name = "Non-Color"
            name = f".KKM Grade {bundle.textures[tid]['name']}"
            blend_img = None
            if blend:
                blend_img = self.images.get(bundle, blend["lut"])
                blend_img.colorspace_settings.name = "Non-Color"
                name += f" + {bundle.textures[blend['lut']]['name']} {blend['amount']:g}"
            self.grades[key] = mats.grade_group(name, img, blend_img, blend["amount"] if blend else 0.0)
        return self.grades[key]

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
        each further pass over a submesh. The node's object comes first. A renderer that draws a blended
        material draws through a child at the centre of its bounds instead, so EEVEE, which sorts blended
        objects by their origins, sorts it as Unity does (ADR 0027); the node's object is then an empty."""
        r = node.get("renderer")
        drawn = r is not None and any(t.level != shaders.SKIPPED for t in tiers)
        blended = drawn and any(t.level != shaders.SKIPPED and bundle.materials[d["material"]]["blend_mode"] in BLENDED
                                for d, t in zip(r["draws"], tiers))
        mesh = self.mesh(bundle, r["mesh"]) if drawn and not blended else None
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
        _keep_wind(obj, bundle, node)
        if blended:
            mesh, centre = self.centred(bundle, r["mesh"])
            first = bpy.data.objects.new(f"{node['name']} blended", mesh)
            collection.objects.link(first)
            first.parent = obj
            first.location = centre
            first["kkbp_maps_sorting"] = True
            out = [obj, first]
        elif mesh is None:
            return [obj]
        else:
            first = obj
            out = [obj]
        for k, assigned in enumerate(passes(r["draws"], tiers)):
            target = first
            if k:
                target = bpy.data.objects.new(f"{node['name']} pass {k + 1}", mesh)
                collection.objects.link(target)
                target.parent = first
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


def _keep_wind(obj, bundle, node: dict):
    """How the game moves a tree, kept on its object as data (Map Bundle 0.10); the tree is drawn at rest.
    A SpeedTree's wind: its numbers, and its switches that are on as one comma-separated string. A
    WindZone's settings likewise."""
    r = node.get("renderer")
    if r is not None and "wind" in r:
        wind = bundle.winds[r["wind"]]
        obj["kkbp_maps_wind"] = {"kind": wind["kind"], "flags": ",".join(wind["flags"]), **wind["floats"]}
    if "wind_zone" in node:
        obj["kkbp_maps_wind_zone"] = dict(node["wind_zone"])


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
        as_shown = plan.as_shown(m, v)
        sky_tree = (skystudio.group(as_shown["sky"], fb.images, b, vp.name)
                    if as_shown["sky"] and as_shown["sky"]["kind"] == "material"
                    and as_shown["sky"]["shader"] == skystudio.SHADER else None)
        light = mats.variant_light(b, as_shown, vp.name, fb.images, grade)
        variant_mats: dict[str, bpy.types.Material] = {}

        tint = koikano_tint(plan.game, v)

        def material_for(material_id, vname=vp.name, light=light, variant_mats=variant_mats, tint=tint):
            if material_id not in variant_mats:
                variant_mats[material_id] = mats.variant_material(b, material_id, vname, base_of(material_id), light,
                                                                  tint)
            return variant_mats[material_id]

        lm = {a["node"]: a for a in b.lightmap_sets[v["lightmap_set"]]["assignments"]} if v["lightmap_set"] else {}
        shown = _shown_nodes(b, v)
        objects: dict[int, bpy.types.Object] = {}
        drawers: list[bpy.types.Object] = []
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
            drawing = [o for o in made if o.type == "MESH"]
            if drawing:
                a = lm.get(i)
                probe = _probe_of(v, world[i], fb.mesh(b, n["renderer"]["mesh"])) \
                    if n["renderer"]["reflection_probes"] != "off" else 0
                for o in drawing:  # every pass is lit as the renderer is
                    o[mats.PROP_TILE] = mats.udim(a["lightmap"]) if a else 0
                    o[mats.PROP_SCALE_OFFSET] = list(a["scale_offset"]) if a else [1.0, 1.0, 0.0, 0.0]
                    o[mats.PROP_UV] = a["uv"] if a else 1
                    o[mats.PROP_PROBE] = probe
                    o[mats.PROP_REALTIME_GI] = int(n["renderer"]["realtime_gi"])
                    o[PROP_LAYER] = n["renderer"]["layer"]
                    drawers.append(o)
        _link_lights(coll, [_light_object(plan.game, light_record, f"{vp.name} {light_record['type'].title()}")
                            for light_record in v["lights"]], v["lights"], drawers)
        w = build_world(b, as_shown, vp, fb, grade, sky_tree)
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
    """The reflection probe Unity would pick for a renderer that takes probes: the first whose box holds its
    bounds' centre (1-based), or 0 for the Map's own reflection. A renderer whose reflection_probes is off
    always takes 0 (ADR 0026)."""
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


def _light_object(game: str, light: dict, name: str) -> bpy.types.Object | None:
    """A Unity light as a Blender one, or None for a light that adds nothing: a baked light, whose light
    is in a Lightmap Set or nowhere, and an area light, which Unity's built-in pipeline only bakes. Mixed
    lights light in realtime. Every light lights per pixel; Unity's pixel light count and render modes
    aren't followed (the look check measures it)."""
    convention = light_convention(game)
    if light["mode"] == "baked" or light["type"] == "area":
        return None
    if light["type"] == "directional":
        data = bpy.data.lights.new(name, "SUN")
        data.color, data.energy = mats.sun_strength(light["color"], light["intensity"],
                                                    convention.lights_use_linear_intensity)
        data.angle = SOFT_SHADOW_ANGLE if light["shadows"] == "soft" else 0.0
    else:
        data = bpy.data.lights.new(name, "POINT" if light["type"] == "point" else "SPOT")
        data.color, data.energy = mats.point_power(light["color"], light["intensity"], light["range"], convention)
        data.shadow_soft_size = 0.0
        data.use_custom_distance = True
        data.cutoff_distance = light["range"]
        if light["type"] == "spot":
            data.spot_size = math.radians(light["spot_angle"])
            data.spot_blend = look.number("spot_blend", convention.spot_blend)
    data.use_shadow = light["shadows"] != "none"
    obj = bpy.data.objects.new(name, data)
    obj.rotation_mode = "QUATERNION"
    if light["type"] != "point":
        obj.rotation_quaternion = light["rotation"]
    if light["type"] != "directional":
        obj.location = light["position"]
    return obj


def _link_lights(coll, lights, records, drawn):
    """Links the lights into the Map Variant, each lighting only the objects whose Unity layer is in its
    culling mask (Map Bundle 0.8), through Blender's light linking: a light whose mask leaves out a layer
    the Map Variant's renderers are on gets a receiver collection of the others."""
    layers = {o[PROP_LAYER] for o in drawn}
    receivers: dict[int, bpy.types.Collection] = {}
    for obj, light in zip(lights, records):
        if obj is None:
            continue
        coll.objects.link(obj)
        mask = light["culling_mask"]
        if all(mask >> layer & 1 for layer in layers):
            continue
        if mask not in receivers:
            r = receivers[mask] = bpy.data.collections.new(f"{coll.name} Layers {mask:08x}")
            for o in drawn:
                if mask >> o[PROP_LAYER] & 1:
                    r.objects.link(o)
        obj.light_linking.receiver_collection = receivers[mask]


def build_world(b, v: dict, vp: VariantPlan, fb: FileBuilder, grade, sky_tree=None) -> bpy.types.World:
    """The Map Variant's World: in EEVEE the Sky for camera rays only, with the camera's height fog over a
    Sky Dome (ADR 0028), graded; black to every other ray, since the Variant Materials hold the indirect
    light (ADR 0020). In Cycles the Sky, ungraded and unfogged, for all. Takes the Map Variant as its Camera
    Profile shows it (LibraryPlan.as_shown)."""
    w = bpy.data.worlds.new(vp.name)
    w.use_nodes = True
    w.node_tree.nodes.clear()
    g = Graph(w.node_tree)
    sky = v["sky"]
    shown = None
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
        if sky["source"] == "dome":   # a mesh, so GlobalFog fogs it; Unity's skybox is past its reach
            shown = mats.height_fog_sky(g, v, color, (coords, "Generated"))
    elif sky_tree is not None:
        coords = g.node("ShaderNodeTexCoord")
        color = (g.group(sky_tree, Vector=(coords, "Generated")), "Color")
    else:
        color = (g.rgb((0.0, 0.0, 0.0)), "Color")  # a procedural skybox isn't rebuilt yet; no Golden Map shows one
    shown = shown or color
    graded = (g.group(grade, Color=shown), "Color") if grade is not None else shown
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
