"""The Map Variants: the light of each Time of Day, with Times of Day that light the Map the same
merged into one (ADR 0009).

KK's SunLightInfo.Set changes the sun, the fog, the sun shafts, the Grade and which objects show; the
ambient light, the reflection and the lightmaps stay as the scene holds them (kk-spike, section 5).
"""

from __future__ import annotations

import json

from ..bundle.hashing import shortest32
from . import space
from .scene import Graph, Obj, Unsupported, Walk, floats, sun_infos
from .textures import Textures

LIGHT_TYPES = {0: "spot", 1: "directional", 2: "point", 3: "area"}
LIGHT_MODES = {4: "realtime", 1: "mixed", 2: "baked"}
SHADOWS = {0: "none", 1: "hard", 2: "soft"}
AMBIENT_SKYBOX, AMBIENT_TRILIGHT, AMBIENT_FLAT = 0, 1, 3
FOG_MODES = {1: "linear", 2: "exponential", 3: "exponential_squared"}
REFLECTION_SKYBOX, REFLECTION_CUSTOM = 0, 1
PROBE_BAKED, PROBE_REALTIME, PROBE_CUSTOM = 0, 1, 2
LUT_SIZE = (1024, 32)
SIX_SIDED = ("_FrontTex", "_BackTex", "_LeftTex", "_RightTex", "_UpTex", "_DownTex")


def variants(graph: Graph, walk: Walk, textures: Textures, lightmap_set: str | None) -> list[dict]:
    store = graph.store
    rs = store.tree(store.refs("RenderSettings")[0])
    rs_ref = store.refs("RenderSettings")[0]
    sun_ref, infos = sun_infos(graph)
    sun_light = store.resolve(sun_ref, store.tree(sun_ref).get("_targetLight")) if sun_ref else None
    ambient = _ambient(rs)
    by_tod = []
    for tod in graph.game.times_of_day:
        info = next((i for i in infos if graph.game.sun_types.get(i.get("type")) == tod), None)
        record = {
            "hidden": walk.hidden[tod],
            "lightmap_set": lightmap_set,
            "lights": _lights(graph, tod, sun_light, info),
            "ambient": ambient,
            "fog": _fog(rs, info),
            "reflection": _reflection(graph, rs_ref, rs, tod, textures),
            "sky": _sky(graph, walk, rs_ref, rs, tod, textures),
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

def _lights(graph: Graph, tod: str, sun_light, info) -> list[dict]:
    store = graph.store
    out = []
    for ref in store.refs("Light"):
        t = store.tree(ref)
        obj = graph.obj_of(ref)
        if obj is None or not t.get("m_Enabled", 1) or not graph.world_active(obj, tod):
            continue
        kind = LIGHT_TYPES.get(t.get("m_Type"))
        if kind is None:
            raise Unsupported(f"light {obj.name} has type {t.get('m_Type')}")
        rotation = graph.world_rotation(obj)
        c = t["m_Color"]
        color, intensity = [c["r"], c["g"], c["b"], c["a"]], t["m_Intensity"]
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
        out.append(light)
    return out


# --- ambient, fog, reflection --------------------------------------------------------------------

def _color(c) -> list[float]:
    return floats([c["r"], c["g"], c["b"], c["a"]])


def _sh(rs) -> list[float]:
    probe = rs["m_AmbientProbe"]
    values = [probe[k] for k in sorted(probe, key=lambda k: int(k.strip("sh[] ")))]
    return floats(space.sh9(values))


def _ambient(rs) -> dict:
    mode = rs.get("m_AmbientMode")
    intensity = shortest32(rs.get("m_AmbientIntensity", 1.0))
    if mode == AMBIENT_SKYBOX:
        return {"mode": "skybox_sh", "intensity": intensity, "sh": _sh(rs)}
    if mode == AMBIENT_FLAT:
        return {"mode": "flat", "intensity": intensity, "sky_color": _color(rs["m_AmbientSkyColor"]), "sh": _sh(rs)}
    if mode == AMBIENT_TRILIGHT:
        return {"mode": "trilight", "intensity": intensity, "sky_color": _color(rs["m_AmbientSkyColor"]),
                "equator_color": _color(rs["m_AmbientEquatorColor"]),
                "ground_color": _color(rs["m_AmbientGroundColor"]), "sh": _sh(rs)}
    raise Unsupported(f"ambient mode {mode}")


def _fog(rs, info) -> dict:
    density = shortest32(rs.get("m_FogDensity", 0.01))
    if info is not None:  # SunLightInfo.SetFog: always linear
        return {"enabled": bool(info["fogUse"]), "mode": "linear", "color": _color(info["fogColor"]),
                "start": shortest32(info["fogStart"]), "end": shortest32(info["fogEnd"]), "density": density}
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
    return {"color": _color(info["sunShaftsColor"])}


def _grade(store, sun_ref, info, textures: Textures) -> dict | None:
    if info is None:
        return None
    if store.resolve(sun_ref, info.get("aceLutBlendTexture")) is not None or info.get("aceBlendAmount", 0.0):
        raise Unsupported("a blended AmplifyColor LUT")
    lut = store.resolve(sun_ref, info.get("aceLutTexture"))
    if lut is None:
        return None
    t = store.texture(lut)
    if (t.width, t.height) != LUT_SIZE:
        raise Unsupported(f"LUT {t.name} is {t.width} × {t.height}")
    return {"kind": "amplify_color", "lut": textures.lut(store, lut), "layout": "amplify_32x32"}
