"""The Map Variants: the light of each Time of Day, with Times of Day that light the Map the same
merged into one (ADR 0009).

KK's SunLightInfo.Set changes the sun, the fog, the sun shafts, the Grade and which objects show; the
ambient light, the reflection and the lightmaps stay as the scene holds them (kk-spike, section 5).
"""

from __future__ import annotations

import json

from ..bundle.hashing import shortest32
from . import skystudio, space
from .scene import Graph, Obj, Unsupported, Walk, floats, sky_infos, sun_info, sun_infos, tod_type
from .textures import Textures

LIGHT_TYPES = {0: "spot", 1: "directional", 2: "point", 3: "area"}
LIGHT_MODES = {4: "realtime", 1: "mixed", 2: "baked"}
SHADOWS = {0: "none", 1: "hard", 2: "soft"}
RENDER_MODES = {0: "auto", 1: "important", 2: "not_important"}   # m_RenderMode
ALL_LAYERS = 0xFFFFFFFF
AMBIENT_SKYBOX, AMBIENT_TRILIGHT, AMBIENT_FLAT = 0, 1, 3
FOG_MODES = {1: "linear", 2: "exponential", 3: "exponential_squared"}
REFLECTION_SKYBOX, REFLECTION_CUSTOM = 0, 1
PROBE_BAKED, PROBE_REALTIME, PROBE_CUSTOM = 0, 1, 2
LUT_SIZE = (1024, 32)
SIX_SIDED = ("_FrontTex", "_BackTex", "_LeftTex", "_RightTex", "_UpTex", "_DownTex")


def variants(graph: Graph, walk: Walk, textures: Textures, lightmap_set: str | None, materials=None) -> list[dict]:
    store = graph.store
    rs = store.tree(store.refs("RenderSettings")[0])
    rs_ref = store.refs("RenderSettings")[0]
    sun_ref, infos = sun_infos(graph)
    sun_light = store.resolve(sun_ref, store.tree(sun_ref).get("_targetLight")) if sun_ref else None
    sky = _SkyStudio(graph)
    by_tod = []
    for tod in graph.game.times_of_day:
        info = sun_info(graph, infos, tod)
        profile = sky.profile(tod)
        record = {
            "hidden": walk.hidden[tod],
            "lightmap_set": lightmap_set,
            "lights": _lights(graph, tod, sun_light, info, sky, profile),
            "ambient": _ambient(rs, info),
            "fog": _fog(rs, info),
            "reflection": _reflection(graph, rs_ref, rs, tod, textures),
            "sky": (sky.record(profile, textures, materials) if profile is not None
                    else _sky(graph, walk, rs_ref, rs, tod, textures)),
            "sun_shafts": _sun_shafts(store, sun_ref, info),
            "grade": _grade(store, sun_ref, info, textures),
        }
        by_tod.append((tod, record))
    merged: list[dict] = []
    keys: list[str] = []
    for tod, record in by_tod:
        key = json.dumps(record, sort_keys=True)
        if key in keys:
            merged[keys.index(key)]["times_of_day"].append(tod)
        else:
            keys.append(key)
            merged.append({"id": tod, "times_of_day": [tod], **record})
    return merged


# --- lights ------------------------------------------------------------------------------------

