"""The bundle's materials: each game material by its Raw Properties, with its textures by Texture Role,
named by its Content Hash.

Only the properties the material's shader declares are kept: a Unity material keeps values left over
from shaders it used before, and those would split materials that look the same. The shader's own
property types tell colours from vectors (Unity 5.6 stores both as colours), and its first forward
pass gives the blend state and culling, resolved through the material's values where a property sets
them.
"""

from __future__ import annotations

import re

from ..bundle import hashing
from .games import Game
from .textures import Textures
from .unity import Ref, Store

# The README's Texture Role table.
ROLES = {
    "_MainTex": "main", "_BaseMap": "main", "_BumpMap": "normal", "_OcclusionMap": "occlusion",
    "_MetallicGlossMap": "metallic_gloss", "_SpecGlossMap": "specular_gloss", "_EmissionMap": "emission",
    "_ParallaxMap": "height", "_DetailMask": "detail_mask", "_DetailAlbedoMap": "detail_main",
    "_DetailTex": "detail_main", "_DetailNormalMap": "detail_normal",
}
NORMAL_ROLES = {"normal", "detail_normal"}

# ShaderLab property types.
COLOR, VECTOR, FLOAT, RANGE, TEXTURE = 0, 1, 2, 3, 4
QUEUES = {"background": 1000, "geometry": 2000, "alphatest": 2450, "transparent": 3000, "overlay": 4000}
ALPHA_TEST_QUEUE, TRANSPARENT_QUEUE = 2450, 3000
# Unity's BlendMode values.
BLEND_ONE, BLEND_SRC_ALPHA, BLEND_ONE_MINUS_SRC_ALPHA = 1, 5, 10
CULL_OFF = 0
SKIPPED_PASSES = {"SHADOWCASTER", "META", "DEFERRED", "PREPASSBASE", "PREPASSFINAL", "MOTIONVECTORS"}


class MaterialError(ValueError):
    pass


class Materials:
    def __init__(self, textures: Textures, game: Game):
        self.textures = textures
        self.game = game
        self.records: dict[str, dict] = {}
        self._ids: dict[tuple, str] = {}

    def add(self, store: Store, ref: Ref, render_queue: int | None = None) -> str:
        """The Content Hash of a material, with `render_queue` overriding its queue (SetRenderQueue)."""
        key = (ref, render_queue)
        mid = self._ids.get(key)
        if mid is None:
            record = self.record(store, ref, render_queue)
            mid = record["id"]
            self.records.setdefault(mid, record)
            self._ids[key] = mid
        return mid

    def record(self, store: Store, ref: Ref, render_queue: int | None, write_textures: bool = True) -> dict:
        """A material's record. With `write_textures` false its textures are left as references
        (`ref` in place of `texture`) and nothing is written, for a caller that may replace them."""
        m = store.tree(ref)
        shader_ref = store.resolve(ref, m.get("m_Shader"))
        if shader_ref is None or not store.is_loaded(shader_ref):
            raise MaterialError(f"material {m.get('m_Name')}'s shader isn't in the bundle")
        form = store.tree(shader_ref).get("m_ParsedForm", {})
        declared = {p["m_Name"]: p["m_Type"] for p in form.get("m_PropInfo", {}).get("m_Props", [])}
        props = m.get("m_SavedProperties", {})
        colors, vectors, floats = {}, {}, {}
        for name, c in _pairs(props.get("m_Colors", [])):
            kind = declared.get(name)
            if kind == COLOR:
                colors[name] = _f([c["r"], c["g"], c["b"], c["a"]])
            elif kind == VECTOR:
                vectors[name] = _f([c["r"], c["g"], c["b"], c["a"]])
        for name, v in _pairs(props.get("m_Floats", [])):
            if declared.get(name) in (FLOAT, RANGE):
                floats[name] = hashing.shortest32(float(v) + 0.0)
        textures = []
        for name, env in _pairs(props.get("m_TexEnvs", [])):
            if declared.get(name) != TEXTURE:
                continue
            tex = store.resolve(ref, env.get("m_Texture"))
            if tex is None or not store.is_loaded(tex):
                continue
            role = ROLES.get(name)
            kind = store.type_of(tex)
            if not write_textures and kind in ("Texture2D", "Cubemap"):
                tid = None
            elif kind == "Texture2D":
                tid = self.textures.material(store, tex, self.game, normal=role in NORMAL_ROLES)
            elif kind == "Cubemap":
                tid = self.textures.cubemap(store, tex)
            else:
                continue  # a RenderTexture is drawn at run time
            entry = {"raw": name, "texture": tid, "offset": _f([env["m_Offset"]["x"], env["m_Offset"]["y"]]),
                     "scale": _f([env["m_Scale"]["x"], env["m_Scale"]["y"]])}
            if tid is None:
                entry["ref"] = tex
            if role:
                entry = {"role": role, **entry}
            textures.append(entry)
        queue = render_queue if render_queue is not None else m.get("m_CustomRenderQueue", -1)
        if queue < 0:
            queue = shader_queue(form)
        keywords = sorted(set(m.get("m_ShaderKeywords", "").split()))
        state = forward_pass_state(form)
        record = {
            "name": m.get("m_Name", ""), "shader": form.get("m_Name") or store.tree(shader_ref).get("m_Name", ""),
            "keywords": keywords, "render_queue": int(queue),
            "blend_mode": blend_mode(state, floats, keywords, queue),
            "double_sided": _state_value(state, "culling", floats, 2) == CULL_OFF if state else False,
            "colors": colors, "floats": floats, "vectors": vectors, "textures": textures,
        }
        if not record["shader"]:
            raise MaterialError(f"material {record['name']}'s shader has no name")
        return {"id": hashing.material_hash(record), **record}


