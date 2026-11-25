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


def _standard(level=REBUILT, reason="", double_sided=False):
    return Tier("standard", level, reason, double_sided)


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
}

UNKNOWN = _skip("no Shader Tier for this shader")


def tier(shader: str) -> Tier:
    return TIERS.get(shader, UNKNOWN)
