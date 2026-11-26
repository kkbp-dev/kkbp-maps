"""Base Materials, Variant Materials, the Grade and each Map Variant's light, as node graphs (D9, D13,
ADR 0002, 0008, 0020, 0021).

- A **Base Material** is a node group per game material (`.KKM <name> <hash8>`), built from its Shader
  Tier's model. Its outputs: the BSDF (the direct light and Cycles' whole surface), and the surface
  values the indirect light needs: Alpha, Albedo, Metallic, Smoothness, Occlusion, Normal (world) and
  Reflections (1 where the probe reflection applies).
- A Map Variant's **light** is a node group (`.KKM Light <Map Variant>`) that adds Unity Standard's
  indirect light to the direct light: the lightmap or the ambient, and the reflection, then the fog and
  the Grade. Per-object values (lightmap tile, scale-offset and UV set, reflection probe) are object
  properties it reads through Attribute nodes.
- A **Variant Material** wraps the two: EEVEE gets Shader to RGB of the BSDF, through the light group,
  emitted; Cycles gets the BSDF, ungraded (ADR 0008).

Colours are as the game serialized them; a linear-space Unity converts colour properties to linear
before its shaders see them, and so does `linear()` here.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy

from .. import look, shaders
from ..games import light_convention
from .nodes import Graph, io, new_group

PROP_TILE = "kkbp_maps_lightmap_tile"
PROP_SCALE_OFFSET = "kkbp_maps_lightmap_scale_offset"
PROP_UV = "kkbp_maps_lightmap_uv"
PROP_PROBE = "kkbp_maps_reflection_probe"
PROP_REALTIME_GI = "kkbp_maps_realtime_gi"   # 1 where the game adds real-time GI (ADR 0025)
PROP_HASH = "kkbp_maps_hash"

UV0, UV1 = "UVMap", "Lightmap"
COLOR_SPACE = {"srgb": "sRGB", "linear": "Non-Color"}
OPAQUE_QUEUE = 2500       # Unity's last opaque queue: [ImageEffectOpaque] effects such as GlobalFog end here
SPECCUBE_LOD_STEPS = 6   # UnityStandardConfig: the mip a fully rough surface samples
EXTENSION = {"repeat": "REPEAT", "clamp": "EXTEND", "mirror": "MIRROR", "mirror_once": "MIRROR"}
INTERPOLATION = {"point": "Closest", "bilinear": "Linear", "trilinear": "Linear"}
COLOR_SPACE_DOUBLE = 4.59479380  # unity_ColorSpaceDouble in a linear project
DIELECTRIC_SPEC = 0.04


def linear(c: float) -> float:
    """Unity's GammaToLinearSpace for one colour channel (the sRGB curve)."""
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def linear_rgb(color) -> tuple[float, float, float]:
    return tuple(linear(float(x)) for x in color[:3])


# --- images ------------------------------------------------------------------------------------

class Images:
    """The images of one file of the Map Library, loaded from the Library's textures folder. A texture
    file is copied there from its Map Bundle once. The paths are absolute while the file is built, and
    made relative when it is saved, so the Map Library can move."""

    def __init__(self, library: Path):
        self.library = library
        self.loaded: dict[str, bpy.types.Image] = {}

    def library_file(self, bundle, texture_id: str) -> Path:
        t = bundle.textures[texture_id]
        path = self.library / "textures" / f"{texture_id}.{t['format']}"
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            _copy(bundle.texture_path(texture_id), path)
        return path

    def get(self, bundle, texture_id: str) -> bpy.types.Image:
        img = self.loaded.get(texture_id)
        if img is None:
            t = bundle.textures[texture_id]
            path = self.library_file(bundle, texture_id)
            img = bpy.data.images.load(str(path), check_existing=False)
            img.name = t["name"] or texture_id
            img.colorspace_settings.name = COLOR_SPACE[t["color_space"]]
            img.alpha_mode = "CHANNEL_PACKED"
            img[PROP_HASH] = texture_id
            self.loaded[texture_id] = img
        return img

    def mips(self, bundle, texture_id: str, levels: int = SPECCUBE_LOD_STEPS) -> list[bpy.types.Image]:
        """An environment map and its mip chain, each level half the size of the one before, written once
        to textures/mips/<id>.mip<k>.exr. Level 0 is the map itself."""
        chain = [self.get(bundle, texture_id)]
        folder = self.library / "textures" / "mips"
        for k in range(1, levels + 1):
            key = f"mip:{texture_id}:{k}"
            img = self.loaded.get(key)
            if img is None:
                path = folder / f"{texture_id}.mip{k}.exr"
                if not path.is_file():
                    folder.mkdir(parents=True, exist_ok=True)
                    src = chain[0]
                    tmp = src.copy()
                    tmp.scale(max(src.size[0] >> k, 4), max(src.size[1] >> k, 2))
                    tmp.filepath_raw = str(path)
                    tmp.file_format = "OPEN_EXR"
                    tmp.save()
                    bpy.data.images.remove(tmp)
                img = bpy.data.images.load(str(path), check_existing=False)
                img.name = f"{chain[0].name} mip {k}"
                img.colorspace_settings.name = chain[0].colorspace_settings.name
                img[PROP_HASH] = f"{texture_id}.mip{k}"
                self.loaded[key] = img
            chain.append(img)
        return chain

    def udim(self, bundle, name: str, tiles: dict[int, str]) -> bpy.types.Image:
        """A UDIM image whose tiles (UDIM number -> texture id) may differ in size. Its tile files are
        copies named <name>.<UDIM>.<format> in textures/lightmaps/."""
        key = f"udim:{name}"
        if key in self.loaded:
            return self.loaded[key]
        folder = self.library / "textures" / "lightmaps"
        folder.mkdir(parents=True, exist_ok=True)
        fmt = None
        for number, tid in sorted(tiles.items()):
            fmt = bundle.textures[tid]["format"]
            target = folder / f"{name}.{number}.{fmt}"
            if not target.is_file():
                _copy(bundle.texture_path(tid), target)
        first = min(tiles)
        img = bpy.data.images.load(str(folder / f"{name}.{first}.{fmt}"), check_existing=False)
        img.source = "TILED"
        img.filepath = str(folder / f"{name}.<UDIM>.{fmt}")
        for number in sorted(tiles):
            if not any(t.number == number for t in img.tiles):
                img.tiles.new(tile_number=number)
        img.reload()
        img.name = name
        img.colorspace_settings.name = "Non-Color"
        img.alpha_mode = "CHANNEL_PACKED"
        self.loaded[key] = img
        return img