def _lights(graph: Graph, tod: str, sun_light, info, sky=None, profile=None) -> list[dict]:
    store = graph.store
    out = []
    bodies = sky.body_lights(profile) if sky is not None and profile is not None else {}
    for ref in store.refs("Light"):
        t = store.tree(ref)
        obj = graph.obj_of(ref)
        body = bodies.get(ref, "absent")   # a SkyStudio sun or moon: the controller switches it
        enabled = bool(t.get("m_Enabled", 1)) if body == "absent" else body is not None
        if obj is None or not enabled or not graph.world_active(obj, tod):
            continue
        kind = LIGHT_TYPES.get(t.get("m_Type"))
        if kind is None:
            raise Unsupported(f"light {obj.name} has type {t.get('m_Type')}")
        rotation = graph.world_rotation(obj)
        c = t["m_Color"]
        color, intensity = [c["r"], c["g"], c["b"], c["a"]], t["m_Intensity"]
        if body not in ("absent", None):
            rotation, color, intensity = body["rotation"], body["color"], body["intensity"]
        if ref == sun_light and info is not None:
            rotation = space.euler_quaternion(info["angle"])
            c = info["color"]
            color, intensity = [c["r"], c["g"], c["b"], c["a"]], info["intensity"]
        light = {"type": kind}
        if kind != "directional":
            light["position"] = floats(space.vector(graph.world_matrix(obj)[:3, 3]))
        if kind != "point":
            light["rotation"] = floats(space.light_rotation(rotation))
        if kind == "area":
            a = t.get("m_AreaSize", {"x": 1.0, "y": 1.0})
            light["size"] = floats([a["x"], a["y"]])
        light["color"] = floats(color)
        light["intensity"] = shortest32(intensity)
        if kind != "directional":
            light["range"] = shortest32(t.get("m_Range", 10.0))
        if kind == "spot":
            light["spot_angle"] = shortest32(t.get("m_SpotAngle", 30.0))
        light["shadows"] = SHADOWS.get(t.get("m_Shadows", {}).get("m_Type", 0), "none")
        light["mode"] = LIGHT_MODES.get(t.get("m_Lightmapping", 4), "realtime")
        light["culling_mask"] = int(t.get("m_CullingMask", {}).get("m_Bits", ALL_LAYERS)) & ALL_LAYERS
        light["render_mode"] = RENDER_MODES.get(t.get("m_RenderMode", 0), "auto")
        out.append(light)
    return out


# --- ambient, fog, reflection --------------------------------------------------------------------

def _color(c) -> list[float]:
    return floats([c["r"], c["g"], c["b"], c["a"]])


def _sh(rs) -> list[float]:
    probe = rs["m_AmbientProbe"]
    values = [probe[k] for k in sorted(probe, key=lambda k: int(k.strip("sh[] ")))]
    return floats(space.sh9(values))


def _ambient(rs, info=None) -> dict:
    """RenderSettings' ambient light, with the colours KKS's SunLightInfo.SetAmbientColor sets."""
    mode = rs.get("m_AmbientMode")
    intensity = shortest32(rs.get("m_AmbientIntensity", 1.0))
    sky, equator, ground = rs.get("m_AmbientSkyColor"), rs.get("m_AmbientEquatorColor"), rs.get("m_AmbientGroundColor")
    if info is not None and "ambientSkyColor" in info:
        sky, equator, ground = info["ambientSkyColor"], info["ambientEquatorColor"], info["ambientGroundColor"]
    if mode == AMBIENT_SKYBOX:
        return {"mode": "skybox_sh", "intensity": intensity, "sh": _sh(rs)}
    if mode == AMBIENT_FLAT:
        return {"mode": "flat", "intensity": intensity, "sky_color": _color(sky), "sh": _sh(rs)}
    if mode == AMBIENT_TRILIGHT:
        return {"mode": "trilight", "intensity": intensity, "sky_color": _color(sky),
                "equator_color": _color(equator), "ground_color": _color(ground), "sh": _sh(rs)}
    raise Unsupported(f"ambient mode {mode}")


def _fog(rs, info) -> dict:
    density = shortest32(rs.get("m_FogDensity", 0.01))
    if info is not None:  # SunLightInfo.SetFog: always linear; KKS also sets the density and GlobalFog
        fog = {"enabled": bool(info["fogUse"]), "mode": "linear", "color": _color(info["fogColor"]),
               "start": shortest32(info["fogStart"]), "end": shortest32(info["fogEnd"]),
               "density": shortest32(info["fogDensity"]) if "fogDensity" in info else density}
        if "glFogHeightFog" in info:
            fog["camera"] = {"distance": bool(info["glFogDistanceFog"]), "height": bool(info["glFogHeightFog"]),
                             "top": shortest32(info["glFogHeight"]),
                             "start_distance": shortest32(max(0.0, info["glFogStartDistance"]))}
        return fog
    return {"enabled": bool(rs.get("m_Fog")), "mode": FOG_MODES.get(rs.get("m_FogMode"), "linear"),
            "color": _color(rs["m_FogColor"]), "start": shortest32(rs.get("m_LinearFogStart", 0.0)),
            "end": shortest32(rs.get("m_LinearFogEnd", 300.0)), "density": density}