def shader_queue(form: dict) -> int:
    """The render queue a shader's first subshader asks for: 'Transparent+1' is 3001; Geometry if none."""
    for key, value in form.get("m_SubShaders", [{}])[0].get("m_Tags", {}).get("tags", []):
        if key.upper() == "QUEUE":
            m = re.fullmatch(r"\s*([A-Za-z]+)\s*([+-]\s*\d+)?\s*", value)
            if m and m.group(1).lower() in QUEUES:
                return QUEUES[m.group(1).lower()] + int((m.group(2) or "0").replace(" ", ""))
            if value.strip().lstrip("-").isdigit():
                return int(value)
    return QUEUES["geometry"]


def forward_pass_state(form: dict) -> dict | None:
    """The render state of the first subshader's first pass that draws colour."""
    subshaders = form.get("m_SubShaders", [])
    if not subshaders:
        return None
    for p in subshaders[0].get("m_Passes", []):
        state = p.get("m_State", {})
        tags = dict(state.get("m_Tags", {}).get("tags", []))
        if str(tags.get("LIGHTMODE", "")).upper() not in SKIPPED_PASSES:
            return state
    return None


def _state_value(state: dict, key: str, floats: dict, default: float) -> float:
    """A render state value: the material's float where a property sets it, else the fixed value."""
    v = state.get(key)
    if v is None:
        return default
    name = v.get("name", "<noninit>")
    if name and name != "<noninit>" and name in floats:
        return floats[name]
    return v.get("val", default)


def blend_mode(state: dict | None, floats: dict, keywords: list[str], queue: int) -> str:
    if state is not None:
        blend = state.get("rtBlend0", {})
        src = _state_value(blend, "srcBlend", floats, BLEND_ONE)
        dst = _state_value(blend, "destBlend", floats, 0)
        if dst == BLEND_ONE and src in (BLEND_ONE, BLEND_SRC_ALPHA):
            return "additive"
        if dst == BLEND_ONE_MINUS_SRC_ALPHA:
            return "alpha"
    if "_ALPHATEST_ON" in keywords or ALPHA_TEST_QUEUE <= queue < TRANSPARENT_QUEUE:
        return "cutout"
    if queue >= TRANSPARENT_QUEUE:
        return "alpha"
    return "opaque"


def _pairs(items):
    """Unity's serialized maps come as [key, value] pairs."""
    for item in items:
        if isinstance(item, (list, tuple)):
            yield item[0], item[1]
        else:
            yield item["first"], item["second"]


def _f(values) -> list[float]:
    return [hashing.shortest32(float(v) + 0.0) for v in values]