def _copy(source: Path, target: Path):
    import shutil
    tmp = target.with_name(target.name + ".partial")
    shutil.copyfile(source, tmp)
    tmp.replace(target)


def image_node(g: Graph, img, record: dict | None, uv, slot=None):
    """An Image Texture node sampling `img` at `uv`, through the material slot's offset and scale."""
    if slot is not None and (slot["scale"] != [1.0, 1.0] or slot["offset"] != [0.0, 0.0]):
        uv = g.vmath("MULTIPLY_ADD", uv, (*slot["scale"], 1.0), (*slot["offset"], 0.0))
    ext = EXTENSION[record["wrap"][0]] if record else "REPEAT"
    interp = INTERPOLATION[record["filter"]] if record else "Linear"
    return g.node("ShaderNodeTexImage", image=img, interpolation=interp, extension=ext, Vector=uv)


# --- the Grade --------------------------------------------------------------------------------

def _srgb_encode(g: Graph, color):
    """AmplifyColor's LinearToGammaSpace: max(1.055·x^(1/2.4) − 0.055, 0), per channel."""
    sep = g.node("ShaderNodeSeparateColor", Color=color)
    chans = []
    for c in ("Red", "Green", "Blue"):
        x = g.math("MAXIMUM", (sep, c), 0.0)
        p = g.math("POWER", x, 1 / 2.4)
        chans.append(g.math("MAXIMUM", g.math("MULTIPLY_ADD", p, 1.055, -0.055), 0.0))
    return g.combine(*chans)


def _srgb_decode(g: Graph, color):
    """AmplifyColor's GammaToLinearSpace: x·(x·(x·0.305306011 + 0.682171111) + 0.012522878)."""
    sep = g.node("ShaderNodeSeparateColor", Color=color)
    chans = []
    for c in ("Red", "Green", "Blue"):
        x = (sep, c)
        inner = g.math("MULTIPLY_ADD", x, 0.305306011, 0.682171111)
        inner = g.math("MULTIPLY_ADD", x, inner, 0.012522878)
        chans.append(g.math("MULTIPLY", x, inner))
    return g.combine(*chans)


def _lut_lookup(g: Graph, image, color):
    """A 32³ AmplifyColor LUT (1024 × 32, README "The AmplifyColor LUT") read in nodes: two slices around
    blue, each bilinear from four Closest reads, so EEVEE's mipmaps never blur it (KKBP's lut_nodes)."""
    sep = g.node("ShaderNodeSeparateColor", Color=color)
    r = g.math("ADD", (sep, "Red"), 0.0, clamp=True)
    gr = g.math("ADD", (sep, "Green"), 0.0, clamp=True)
    b = g.math("ADD", (sep, "Blue"), 0.0, clamp=True)
    x = g.math("MULTIPLY", r, 31.0)
    x0 = g.math("FLOOR", x)
    fx = g.math("SUBTRACT", x, x0)
    x1 = g.math("MINIMUM", g.math("ADD", x0, 1.0), 31.0)
    y = g.math("MULTIPLY", gr, 31.0)
    y0 = g.math("FLOOR", y)
    fy = g.math("SUBTRACT", y, y0)
    y1 = g.math("MINIMUM", g.math("ADD", y0, 1.0), 31.0)
    v0 = g.math("MULTIPLY_ADD", y0, 1 / 32, 0.5 / 32)
    v1 = g.math("MULTIPLY_ADD", y1, 1 / 32, 0.5 / 32)
    blue = g.math("MULTIPLY", b, 31.0)
    low = g.math("FLOOR", blue)
    high = g.math("MINIMUM", g.math("ADD", low, 1.0), 31.0)
    frac = g.math("SUBTRACT", blue, low)
    texels = []
    for s in (low, high):
        col0 = g.math("MULTIPLY_ADD", s, 32.0, x0)
        col1 = g.math("MULTIPLY_ADD", s, 32.0, x1)
        u0 = g.math("MULTIPLY_ADD", col0, 1 / 1024, 0.5 / 1024)
        u1 = g.math("MULTIPLY_ADD", col1, 1 / 1024, 0.5 / 1024)
        reads = {}
        for name, u, v in (("00", u0, v0), ("10", u1, v0), ("01", u0, v1), ("11", u1, v1)):
            uv = g.node("ShaderNodeCombineXYZ", X=u, Y=v)
            reads[name] = (g.node("ShaderNodeTexImage", image=image, interpolation="Closest", extension="EXTEND",
                                  Vector=uv), "Color")
        row0 = g.mix(fx, reads["00"], reads["10"])
        row1 = g.mix(fx, reads["01"], reads["11"])
        texels.append(g.mix(fy, row0, row1))
    return g.mix(frac, texels[0], texels[1])