def _reflection(graph: Graph, rs_ref, rs, tod: str, textures: Textures) -> dict:
    store = graph.store
    mode = rs.get("m_DefaultReflectionMode", REFLECTION_SKYBOX)
    if mode not in (REFLECTION_SKYBOX, REFLECTION_CUSTOM):
        raise Unsupported(f"reflection mode {mode}")
    source = store.resolve(rs_ref, rs.get("m_CustomReflection" if mode == REFLECTION_CUSTOM
                                          else "m_GeneratedSkyboxReflection"))
    texture = textures.cubemap(store, source) if source is not None and store.is_loaded(source) else None
    probes = []
    for ref in store.refs("ReflectionProbe"):
        t = store.tree(ref)
        obj = graph.obj_of(ref)
        if obj is None or not t.get("m_Enabled", 1) or not graph.world_active(obj, tod):
            continue
        baked = store.resolve(ref, t.get("m_CustomBakedTexture" if t.get("m_Mode") == PROBE_CUSTOM else "m_BakedTexture"))
        if t.get("m_Mode") == PROBE_BAKED and baked is None:
            continue  # never baked: Unity draws nothing from it, and its renderers take the Map's reflection (ADR 0023)
        if t.get("m_Mode") == PROBE_REALTIME or baked is None:
            raise Unsupported(f"reflection probe {obj.name} has no baked cubemap")
        m = graph.world_matrix(obj)
        lossy = [float((m[:3, i] ** 2).sum() ** 0.5) for i in range(3)]
        off, size = t["m_BoxOffset"], t["m_BoxSize"]
        centre = m[:3, 3] + [off["x"] * lossy[0], off["y"] * lossy[1], off["z"] * lossy[2]]
        probes.append({
            "texture": textures.cubemap(store, baked),
            "position": floats(space.vector(centre)),
            "box_size": floats(space.scale([size["x"] * lossy[0], size["y"] * lossy[1], size["z"] * lossy[2]])),
            "box_projection": bool(t.get("m_BoxProjection")),
            "intensity": shortest32(t.get("m_IntensityMultiplier", 1.0)),
        })
    return {"source": "custom" if mode == REFLECTION_CUSTOM else "skybox",
            "intensity": shortest32(rs.get("m_ReflectionIntensity", 1.0)), "texture": texture, "probes": probes}


# --- sky, sun shafts, Grade -----------------------------------------------------------------------

def _material_values(store, material):
    props = store.tree(material).get("m_SavedProperties", {})
    pairs = lambda items: ((i[0], i[1]) if isinstance(i, (list, tuple)) else (i["first"], i["second"]) for i in items)
    return dict(pairs(props.get("m_TexEnvs", []))), dict(pairs(props.get("m_Floats", []))), \
        dict(pairs(props.get("m_Colors", [])))


