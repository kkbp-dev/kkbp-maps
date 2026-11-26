"""The Shader Tiers (D13): how the Builder rebuilds each game shader, by the shader's name.

A tier says which rebuild a material gets (`model`) and how close it is (`level`): `rebuilt` by fixed
rules, `approximated`, or `skipped`, in which case what it draws is left out. The Build Report lists the
approximated and skipped ones. Never imports bpy.

The names are Unity's and the game's own shader names, the only marker a material gives of what it is.
"""

from __future__ import annotations

from dataclasses import dataclass

REBUILT, APPROXIMATED, SKIPPED = "rebuilt", "approximated", "skipped"


@dataclass(frozen=True)
class Tier:
    model: str | None     # "standard" or "unlit"; None when skipped
    level: str
    reason: str = ""      # why it is approximated or skipped, for the Build Report
    double_sided: bool = False
    tint: str | None = None   # an unlit model's colour property
    tint_scale: float = 1.0   # Unity's particle shaders double their tint
    vertex_color: bool = False   # the albedo is multiplied by the mesh's color0
    blend: str | None = None     # a Blend Mode the Builder draws the material with, whatever the bundle says
    cutout_keywords: tuple[str, ...] = ()   # keywords that make the material cutout at its _Cutoff
    color: str | None = None     # the water model's colour property
    alpha: float = 1.0           # the water model's opacity
    density: str | None = None   # the water model's density property, which sets its opacity instead


def _standard(level=REBUILT, reason="", double_sided=False, vertex_color=False):
    return Tier("standard", level, reason, double_sided, vertex_color=vertex_color)


def _water(color, alpha=0.6, density=None, reason="water drawn as a smooth tinted surface"):
    """Water (Lux Water, NatureManufacture's rivers): its textures are foam, caustics and flow, not its
    colour; drawn as a smooth, partly see-through surface of one colour property (a first guess)."""
    return Tier("water", APPROXIMATED, reason, double_sided=True, blend="alpha", color=color, alpha=alpha,
                density=density)


def blend_mode(material: dict) -> str:
    """The Blend Mode the Builder draws a material with: the bundle's, unless its Shader Tier sets one or
    one of its keywords makes it cutout (SpeedTree clips its leaves and fronds at _Cutoff)."""
    t = tier(material["shader"])
    if t.blend:
        return t.blend
    if any(k in material["keywords"] for k in t.cutout_keywords):
        return "cutout"
    return material["blend_mode"]


def _unlit(level=REBUILT, reason="", tint=None, tint_scale=1.0):
    return Tier("unlit", level, reason, tint=tint, tint_scale=tint_scale)


def _skip(reason):
    return Tier(None, SKIPPED, reason)


TIERS: dict[str, Tier] = {
    "Standard": _standard(),
    "Standard (Specular setup)": _standard(APPROXIMATED, "specular setup taken as metallic"),
    "Custom/StandardDouble": _standard(double_sided=True),
    # Unity's built-in Lambert, read from the player's resources (ADR 0031): warehouse's Shadow Caster.
    "Legacy Shaders/Diffuse": _standard(APPROXIMATED, "Lambert drawn as Standard"),
    # KK's only Game Shader Model candidate; its model waits for a Golden Map that uses it (D13).
    "Shader Forge/main_item": _standard(APPROXIMATED, "no Game Shader Model yet"),
    # KK draws its foliage with particle shaders on plain meshes: unlit, tinted, alpha blended.
    "Particles/Alpha Blended": _unlit(tint="_TintColor", tint_scale=2.0),
    "Particles/Anim Alpha Blended": _unlit(APPROXIMATED, "its texture sheet animation isn't played",
                                           tint="_TintColor", tint_scale=2.0),
    "Particles/VertexLit Blended": _unlit(APPROXIMATED, "drawn unlit", tint="_EmisColor"),
    "Particles/Additive": _unlit(tint="_TintColor", tint_scale=2.0),
    "Unlit/Transparent": _unlit(),
    "Unlit/Transparent Cutout": _unlit(),
    "Unlit/Texture": _unlit(),
    "Unlit/Color": _unlit(tint="_Color"),
    "Xffect/heat_distortion": _skip("heat haze"),
    "FX/MirrorReflection_Transparent": _skip("mirror"),
    "Shader Forge/spotLight_beam": _skip("volumetric light"),
    "Shader Forge/spotLight_glow": _skip("volumetric light"),
    "Shader Forge/spotLaser": _skip("volumetric light"),
    "Shader Forge/volumeLight": _skip("volumetric light"),
    "Shader Forge/electricLight": _skip("volumetric light"),
    "Unlit/MosaicTexture": _skip("mosaic"),
    "Custom/Silhouette": _skip("silhouette"),
    # KKS (kks-spike.md, section 9).
    "Nature/SpeedTree": Tier("standard", APPROXIMATED, "hue variation and wind aren't drawn",
                             cutout_keywords=("GEOM_TYPE_LEAF", "GEOM_TYPE_FROND")),
    # Koikano's map shader as the game's globals leave it (games.KOIKANO); always alpha-tested at _Cutoff.
    "Koikano/main_item_map": Tier("koikano", REBUILT, blend="cutout"),
    "Koikano/sub_texture_cutout": _standard(APPROXIMATED, "Koikano drawn as Standard"),
    "Koikano/sub_texture_subblendcutout": _standard(APPROXIMATED, "Koikano drawn as Standard"),
    "Koikano/sub_add_cullfront": _standard(APPROXIMATED, "Koikano drawn as Standard"),
    "Koikano/main_clothes_item": _standard(APPROXIMATED, "Koikano drawn as Standard"),
    "Koikano/main_clothes_item_glasses": _standard(APPROXIMATED, "Koikano drawn as Standard"),
    "ProBuilder/Standard Vertex Color": _standard(vertex_color=True),
    # Lux Water: its _Color is the colour the captures show for the sea at evening and night, and its
    # _Density sets how much of what lies behind it shows (materials.WATER_DEPTH); its refraction, depth
    # absorption and underwater effect aren't drawn, so the day sea lacks the sand's turquoise.
    "Lux Water/WaterSurface": _water("_Color", density="_Density"),
    "Lux Water/WaterSurface Tessellation": _water("_Color", density="_Density"),
    "NatureManufacture Shaders/Water/Water River Mobile": _water("_ShalowColor"),
    "NatureManufacture Shaders/Water/Water River Tesseled": _water("_ShalowColor"),
    "NatureManufacture Shaders/Water/Water River Tesseled Vertex Color": _water("_ShalowColor"),
    "Legacy Shaders/Particles/VertexLit Blended": _unlit(APPROXIMATED, "drawn unlit", tint="_EmisColor"),
    "FX/MirrorReflection": _skip("mirror"),
    "Custom/MiniMapRoad": _skip("mini-map overlay"),
}

UNKNOWN = _skip("no Shader Tier for this shader")


def tier(shader: str) -> Tier:
    return TIERS.get(shader, UNKNOWN)