def grade_group(name: str, lut_image, blend_image=None, amount: float = 0.0) -> bpy.types.ShaderNodeTree:
    """`.KKM Grade <LUT>`: AmplifyColor on a linear colour, with no tonemapper and exposure 1 (the assumed
    Camera Profile, ADR 0010): sRGB-encode, look up the LUT, decode. With a blend LUT (KKS, Map Bundle
    0.7) both are looked up and mixed by `amount`, as AmplifyColor does when its BlendAmount isn't 0."""
    tree = bpy.data.node_groups.get(name)
    if tree is not None:
        return tree
    tree = new_group(name, inputs=[("Color", "NodeSocketColor", (0.5, 0.5, 0.5, 1.0))],
                     outputs=[("Color", "NodeSocketColor")])
    g, i, o = io(tree)
    enc = _srgb_encode(g, (i, "Color"))
    graded = _lut_lookup(g, lut_image, enc)
    if blend_image is not None and amount > 0:
        graded = g.mix(amount, graded, _lut_lookup(g, blend_image, enc))
    g.link(_srgb_decode(g, graded), (o, "Color"))
    return tree


# --- Base Materials --------------------------------------------------------------------------------

BASE_OUTPUTS = [("BSDF", "NodeSocketShader"), ("Alpha", "NodeSocketFloat"), ("Albedo", "NodeSocketColor"),
                ("Metallic", "NodeSocketFloat"), ("Smoothness", "NodeSocketFloat"),
                ("Occlusion", "NodeSocketFloat"), ("Normal", "NodeSocketVector"), ("Reflections", "NodeSocketFloat")]


def base_material(bundle, material_id: str, images: Images) -> bpy.types.ShaderNodeTree:
    """The Base Material of a game material: one node group per Content Hash in each file."""
    for tree in bpy.data.node_groups:
        if tree.get(PROP_HASH) == material_id:
            return tree
    m = bundle.materials[material_id]
    tier = shaders.tier(m["shader"])
    tree = new_group(f".KKM {m['name']} {material_id[:8]}", outputs=BASE_OUTPUTS)
    tree[PROP_HASH] = material_id
    tree["kkbp_maps_shader"] = m["shader"]
    tree["kkbp_maps_tier"] = tier.level
    g, _, out = io(tree)
    if tier.model == "unlit":
        _unlit(g, out, bundle, m, tier, images)
    else:
        _standard(g, out, bundle, m, images, vertex_color=tier.vertex_color)
    return tree


def _texture(bundle, m, raw):
    return next((t for t in m["textures"] if t["raw"] == raw), None)


def _sample(g, bundle, m, raw, images, uv):
    slot = _texture(bundle, m, raw)
    if slot is None:
        return None
    img = images.get(bundle, slot["texture"])
    return image_node(g, img, bundle.textures[slot["texture"]], uv, slot)


def _uv(g, name=UV0):
    return (g.node("ShaderNodeUVMap", uv_map=name), "UV")