def _sky(graph: Graph, walk: Walk, rs_ref, rs, tod: str, textures: Textures) -> dict | None:
    store = graph.store
    shown = [i for i in walk.domes if graph.world_active(walk.nodes[i].obj, tod)]
    if len(shown) > 1:
        raise Unsupported(f"{len(shown)} Sky Domes show at {tod}")
    if shown:
        node = walk.nodes[shown[0]]
        material = next(m for m in _dome_materials(graph, node.obj) if m is not None)
        texenvs, fl, colors = _material_values(store, material)
        cube = store.resolve(material, texenvs["_Tex"]["m_Texture"])
        turn = space._qmul(graph.world_rotation(node.obj), space._quat_y(fl.get("_Rotation", 0.0)))
        rotation = space.yaw_degrees(turn)
        if rotation is None:
            raise Unsupported(f"Sky Dome {node.obj.name} is tilted")
        return {"kind": "cubemap", "source": "dome", "texture": textures.cubemap(store, cube),
                "tint": _color(colors["_Tint"]), "exposure": shortest32(fl.get("_Exposure", 1.0)),
                "rotation": shortest32(rotation), "geometry": [shown[0]]}
    material = store.resolve(rs_ref, rs.get("m_SkyboxMaterial"))
    if material is None or not store.is_loaded(material):
        return None
    from .scene import shader_name
    shader = shader_name(store, material)
    texenvs, fl, colors = _material_values(store, material)
    if shader == "Skybox/Procedural":
        from .materials import COLOR, FLOAT, RANGE
        form = store.tree(store.resolve(material, store.tree(material)["m_Shader"])).get("m_ParsedForm", {})
        declared = {p["m_Name"]: p["m_Type"] for p in form.get("m_PropInfo", {}).get("m_Props", [])}
        return {"kind": "procedural", "source": "skybox",
                "colors": {k: _color(v) for k, v in colors.items() if declared.get(k) == COLOR},
                "floats": {k: shortest32(v) for k, v in fl.items() if declared.get(k) in (FLOAT, RANGE)},
                "geometry": []}
    if shader == "Skybox/Cubemap":
        texture = textures.cubemap(store, store.resolve(material, texenvs["_Tex"]["m_Texture"]))
    elif shader == "Skybox/6 Sided":
        refs = {k: store.resolve(material, texenvs[k]["m_Texture"]) for k in SIX_SIDED}
        texture = textures.six_sided(store, refs, store.tree(material).get("m_Name", ""))
    else:
        raise Unsupported(f"skybox shader {shader}")
    return {"kind": "cubemap", "source": "skybox", "texture": texture, "tint": _color(colors["_Tint"]),
            "exposure": shortest32(fl.get("_Exposure", 1.0)),
            "rotation": shortest32(space.skybox_rotation(fl.get("_Rotation", 0.0))), "geometry": []}


def _dome_materials(graph: Graph, obj: Obj):
    store = graph.store
    r = store.tree(obj.component("MeshRenderer"))
    return [store.resolve(obj.component("MeshRenderer"), m) for m in r.get("m_Materials", [])]


def _sun_shafts(store, sun_ref, info) -> dict | None:
    if info is None or store.resolve(sun_ref, info.get("sunShaftsTransform")) is None:
        return None
    shafts = {"color": _color(info["sunShaftsColor"])}
    if "sunShaftIntensity" in info:   # KKS's SunLightInfo.SetSunShafts sets them all
        shafts.update(threshold=_color(info["sunThresholdColor"]), max_radius=shortest32(max(0.0, info["sunMaxRadius"])),
                      blur_radius=shortest32(max(0.0, info["sunShaftBlurRadius"])),
                      blur_iterations=max(0, int(info["sunRadialBlurIterations"])),
                      intensity=shortest32(max(0.0, info["sunShaftIntensity"])))
    return shafts


def _grade(store, sun_ref, info, textures: Textures) -> dict | None:
    if info is None:
        return None
    lut = store.resolve(sun_ref, info.get("aceLutTexture"))
    if lut is None:
        return None
    t = store.texture(lut)
    if (t.width, t.height) != LUT_SIZE:
        raise Unsupported(f"LUT {t.name} is {t.width} × {t.height}")
    grade = {"kind": "amplify_color", "lut": textures.lut(store, lut), "layout": "amplify_32x32"}
    amount = min(1.0, float(info.get("aceBlendAmount", 0.0)))
    if amount > 0:   # AmplifyColor mixes the blend LUT's result in by BlendAmount (Map Bundle 0.7)
        blend = store.resolve(sun_ref, info.get("aceLutBlendTexture"))
        if blend is None:
            raise Unsupported("a blended AmplifyColor LUT without its blend texture")
        b = store.texture(blend)
        if (b.width, b.height) != LUT_SIZE:
            raise Unsupported(f"LUT {b.name} is {b.width} × {b.height}")
        grade["blend"] = {"lut": textures.lut(store, blend), "amount": shortest32(amount)}
    return grade


# --- KKS's SkyStudio skies --------------------------------------------------------------------------