def _standard(g: Graph, out, bundle, m, images, vertex_color: bool = False):
    """Unity's Standard shader by its fixed rules (D13): metallic setup, albedo alpha or metallic alpha
    smoothness, normal and detail maps, occlusion, emission, cutout. Parallax is left out. With
    `vertex_color` (ProBuilder's Standard Vertex Color) the albedo is multiplied by the mesh's colour."""
    kw = set(m["keywords"])
    fl, co = m["floats"], m["colors"]
    uv = _uv(g)
    color = co.get("_Color", [1.0, 1.0, 1.0, 1.0])
    main = _sample(g, bundle, m, "_MainTex", images, uv)
    albedo = g.rgb(linear_rgb(color))
    if main is not None:
        albedo = g.mix(1.0, albedo, (main, "Color"), blend_type="MULTIPLY")
    if vertex_color:   # the colour as stored; the look check says whether ProBuilder decodes it
        vc = g.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name="color0")
        albedo = g.mix(1.0, albedo, (vc, "Color"), blend_type="MULTIPLY")
    smooth_from_albedo = fl.get("_SmoothnessTextureChannel", 0.0) >= 0.5
    if main is not None and not smooth_from_albedo:
        alpha = g.math("MULTIPLY", (main, "Alpha"), float(color[3]))
    else:
        alpha = g.value(float(color[3]))

    if "_DETAIL_MULX2" in kw:
        uv_detail = _uv(g, UV1) if fl.get("_UVSec", 0.0) >= 0.5 else uv
        detail = _sample(g, bundle, m, "_DetailAlbedoMap", images, uv_detail)
        mask_tex = _sample(g, bundle, m, "_DetailMask", images, uv)
        mask = (mask_tex, "Alpha") if mask_tex is not None else 1.0
        if detail is not None:
            doubled = g.mix(1.0, (detail, "Color"), (COLOR_SPACE_DOUBLE,) * 3 + (1.0,), blend_type="MULTIPLY")
            factor = g.mix(mask, (1.0, 1.0, 1.0, 1.0), doubled)
            albedo = g.mix(1.0, albedo, factor, blend_type="MULTIPLY")

    gloss_map = _sample(g, bundle, m, "_MetallicGlossMap", images, uv) if "_METALLICGLOSSMAP" in kw else None
    if gloss_map is not None:
        metallic = (g.node("ShaderNodeSeparateColor", Color=(gloss_map, "Color")), "Red")
        source = (main, "Alpha") if smooth_from_albedo and main is not None else (gloss_map, "Alpha")
        smoothness = g.math("MULTIPLY", source, fl.get("_GlossMapScale", 1.0))
    else:
        metallic = g.value(fl.get("_Metallic", 0.0))
        if smooth_from_albedo and main is not None:
            smoothness = g.math("MULTIPLY", (main, "Alpha"), fl.get("_GlossMapScale", 1.0))
        else:
            smoothness = g.value(fl.get("_Glossiness", 0.5))

    normal = (g.node("ShaderNodeNewGeometry"), "Normal")
    bump = _sample(g, bundle, m, "_BumpMap", images, uv) if "_NORMALMAP" in kw else None
    detail_bump = None
    if "_DETAIL_MULX2" in kw:
        uv_detail = _uv(g, UV1) if fl.get("_UVSec", 0.0) >= 0.5 else uv
        detail_bump = _sample(g, bundle, m, "_DetailNormalMap", images, uv_detail)
    if bump is not None or detail_bump is not None:
        tangent = _tangent_normal(g, bump, fl.get("_BumpScale", 1.0))
        if detail_bump is not None:
            mask_tex = _sample(g, bundle, m, "_DetailMask", images, uv)
            detail_t = _tangent_normal(g, detail_bump, fl.get("_DetailNormalMapScale", 1.0))
            if mask_tex is not None:
                detail_t = g.mix((mask_tex, "Alpha"), (0.0, 0.0, 1.0), detail_t, data_type="VECTOR")
            tangent = _blend_normals(g, tangent, detail_t)
        encoded = g.vmath("MULTIPLY_ADD", tangent, (0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
        normal = (g.node("ShaderNodeNormalMap", uv_map=UV0, Color=encoded), "Normal")

    occlusion = 1.0
    occ = _sample(g, bundle, m, "_OcclusionMap", images, uv)
    if occ is not None:
        green = (g.node("ShaderNodeSeparateColor", Color=(occ, "Color")), "Green")
        occlusion = g.math("MULTIPLY_ADD", g.math("SUBTRACT", green, 1.0), fl.get("_OcclusionStrength", 1.0), 1.0)

    emission = (0.0, 0.0, 0.0, 1.0)
    if "_EMISSION" in kw:
        e = co.get("_EmissionColor", [0.0, 0.0, 0.0, 1.0])
        emission = g.rgb(linear_rgb(e))
        etex = _sample(g, bundle, m, "_EmissionMap", images, uv)
        if etex is not None:
            emission = g.mix(1.0, emission, (etex, "Color"), blend_type="MULTIPLY")

    if m["blend_mode"] == "cutout":
        alpha = g.math("GREATER_THAN", alpha, fl.get("_Cutoff", 0.5) - 1e-6)
    elif m["blend_mode"] == "opaque":
        alpha = 1.0

    roughness = g.math("SUBTRACT", 1.0, smoothness)
    specular = 0.0 if "_SPECULARHIGHLIGHTS_OFF" in kw else 0.5
    bsdf = g.node("ShaderNodeBsdfPrincipled", **{"Base Color": albedo, "Metallic": metallic, "Roughness": roughness,
                                                  "Normal": normal, "Emission Color": emission,
                                                  "Emission Strength": 1.0, "Specular IOR Level": specular})
    g.link(bsdf, (out, "BSDF"))
    for key, value in (("Alpha", alpha), ("Albedo", albedo), ("Metallic", metallic), ("Smoothness", smoothness),
                       ("Occlusion", occlusion), ("Normal", normal),
                       ("Reflections", 0.0 if "_GLOSSYREFLECTIONS_OFF" in kw else 1.0)):
        g.set(out, key, value)


def _tangent_normal(g, tex, scale):
    """A standard tangent-space normal map's vector, its x and y scaled (UnpackScaleNormal)."""
    if tex is None:
        return (0.0, 0.0, 1.0)
    v = g.vmath("MULTIPLY_ADD", (tex, "Color"), (2.0, 2.0, 2.0), (-1.0, -1.0, -1.0))
    return g.vmath("MULTIPLY", v, (scale, scale, 1.0))


def _blend_normals(g, a, b):
    """Unity's BlendNormals: normalize(a.xy + b.xy, a.z · b.z)."""
    sa = g.node("ShaderNodeSeparateXYZ", Vector=a)
    sb = g.node("ShaderNodeSeparateXYZ", Vector=b)
    v = g.node("ShaderNodeCombineXYZ", X=g.math("ADD", (sa, "X"), (sb, "X")), Y=g.math("ADD", (sa, "Y"), (sb, "Y")),
               Z=g.math("MULTIPLY", (sa, "Z"), (sb, "Z")))
    return g.vmath("NORMALIZE", v)


def _unlit(g: Graph, out, bundle, m, tier, images):
    """An unlit shader: the main texture times its tint (Unity's particle shaders double it), alpha the
    product's. KK's meshes have no vertex colours, which Unity then takes as white."""
    uv = _uv(g)
    main = _sample(g, bundle, m, "_MainTex", images, uv)
    tint = m["colors"].get(tier.tint, [1.0, 1.0, 1.0, 1.0]) if tier.tint else [1.0, 1.0, 1.0, 1.0]
    k = tier.tint_scale
    color = g.rgb(tuple(k * c for c in linear_rgb(tint)))
    alpha = g.value(min(1.0, k * float(tint[3])) if main is None else k * float(tint[3]))
    if main is not None:
        color = g.mix(1.0, color, (main, "Color"), blend_type="MULTIPLY")
        alpha = g.math("MULTIPLY", (main, "Alpha"), k * float(tint[3]), clamp=True)
    if m["blend_mode"] == "opaque":
        alpha = 1.0
    elif m["blend_mode"] == "cutout":
        alpha = g.math("GREATER_THAN", alpha, m["floats"].get("_Cutoff", 0.5) - 1e-6)
    emit = g.node("ShaderNodeEmission", Color=color, Strength=1.0)
    g.link(emit, (out, "BSDF"))
    g.set(out, "Alpha", alpha)
    g.set(out, "Albedo", (0.0, 0.0, 0.0, 1.0))
    g.set(out, "Occlusion", 1.0)
    g.link((g.node("ShaderNodeNewGeometry"), "Normal"), (out, "Normal"))
    g.set(out, "Reflections", 0.0)


# --- a Map Variant's light ----------------------------------------------------------------------------

LIGHT_INPUTS = [("Direct", "NodeSocketColor", (0.0, 0.0, 0.0, 1.0)), ("Albedo", "NodeSocketColor", (0.0, 0.0, 0.0, 1.0)),
                ("Metallic", "NodeSocketFloat", 0.0), ("Smoothness", "NodeSocketFloat", 0.0),
                ("Occlusion", "NodeSocketFloat", 1.0), ("Normal", "NodeSocketVector", (0.0, 0.0, 1.0)),
                ("Reflections", "NodeSocketFloat", 1.0), ("Additive", "NodeSocketFloat", 0.0),
                ("Opaque", "NodeSocketFloat", 1.0)]


def variant_light(bundle, variant: dict, name: str, images: Images, grade) -> bpy.types.ShaderNodeTree:
    """`.KKM Light <Map Variant>`: Unity Standard's indirect light added to the direct light, then the
    linear fog, the camera's height fog on opaque surfaces, and the Grade (ADR 0020, 0021, 0028). Takes the
    Map Variant as its Camera Profile shows it (LibraryPlan.as_shown). Outputs the graded colour and the
    ungraded one."""
    tree = new_group(f".KKM Light {name}", inputs=LIGHT_INPUTS,
                     outputs=[("Color", "NodeSocketColor"), ("Ungraded", "NodeSocketColor")])
    g, i, o = io(tree)
    n = (i, "Normal")
    geo = g.node("ShaderNodeNewGeometry")
    view = g.vmath("NORMALIZE", (geo, "Incoming"))
    nv = g.math("MAXIMUM", g.vmath("DOT_PRODUCT", n, view), 0.0)
    metallic, smooth = (i, "Metallic"), (i, "Smoothness")
    one_minus_refl = g.math("MULTIPLY", g.math("SUBTRACT", 1.0, metallic), 1.0 - DIELECTRIC_SPEC)
    diff_color = g.mix(1.0, (i, "Albedo"), g.combine(one_minus_refl, one_minus_refl, one_minus_refl),
                       blend_type="MULTIPLY")
    spec_color = g.mix(metallic, (DIELECTRIC_SPEC,) * 3 + (1.0,), (i, "Albedo"))

    gi = _ambient(g, variant["ambient"], n)
    lm_set = bundle.lightmap_sets.get(variant["lightmap_set"]) if variant["lightmap_set"] else None
    if lm_set is not None:
        lm = _lightmap(g, bundle, lm_set, images, n)
        share = look.number("realtime_gi_ambient", light_convention(bundle.game).realtime_gi_ambient)
        if share:   # real-time GI no file holds, as a share of the ambient on top of the lightmap (ADR 0025)
            k = g.math("MULTIPLY", (_attribute(g, PROP_REALTIME_GI), "Fac"), share)
            lm = g.vmath("ADD", lm, g.vmath("SCALE", gi, scale=k))
        gi = g.mix(_lightmapped(g), gi, lm)
    diffuse = g.mix(1.0, diff_color, gi, blend_type="MULTIPLY")
    diffuse = g.vmath("SCALE", diffuse, scale=(i, "Occlusion"))

    perceptual = g.math("SUBTRACT", 1.0, smooth)
    env = _reflection(g, bundle, variant, images, n, view, geo, perceptual)
    roughness = g.math("MULTIPLY", perceptual, perceptual)
    reduction = g.math("DIVIDE", 1.0, g.math("MULTIPLY_ADD", roughness, roughness, 1.0))
    grazing = g.math("ADD", smooth, g.math("SUBTRACT", 1.0, one_minus_refl), clamp=True)
    fresnel_t = g.math("POWER", g.math("SUBTRACT", 1.0, nv), 5.0)
    fresnel = g.mix(fresnel_t, spec_color, g.combine(grazing, grazing, grazing))
    spec = g.mix(1.0, env, fresnel, blend_type="MULTIPLY")
    spec_k = g.math("MULTIPLY", g.math("MULTIPLY", reduction, (i, "Occlusion")), (i, "Reflections"))
    spec = g.vmath("SCALE", spec, scale=spec_k)

    lit = g.vmath("ADD", g.vmath("ADD", (i, "Direct"), diffuse), spec)
    lit = _fog(g, variant["fog"], lit, (i, "Additive"))
    lit = _height_fog(g, variant, lit, (i, "Opaque"))
    g.link(lit, (o, "Ungraded"))
    g.link(g.group(grade, Color=lit) if grade is not None else lit, (o, "Color"))
    return tree


def _attribute(g, name):
    return g.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name)


def _lightmapped(g):
    return g.math("GREATER_THAN", (_attribute(g, PROP_TILE), "Fac"), 0.5)


def _ambient(g, ambient: dict, n):
    """The Map's ambient light at the normal: a flat colour, or the L2 probe as UnityCG's SHEval9."""
    if ambient["mode"] == "flat":   # 1F also holds a stale probe; the look check confirms the Flat colour
        c = linear_rgb(ambient["sky_color"])
        k = ambient["intensity"]
        return g.rgb(tuple(k * x for x in c))
    sh = ambient["sh"]
    s = g.node("ShaderNodeSeparateXYZ", Vector=n)
    x, y, z = (s, "X"), (s, "Y"), (s, "Z")
    b0 = g.node("ShaderNodeCombineXYZ", X=1.0, Y=y, Z=z)
    b1 = g.node("ShaderNodeCombineXYZ", X=x, Y=g.math("MULTIPLY", x, y), Z=g.math("MULTIPLY", y, z))
    b2 = g.node("ShaderNodeCombineXYZ", X=g.math("MULTIPLY_ADD", g.math("MULTIPLY", z, z), 3.0, -1.0),
                Y=g.math("MULTIPLY", x, z),
                Z=g.math("SUBTRACT", g.math("MULTIPLY", x, x), g.math("MULTIPLY", y, y)))
    chans = []
    for c in range(3):
        k = sh[9 * c:9 * c + 9]
        d0 = g.vmath("DOT_PRODUCT", b0, tuple(k[0:3]))
        d1 = g.vmath("DOT_PRODUCT", b1, tuple(k[3:6]))
        d2 = g.vmath("DOT_PRODUCT", b2, tuple(k[6:9]))
        chans.append(g.math("MAXIMUM", g.math("ADD", g.math("ADD", d0, d1), d2), 0.0))
    return g.combine(*chans)


def _lightmap(g, bundle, lm_set: dict, images: Images, n):
    """The renderer's lightmap from the set's UDIMs: lightmap UV = uv · scale + offset + its tile's place,
    times the directional term (dot(N, d − 0.5) + 0.5) / max(d.a, 1e-4) in world axes."""
    name = lm_set_name(bundle, lm_set)
    color = images.udim(bundle, name, {udim(lm["index"]): lm["color"] for lm in lm_set["lightmaps"]})
    tile = (_attribute(g, PROP_TILE), "Fac")
    so = _attribute(g, PROP_SCALE_OFFSET)
    which = (_attribute(g, PROP_UV), "Fac")
    uv = g.mix(which, _uv(g, UV0), _uv(g, UV1), data_type="VECTOR")
    t = g.math("SUBTRACT", tile, 1001.0)
    du = g.math("FLOORED_MODULO", t, 10.0)
    dv = g.math("FLOOR", g.math("DIVIDE", t, 10.0))
    sep_so = g.node("ShaderNodeSeparateXYZ", Vector=(so, "Vector"))
    scale = g.node("ShaderNodeCombineXYZ", X=(sep_so, "X"), Y=(sep_so, "Y"), Z=0.0)
    offset = g.node("ShaderNodeCombineXYZ", X=g.math("ADD", (sep_so, "Z"), du), Y=g.math("ADD", (so, "Alpha"), dv), Z=0.0)
    lm_uv = g.vmath("MULTIPLY_ADD", uv, scale, offset)
    col = g.node("ShaderNodeTexImage", image=color, interpolation="Linear", extension="EXTEND", Vector=lm_uv)
    if lm_set["mode"] != "directional":
        return (col, "Color")
    direction = images.udim(bundle, name + "_dir", {udim(lm["index"]): lm["direction"] for lm in lm_set["lightmaps"]})
    d = g.node("ShaderNodeTexImage", image=direction, interpolation="Linear", extension="EXTEND", Vector=lm_uv)
    centred = g.vmath("SUBTRACT", (d, "Color"), (0.5, 0.5, 0.5))
    term = g.math("ADD", g.vmath("DOT_PRODUCT", n, centred), 0.5)
    term = g.math("DIVIDE", term, g.math("MAXIMUM", (d, "Alpha"), 1e-4))
    return g.vmath("SCALE", (col, "Color"), scale=term)


def udim(index: int) -> int:
    return 1001 + index % 10 + 10 * (index // 10)


def lm_set_name(bundle, lm_set: dict) -> str:
    """A Lightmap Set's file name: its colour textures' hashes decide it, so a rebuild names it the same."""
    import hashlib
    ids = ",".join(lm["color"] for lm in sorted(lm_set["lightmaps"], key=lambda lm: lm["index"]))
    return f"lightmap_{hashlib.sha256(ids.encode()).hexdigest()[:16]}"


def _env_sample(g, bundle, images, texture_id, direction, mip=None):
    """The environment map along `direction`; given `mip` (a socket, 0 to SPECCUBE_LOD_STEPS), blended
    between the two levels of its mip chain either side, as a trilinear cubemap lookup is."""
    if mip is None:
        img = images.get(bundle, texture_id)
        return (g.node("ShaderNodeTexEnvironment", image=img, interpolation="Linear", Vector=direction), "Color")
    chain = images.mips(bundle, texture_id)
    out = (g.node("ShaderNodeTexEnvironment", image=chain[0], interpolation="Linear", Vector=direction), "Color")
    for k, img in enumerate(chain[1:], start=1):
        level = (g.node("ShaderNodeTexEnvironment", image=img, interpolation="Linear", Vector=direction), "Color")
        out = g.mix(g.math("SUBTRACT", mip, float(k - 1), clamp=True), out, level)
    return out


def _reflection(g, bundle, variant, images, n, view, geo, perceptual):
    """The reflection along R = reflect(−V, N): the probe the object's property names (box-projected
    where the probe says so), else the Map's reflection cubemap, else the ambient, at Unity's mip for the
    surface's perceptual roughness, r · (1.7 − 0.7 r) · 6, from a chain of halved maps."""
    if look.get("reflection") == "off":
        return (g.rgb((0.0, 0.0, 0.0)), "Color")
    mip = g.math("MULTIPLY", g.math("MULTIPLY", perceptual, g.math("MULTIPLY_ADD", perceptual, -0.7, 1.7)),
                 float(SPECCUBE_LOD_STEPS))
    r = g.vmath("REFLECT", g.vmath("SCALE", view, scale=-1.0), n)
    refl = variant["reflection"]
    if refl["texture"] is not None:
        env = g.vmath("SCALE", _env_sample(g, bundle, images, refl["texture"], r, mip), scale=refl["intensity"])
    else:
        env = (g.rgb((0.0, 0.0, 0.0)), "Color")
    probe_index = (_attribute(g, PROP_PROBE), "Fac")
    for k, probe in enumerate(refl["probes"], start=1):
        direction = r
        if probe["box_projection"]:
            direction = _box_project(g, r, (geo, "Position"), probe)
        sample = g.vmath("SCALE", _env_sample(g, bundle, images, probe["texture"], direction, mip),
                         scale=probe["intensity"])
        chosen = g.math("COMPARE", probe_index, float(k), 0.25)
        env = g.mix(chosen, env, sample)
    return env


def _box_project(g, r, position, probe):
    """Unity's BoxProjectedCubemapDirection: the ray from the surface to the probe's box, seen from its centre."""
    c = probe["position"]
    half = [s / 2 for s in probe["box_size"]]
    box_max = tuple(c[k] + half[k] for k in range(3))
    box_min = tuple(c[k] - half[k] for k in range(3))
    rn = g.vmath("NORMALIZE", r)
    to_max = g.vmath("DIVIDE", g.vmath("SUBTRACT", box_max, position), rn)
    to_min = g.vmath("DIVIDE", g.vmath("SUBTRACT", box_min, position), rn)
    sep_r = g.node("ShaderNodeSeparateXYZ", Vector=rn)
    sep_max = g.node("ShaderNodeSeparateXYZ", Vector=to_max)
    sep_min = g.node("ShaderNodeSeparateXYZ", Vector=to_min)
    dists = []
    for axis in ("X", "Y", "Z"):
        positive = g.math("GREATER_THAN", (sep_r, axis), 0.0)
        dists.append(g.mix(positive, (sep_min, axis), (sep_max, axis), data_type="FLOAT"))
    t = g.math("MINIMUM", g.math("MINIMUM", dists[0], dists[1]), dists[2])
    hit = g.vmath("MULTIPLY_ADD", rn, g.node("ShaderNodeCombineXYZ", X=t, Y=t, Z=t), position)
    return g.vmath("SUBTRACT", hit, tuple(c))


def _fog(g, fog: dict, lit, additive):
    """Unity's linear fog by view depth, before the Grade; an additive surface fades to black (ADR 0021)."""
    if not fog["enabled"]:
        return lit
    depth = (g.node("ShaderNodeCameraData"), "View Z Depth")
    span = max(fog["end"] - fog["start"], 1e-6)
    f = g.math("DIVIDE", g.math("SUBTRACT", fog["end"], depth), span, clamp=True)
    color = g.mix(additive, g.rgb(linear_rgb(fog["color"])), (0.0, 0.0, 0.0, 1.0))
    return g.mix(f, color, lit)


def _height_fog(g, variant: dict, lit, opaque):
    """The camera's height fog (ADR 0028), as Unity's GlobalFog draws it over the opaque surfaces after
    they are drawn (ComputeHalfSpace, height only): with C the camera, P the surface, V = P − C and F the
    fog's top, k = 1 if C is at or below F, c1 = k(P·F + C·F), c2 = (1 − 2k)·P·F,
    g = −(density/2)|V|·(c1 − min(c2, 0)² / |V·F|), and that distance through the linear fog."""
    h = variant.get("height_fog")
    if not h:
        return lit
    fog = variant["fog"]
    geo = g.node("ShaderNodeNewGeometry")
    dist = (g.node("ShaderNodeCameraData"), "View Distance")
    toward = g.node("ShaderNodeSeparateXYZ", Vector=g.vmath("NORMALIZE", (geo, "Incoming")))
    p_f = g.math("SUBTRACT", (g.node("ShaderNodeSeparateXYZ", Vector=(geo, "Position")), "Z"), h["top"])
    v_f = g.math("MULTIPLY", g.math("MULTIPLY", (toward, "Z"), dist), -1.0)       # V·F, V from camera to surface
    c_f = g.math("SUBTRACT", p_f, v_f)                                             # C·F
    k = g.math("LESS_THAN", c_f, 1e-9)
    c1 = g.math("MULTIPLY", k, g.math("ADD", p_f, c_f))
    c2 = g.math("MULTIPLY", g.math("MULTIPLY_ADD", k, -2.0, 1.0), p_f)
    low = g.math("MINIMUM", c2, 0.0)
    term = g.math("DIVIDE", g.math("MULTIPLY", low, low), g.math("ABSOLUTE", g.math("ADD", v_f, 1e-5)))
    depth = g.math("MULTIPLY", g.math("MULTIPLY", dist, -0.5 * h["density"]), g.math("SUBTRACT", c1, term))
    span = max(fog["end"] - fog["start"], 1e-6)
    f = g.math("DIVIDE", g.math("SUBTRACT", fog["end"], g.math("MAXIMUM", depth, 0.0)), span, clamp=True)
    f = g.math("SUBTRACT", 1.0, g.math("MULTIPLY", opaque, g.math("SUBTRACT", 1.0, f)))  # 1 where not opaque
    return g.mix(f, g.rgb(linear_rgb(fog["color"])), lit)


def height_fog_sky(g, variant: dict, color, direction):
    """The camera's height fog over a Sky Dome at infinity (ADR 0016, 0028): every direction below the
    horizon goes the whole way through the fog, so it is the fog colour; above it, a camera above the fog's
    top sees no fog. (A camera below the top would see a little near the horizon; that isn't drawn.)"""
    if not variant.get("height_fog"):
        return color
    below = g.math("LESS_THAN", (g.node("ShaderNodeSeparateXYZ", Vector=direction), "Z"), 0.0)
    return g.mix(below, color, g.rgb(linear_rgb(variant["fog"]["color"])))


# --- materials --------------------------------------------------------------------------------------

def _finish(mat, m: dict, tier):
    mat.use_backface_culling = not (m["double_sided"] or tier.double_sided)
    # Unity's shadow pass culls as the material draws: a one-sided surface casts from its front only.
    mat.use_backface_culling_shadow = mat.use_backface_culling
    mat.surface_render_method = "BLENDED" if m["blend_mode"] in ("alpha", "additive") else "DITHERED"
    mat[PROP_HASH] = m["id"]


def variant_material(bundle, material_id: str, variant_name: str, base, light) -> bpy.types.Material:
    """The Variant Material of a Base Material in a Map Variant (ADR 0002, 0008, 0020)."""
    m = bundle.materials[material_id]
    tier = shaders.tier(m["shader"])
    mat = bpy.data.materials.new(f"{m['name']}, {variant_name}")
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    g = Graph(mat.node_tree)
    b = g.group(base)
    rgb = g.node("ShaderNodeShaderToRGB", Shader=(b, "BSDF"))
    additive = 1.0 if m["blend_mode"] == "additive" else 0.0
    lit = g.group(light, Direct=(rgb, "Color"), Albedo=(b, "Albedo"), Metallic=(b, "Metallic"),
                  Smoothness=(b, "Smoothness"), Occlusion=(b, "Occlusion"), Normal=(b, "Normal"),
                  Reflections=(b, "Reflections"), Additive=additive,
                  Opaque=1.0 if m["render_queue"] <= OPAQUE_QUEUE else 0.0)
    _outputs(g, m, (lit, "Color"), (b, "BSDF"), (b, "Alpha"))
    _finish(mat, m, tier)
    mat["kkbp_maps_variant"] = variant_name
    return mat


def asset_material(bundle, material_id: str, base, grade) -> bpy.types.Material:
    """A Prop's or Structure's own material: its Base Material lit by whatever scene it is in, graded
    by the Library's day Grade in EEVEE (ADR 0002), ungraded in Cycles."""
    m = bundle.materials[material_id]
    tier = shaders.tier(m["shader"])
    mat = bpy.data.materials.new(m["name"])
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    g = Graph(mat.node_tree)
    b = g.group(base)
    rgb = g.node("ShaderNodeShaderToRGB", Shader=(b, "BSDF"))
    color = (g.group(grade, Color=(rgb, "Color")), "Color") if grade is not None else (rgb, "Color")
    _outputs(g, m, color, (b, "BSDF"), (b, "Alpha"))
    _finish(mat, m, tier)
    return mat


def _outputs(g: Graph, m: dict, color, bsdf, alpha):
    """EEVEE: the colour emitted; Cycles: the BSDF. Both let what is behind show through by alpha."""
    emit = g.node("ShaderNodeEmission", Color=color, Strength=1.0)
    eevee = _with_alpha(g, m, emit, alpha)
    cycles = _with_alpha(g, m, bsdf, alpha)
    g.link(eevee, (g.node("ShaderNodeOutputMaterial", target="EEVEE", is_active_output=True), "Surface"))
    g.link(cycles, (g.node("ShaderNodeOutputMaterial", target="CYCLES"), "Surface"))


def _with_alpha(g, m, shader, alpha):
    if m["blend_mode"] == "opaque":
        return shader
    clear = g.node("ShaderNodeBsdfTransparent")
    if m["blend_mode"] == "additive":
        # Blend One One: the background stays whole and the surface adds alpha times its colour. Black
        # emission adds nothing and lets nothing through, so the Add keeps the background exactly once.
        nothing = g.node("ShaderNodeEmission", Color=(0.0, 0.0, 0.0, 1.0), Strength=0.0)
        scaled = g.node("ShaderNodeMixShader", Fac=alpha, Shader=nothing, Shader_001=shader)
        return g.node("ShaderNodeAddShader", Shader=clear, Shader_001=scaled)
    return g.node("ShaderNodeMixShader", Fac=alpha, Shader=clear, Shader_001=shader)


def left_out_material() -> bpy.types.Material:
    """What a skipped draw's faces get: nothing drawn, no shadow."""
    mat = bpy.data.materials.get(".KKM left out")
    if mat is None:
        mat = bpy.data.materials.new(".KKM left out")
        mat.use_nodes = True
        mat.node_tree.nodes.clear()
        g = Graph(mat.node_tree)
        g.link(g.node("ShaderNodeBsdfTransparent"), (g.node("ShaderNodeOutputMaterial"), "Surface"))
        mat.surface_render_method = "DITHERED"
        mat["kkbp_maps_left_out"] = True
    return mat


def unity_light_rgb(color, intensity: float, lights_use_linear_intensity: bool) -> list[float]:
    """A Unity light's colour as the shader receives it, linear."""
    if lights_use_linear_intensity:
        return [linear(c) * intensity for c in color[:3]]
    return [linear(c * intensity) for c in color[:3]]


def point_power(color, intensity: float, light_range: float, convention) -> tuple[tuple, float]:
    """A Unity point or spot light as a Blender light's (colour, watts). A Blender light of P watts lights
    a white diffuse surface at distance d to P / (4π² d²) (measured in both renderers); Unity's to
    colour · 1 / (1 + 25 (d/range)²). They agree at d = point_reference · range."""
    rgb = unity_light_rgb(color, intensity, convention.lights_use_linear_intensity)
    peak = max(rgb)
    if peak <= 0 or light_range <= 0:
        return (1.0, 1.0, 1.0), 0.0
    d = convention.point_reference * light_range
    falloff = 1.0 / (1.0 + 25.0 * convention.point_reference ** 2)
    return tuple(c / peak for c in rgb), 4.0 * math.pi ** 2 * d * d * falloff * peak


def sun_strength(color, intensity: float, lights_use_linear_intensity: bool):
    """A Unity directional light as a Blender sun's (colour, strength). Unity's diffuse is
    albedo · N·L · light; a Blender sun of strength 1 lights a white diffuse surface to 1/π."""
    if lights_use_linear_intensity:
        rgb = [linear(c) * intensity for c in color[:3]]
    else:
        rgb = [linear(c * intensity) for c in color[:3]]
    peak = max(rgb)
    if peak <= 0:
        return (1.0, 1.0, 1.0), 0.0
    return tuple(c / peak for c in rgb), math.pi * peak