class _SkyStudio:
    """KKS's TimeOfDayController and MapSkyInfo (kks-spike.md, section 4): which SkyStudio profile shows
    at each Time of Day, the skybox it sets, and the sun and moon lights it drives (skystudio.py)."""

    def __init__(self, graph: Graph):
        self.graph = graph
        self.store = graph.store
        self.sky_ref, self.infos = sky_infos(graph)
        controllers = [c for c in graph.behaviours.get("TimeOfDayController", []) if self.store.tree(c).get("m_Enabled", 1)]
        if len(controllers) > 1:
            raise Unsupported(f"{len(controllers)} TimeOfDayControllers")
        self.controller = controllers[0] if controllers else None
        self._profiles: dict = {}

    def profile(self, tod: str):
        """(profile Ref, skystudio.Profile) shown at a Time of Day, or None for a Map without SkyStudio.
        MapSkyInfo.Change(type) sets its info's profile, where it names one, on the controller."""
        if self.controller is None:
            return None
        store = self.store
        ref = store.resolve(self.controller, store.tree(self.controller).get("m_SkyProfile"))
        kind = tod_type(self.graph, tod)
        if self.sky_ref is not None and 0 <= kind < len(self.infos):
            ref = store.resolve(self.sky_ref, self.infos[kind].get("_profile")) or ref
        if ref is None or not store.is_loaded(ref):
            return None
        if ref not in self._profiles:
            self._profiles[ref] = skystudio.Profile(store.tree(ref))
        return ref, self._profiles[ref]

    def body_lights(self, profile) -> dict:
        """Light Ref -> the controller's settings for it (skystudio.body_light), for the lights under the
        sun and moon orbits."""
        store, out = self.store, {}
        t = store.tree(self.controller)
        for body in ("sun", "moon"):
            orbit = store.resolve(self.controller, t.get(f"{body}Orbit"))
            obj = self.graph.obj_of(orbit) if orbit is not None and store.is_loaded(orbit) else None
            light = _first_light(obj)
            if light is not None:
                out[light] = skystudio.body_light(profile[1], body)
        return out

    def record(self, profile, textures: Textures, materials) -> dict:
        """The Map Variant's Sky: the profile's skybox material with the values the controller sets."""
        store = self.store
        ref, prof = profile
        material = store.resolve(ref, prof.tree.get("m_SkyboxMaterial"))
        if material is None or not store.is_loaded(material):
            raise Unsupported(f"SkyStudio profile {prof.name} has no skybox material")
        base = materials.record(store, material, None, write_textures=False)
        if not base["shader"].startswith(skystudio.SHADER_PREFIX):
            raise Unsupported(f"SkyStudio profile {prof.name} draws with {base['shader']}")
        values = skystudio.sky_values(prof, base, lambda pptr: self._texture(ref, pptr, textures, materials))
        for t in values["textures"]:
            if t["texture"] is None:
                t["texture"] = self._convert(t.pop("ref"), textures, materials)
            else:
                t.pop("ref", None)
        values["textures"] = [t for t in values["textures"] if t["texture"] is not None]
        feature_keywords = {kw for kw, _, _ in skystudio.FEATURES.values() if kw}
        keywords = sorted((set(base["keywords"]) - feature_keywords) | set(prof.keywords()))
        return {"kind": "material", "source": "skystudio", "shader": base["shader"], "keywords": keywords,
                **values, "geometry": []}

    def _texture(self, owner, pptr, textures: Textures, materials):
        tex = self.store.resolve(owner, pptr) if pptr else None
        return self._convert(tex, textures, materials) if tex is not None and self.store.is_loaded(tex) else None

    def _convert(self, tex, textures: Textures, materials):
        kind = self.store.type_of(tex)
        if kind == "Texture2D":
            return textures.material(self.store, tex, self.graph.game, normal=False)
        if kind == "Cubemap":
            return textures.cubemap(self.store, tex)
        return None


def _first_light(obj: Obj | None):
    """Component.GetComponentInChildren<Light>: the object's own Light, else its children's, depth first."""
    if obj is None:
        return None
    if "Light" in obj.components:
        return obj.components["Light"][0]
    for child in obj.children:
        found = _first_light(child)
        if found is not None:
            return found
    return None
