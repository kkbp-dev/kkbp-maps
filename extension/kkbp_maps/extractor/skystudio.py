"""Funly SkyStudio skies (KKS): what the TimeOfDayController sets on the skybox and on the sun and moon
lights for a profile, worked out from the profile alone.

KKS keeps its sky in a `SkyProfile` per Time of Day (`MapSkyInfo`). Each frame the controller puts the
profile's skybox material on RenderSettings, sets its shader values from the profile's keyframes
(`SkyMaterialController`), switches its keywords by the profile's features, and aims and colours the
light under the sun and moon orbits. The materials as stored are stale (kks-spike.md, section 4), so
the values here are the profile's. Every property in KKS's profiles has one keyframe, so the sky time
doesn't matter; a profile with more stops the extraction.

The tables are Funly's code written as data, decompiled from KKS's `Assembly-CSharp`
(`TimeOfDayController.UpdateSkyForCurrentTime`, `SkyMaterialController`, `Standard3dShaderDefinition`):
names are the only marker Funly gives. Directions are converted to Blender's space here (ADR 0011).
"""

from __future__ import annotations

import math

from ..bundle.hashing import shortest32
from . import space

SHADER_PREFIX = "Funly/Sky Studio/"

# Feature -> (shader keyword or None for a plain switch, the feature it depends on, the value that one
# must have). Standard3dShaderDefinition.
FEATURES: dict[str, tuple[str | None, str | None, bool]] = {
    "GradientSkyFeature": ("GRADIENT_BACKGROUND", None, False),
    "SunFeature": ("SUN", None, False),
    "MoonFeature": ("MOON", None, False),
    "CloudFeature": ("CLOUDS", None, False),
    "FogFeature": ("HORIZON_FOG", None, False),
    "StarBasicFeature": ("STARS_BASIC", "MobileQualityFeature", True),
    "StarLayer1Feature": ("STAR_LAYER_1", "MobileQualityFeature", False),
    "StarLayer2Feature": ("STAR_LAYER_2", "MobileQualityFeature", False),
    "StarLayer3Feature": ("STAR_LAYER_3", "MobileQualityFeature", False),
    "VertexGradientSkyFeature": ("VERTEX_GRADIENT_BACKGROUND", None, False),
    "SunCustomTextureFeature": ("SUN_CUSTOM_TEXTURE", None, False),
    "SunSpriteSheetFeature": ("SUN_SPRITE_SHEET", "SunCustomTextureFeature", True),
    "SunAlphaBlendFeature": ("SUN_ALPHA_BLEND", "SunCustomTextureFeature", True),
    "SunRotationFeature": ("SUN_ROTATION", "SunCustomTextureFeature", True),
    "MoonCustomTextureFeature": ("MOON_CUSTOM_TEXTURE", None, False),
    "MoonSpriteSheetFeature": ("MOON_SPRITE_SHEET", "MoonCustomTextureFeature", True),
    "MoonAlphaBlendFeature": ("MOON_ALPHA_BLEND", "MoonCustomTextureFeature", True),
    "MoonRotationFeature": ("MOON_ROTATION", "MoonCustomTextureFeature", True),
    "StarLayer1CustomTextureFeature": ("STAR_LAYER_1_CUSTOM_TEXTURE", None, False),
    "StarLayer1SpriteSheetFeature": ("STAR_LAYER_1_SPRITE_SHEET", "StarLayer1CustomTextureFeature", True),
    "StarLayer2CustomTextureFeature": ("STAR_LAYER_2_CUSTOM_TEXTURE", None, False),
    "StarLayer2SpriteSheetFeature": ("STAR_LAYER_2_SPRITE_SHEET", "StarLayer2CustomTextureFeature", True),
    "StarLayer3CustomTextureFeature": ("STAR_LAYER_3_CUSTOM_TEXTURE", None, False),
    "StarLayer3SpriteSheetFeature": ("STAR_LAYER_3_SPRITE_SHEET", "StarLayer3CustomTextureFeature", True),
    "NoiseCloudFeature": ("NOISE_CLOUDS", "CloudFeature", True),
    "CubemapCloudFeature": ("CUBEMAP_CLOUDS", "CloudFeature", True),
    "CubemapNormalCloudFeature": ("CUBEMAP_NORMAL_CLOUDS", "CloudFeature", True),
    "CubemapCloudTextureFormatRGBFeature": ("CUBEMAP_CLOUD_FORMAT_RGB", "CubemapCloudFeature", True),
    "CubemapCloudTextureFormatRGBAFeature": ("CUBEMAP_CLOUD_FORMAT_RGBA", "CubemapCloudFeature", True),
    "CubemapCloudDoubleLayerFeature": ("CUBEMAP_CLOUD_DOUBLE_LAYER", "CubemapCloudFeature", True),
    "CubemapCloudDoubleLayerCubemap": ("CUBEMAP_CLOUD_DOUBLE_LAYER_CUSTOM_TEXTURE", "CubemapCloudDoubleLayerFeature", True),
    "CubemapNormalCloudDoubleLayerFeature": ("CUBEMAP_NORMAL_CLOUD_DOUBLE_LAYER", "CubemapNormalCloudFeature", True),
    "MobileQualityFeature": (None, None, False),
    "RainFeature": (None, None, False),
    "RainSplashFeature": (None, None, False),
    "LightningFeature": (None, None, False),
    "RainSoundFeature": (None, None, False),
    "ThunderFeature": (None, None, False),
}

# (the features that must all be on, [(profile key, kind, shader property)]), in the
# controller's order. Values set again later win, as on the material.
C, F, T = "color", "float", "texture"
_STARS = [(f"StarLayer{n}Feature", [(f"Star{n}ColorKey", C, f"_StarLayer{n}Color"),
                                    (f"Star{n}SizeKey", F, f"_StarLayer{n}MaxRadius"),
                                    (f"Star{n}TextureKey", T, f"_StarLayer{n}Tex"),
                                    (f"Star{n}TwinkleAmountKey", F, f"_StarLayer{n}TwinkleAmount"),
                                    (f"Star{n}TwinkleSpeedKey", F, f"_StarLayer{n}TwinkleSpeed"),
                                    (f"Star{n}RotationSpeed", F, f"_StarLayer{n}RotationSpeed"),
                                    (f"Star{n}EdgeFeathering", F, f"_StarLayer{n}EdgeFade"),
                                    (f"Star{n}ColorIntensityKey", F, f"_StarLayer{n}HDRBoost")]) for n in (1, 2, 3)]
VALUES: list[tuple[tuple[str, ...], list[tuple[str, str, str]]]] = [
    ((), [("SkyCubemapKey", T, "_MainTex"), ("SkyUpperColorKey", C, "_GradientSkyUpperColor"),
          ("SkyMiddleColorKey", C, "_GradientSkyMiddleColor"), ("SkyLowerColorKey", C, "_GradientSkyLowerColor"),
          ("SkyMiddleColorPosition", F, "_GradientFadeMiddlePosition"),
          ("HorizonStarScaleKey", F, "_HorizonScaleFactor")]),
    (("CloudFeature", "NoiseCloudFeature"), [
        ("CloudNoiseTextureKey", T, "_CloudNoiseTexture"), ("CloudTextureTiling", F, "_CloudTextureTiling"),
        ("CloudDensityKey", F, "_CloudDensity"), ("CloudSpeedKey", F, "_CloudSpeed"),
        ("CloudDirectionKey", F, "_CloudDirection"), ("CloudHeightKey", F, "_CloudHeight"),
        ("CloudColor1Key", C, "_CloudColor1"), ("CloudColor2Key", C, "_CloudColor2"),
        ("CloudFadePositionKey", F, "_CloudFadePosition"), ("CloudFadeAmountKey", F, "_CloudFadeAmount")]),
    (("CloudFeature", "CubemapCloudFeature"), [
        ("CloudCubemapTextureKey", T, "_CloudCubemapTexture"),
        ("CloudCubemapRotationSpeedKey", F, "_CloudCubemapRotationSpeed"),
        ("CloudCubemapTintColorKey", C, "_CloudCubemapTintColor"), ("CloudCubemapHeightKey", F, "_CloudCubemapHeight")]),
    (("CloudFeature", "CubemapCloudFeature", "CubemapCloudDoubleLayerFeature"), [
        ("CloudCubemapDoubleLayerHeightKey", F, "_CloudCubemapDoubleLayerHeight"),
        ("CloudCubemapDoubleLayerRotationSpeedKey", F, "_CloudCubemapDoubleLayerRotationSpeed"),
        ("CloudCubemapDoubleLayerTintColorKey", C, "_CloudCubemapDoubleLayerTintColor")]),
    (("CloudFeature", "CubemapCloudFeature", "CubemapCloudDoubleLayerFeature", "CubemapCloudDoubleLayerCubemap"), [
        ("CloudCubemapDoubleLayerCustomTextureKey", T, "_CloudCubemapDoubleTexture")]),
    (("CloudFeature", "CubemapNormalCloudFeature"), [
        ("CloudCubemapNormalTextureKey", T, "_CloudCubemapNormalTexture"),
        ("CloudCubemapNormalLitColorKey", C, "_CloudCubemapNormalLitColor"),
        ("CloudCubemapNormalShadowColorKey", C, "_CloudCubemapNormalShadowColor"),
        ("CloudCubemapNormalAmbientIntensityKey", F, "_CloudCubemapNormalAmbientIntensity"),
        ("CloudCubemapNormalHeightKey", F, "_CloudCubemapNormalHeight"),
        ("CloudCubemapNormalRotationSpeedKey", F, "_CloudCubemapNormalRotationSpeed")]),
    (("CloudFeature", "CubemapNormalCloudFeature", "CubemapNormalCloudDoubleLayerFeature"), [
        ("CloudCubemapNormalDoubleLayerHeightKey", F, "_CloudCubemapNormalDoubleLayerHeight"),
        ("CloudCubemapNormalDoubleLayerRotationSpeedKey", F, "_CloudCubemapNormalDoubleLayerRotationSpeed"),
        ("CloudCubemapNormalDoubleLayerLitColorKey", C, "_CloudCubemapNormalDoubleLitColor"),
        ("CloudCubemapNormalDoubleLayerShadowKey", C, "_CloudCubemapNormalDoubleShadowColor")]),
    (("CloudFeature", "CubemapNormalCloudFeature", "CubemapNormalCloudDoubleLayerFeature",
      "CubemapNormalCloudDoubleLayerCubemap"), [
        ("CloudCubemapNormalDoubleLayerCustomTextureKey", T, "_CloudCubemapNormalDoubleTexture")]),
    (("FogFeature",), [("FogColorKey", C, "_HorizonFogColor"), ("FogDensityKey", F, "_HorizonFogDensity"),
                       ("FogLengthKey", F, "_HorizonFogLength")]),
    (("SunFeature",), [("SunColorKey", C, "_SunColor"), ("SunSizeKey", F, "_SunRadius"),
                       ("SunEdgeFeatheringKey", F, "_SunEdgeFade"), ("SunColorIntensityKey", F, "_SunHDRBoost")]),
    (("SunFeature", "SunCustomTextureFeature"), [("SunTextureKey", T, "_SunTex")]),
    (("SunFeature", "SunSpriteSheetFeature"), [("SunSpriteItemCount", F, "_SunSpriteItemCount"),
                                               ("SunSpriteAnimationSpeed", F, "_SunSpriteAnimationSpeed")]),
    (("MoonFeature",), [("MoonColorKey", C, "_MoonColor"), ("MoonSizeKey", F, "_MoonRadius"),
                        ("MoonEdgeFeatheringKey", F, "_MoonEdgeFade"), ("MoonColorIntensityKey", F, "_MoonHDRBoost")]),
    (("MoonFeature", "MoonCustomTextureFeature"), [("MoonTextureKey", T, "_MoonTex")]),
    (("MoonFeature", "MoonSpriteSheetFeature"), [("MoonSpriteItemCount", F, "_MoonSpriteItemCount"),
                                                 ("MoonSpriteAnimationSpeed", F, "_MoonSpriteAnimationSpeed")]),
    (("StarBasicFeature",), [
        ("StarBasicCubemapKey", T, "_StarBasicCubemap"), ("StarBasicTwinkleSpeedKey", F, "_StarBasicTwinkleSpeed"),
        ("StarBasicTwinkleAmountKey", F, "_StarBasicTwinkleAmount"), ("StarBasicOpacityKey", F, "_StarBasicOpacity"),
        ("StarBasicTintColorKey", C, "_StarBasicTintColor"), ("StarBasicExponentKey", F, "_StarBasicExponent"),
        ("StarBasicIntensityKey", F, "_StarBasicHDRBoost")]),
] + [((feature,), entries) for feature, entries in _STARS]
# Values computed from two keys: (begin key, length key, begin property, end property), end =
# clamp(begin + length, -1, 1) (ApplyGradientValuesOnMaterial, ApplyStarFadeValuesOnMaterial).
FADES = [("HorizonTransitionStartKey", "HorizonTransitionLengthKey", "_GradientFadeBegin", "_GradientFadeEnd"),
         ("StarTransitionStartKey", "StarTransitionLengthKey", "_StarFadeBegin", "_StarFadeEnd")]
# Sprite sheet dimensions: (feature, columns key, rows key, vector property).
SPRITES = [("SunSpriteSheetFeature", "SunSpriteColumnCountKey", "SunSpriteRowCountKey", "_SunSpriteDimensions"),
           ("MoonSpriteSheetFeature", "MoonSpriteColumnCountKey", "MoonSpriteRowCountKey", "_MoonSpriteDimensions")] + [
    (f"StarLayer{n}SpriteSheetFeature", f"Star{n}SpriteColumnCountKey", f"Star{n}SpriteRowCountKey",
     f"_StarLayer{n}SpriteDimensions") for n in (1, 2, 3)]
# A star layer's data texture is a field of the profile, not a keyframe.
STAR_DATA = [(f"StarLayer{n}Feature", f"starLayer{n}DataTexture", f"_StarLayer{n}DataTex") for n in (1, 2, 3)]
# Directions: (feature, sphere point key, vector property).
BODIES = {"sun": ("SunFeature", "SunPositionKey", "_SunPosition", "SunLightColorKey", "SunLightIntensityKey"),
          "moon": ("MoonFeature", "MoonPositionKey", "_MoonPosition", "MoonLightColorKey", "MoonLightIntensityKey")}
GROUPS = {"color": "m_ColorGroup", "float": "m_NumberGroup", "texture": "m_TextureGroup",
          "sphere": "m_SpherePointGroup", "bool": "m_BoolGroup"}


class SkyStudioError(NotImplementedError):
    pass


class Profile:
    """A SkyProfile's typetree, read as the controller reads it at any sky time (single keyframes)."""

    def __init__(self, tree: dict):
        self.tree = tree
        self.name = tree.get("m_Name", "")
        status = tree.get("featureStatus", {})
        self.status = dict(zip(status.get("m_Keys", []), (bool(v) for v in status.get("m_Values", []))))
        self.groups = {}
        for kind, field in GROUPS.items():
            g = tree.get("keyframeGroups", {}).get(field, {})
            self.groups[kind] = dict(zip(g.get("m_Keys", []), g.get("m_Values", [])))

    def enabled(self, feature: str) -> bool:
        """SkyProfile.IsFeatureEnabled: on, and every feature it depends on at the value it needs."""
        if feature not in FEATURES or not self.status.get(feature):
            return False
        while True:
            _, parent, needed = FEATURES[feature]
            if parent is None:
                return True
            if self.status.get(parent, False) != needed:
                return False
            feature = parent

    def value(self, kind: str, key: str):
        group = self.groups[kind].get(key)
        if group is None:
            return None
        frames = group.get("keyframes", [])
        if len(frames) > 1:
            raise SkyStudioError(f"SkyStudio profile {self.name}: {key} has {len(frames)} keyframes")
        if not frames:
            return None
        f = frames[0]
        return {"color": lambda: f["color"], "float": lambda: f["value"], "texture": lambda: f["texture"],
                "sphere": lambda: f["spherePoint"], "bool": lambda: f["value"]}[kind]()

    def keywords(self) -> list[str]:
        """The keywords SynchronizeAllShaderKeywords leaves on."""
        return sorted({kw for f, (kw, _, _) in FEATURES.items() if kw and self.enabled(f)})


def direction(point: dict) -> tuple[float, float, float]:
    """SphereUtility.SphericalCoordinateToDirection, in Unity's space."""
    h, v = point["horizontalRotation"], point["verticalRotation"]
    return (math.cos(v) * math.cos(h), math.sin(v), math.cos(v) * math.sin(h))


def look_rotation(forward) -> tuple[float, float, float, float]:
    """Unity's Quaternion.LookRotation(forward, up), as (x, y, z, w): the rotation whose +Z is forward."""
    fx, fy, fz = forward
    n = math.sqrt(fx * fx + fy * fy + fz * fz)
    f = (fx / n, fy / n, fz / n)
    up = (0.0, 1.0, 0.0) if abs(f[1]) < 0.9999 else (0.0, 0.0, 1.0)
    r = (up[1] * f[2] - up[2] * f[1], up[2] * f[0] - up[0] * f[2], up[0] * f[1] - up[1] * f[0])
    rn = math.sqrt(sum(c * c for c in r))
    r = tuple(c / rn for c in r)
    u = (f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0])
    m00, m01, m02 = r[0], u[0], f[0]
    m10, m11, m12 = r[1], u[1], f[1]
    m20, m21, m22 = r[2], u[2], f[2]
    trace = m00 + m11 + m22
    if trace > 0:
        s = math.sqrt(trace + 1.0) * 2
        return ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, 0.25 * s)
    if m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        return (0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    if m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        return ((m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s)
    s = math.sqrt(1.0 + m22 - m00 - m11) * 2
    return ((m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s)


def sky_values(profile: Profile, base: dict, texture) -> dict:
    """The skybox's values as the controller leaves them: `base` is the material's own record parts
    (colors, floats, vectors, textures by raw name, as materials.py reads them), overwritten by the
    profile's. `texture(pptr)` turns a profile's texture reference into a texture id, or None."""
    colors, floats, vectors = dict(base["colors"]), dict(base["floats"]), dict(base["vectors"])
    textures = {t["raw"]: t for t in base["textures"]}

    def put(kind, prop, v):
        if kind == C:
            colors[prop] = [shortest32(v[c]) for c in "rgba"]
        elif kind == F:
            floats[prop] = shortest32(float(v))
        elif kind == T:
            tid = texture(v)
            if tid is None:
                textures.pop(prop, None)
            else:
                textures[prop] = {"raw": prop, "texture": tid, "offset": [0.0, 0.0], "scale": [1.0, 1.0]}

    for needed, entries in VALUES:
        if all(profile.enabled(f) for f in needed):
            for key, kind, prop in entries:
                v = profile.value(kind, key)
                if v is not None:
                    put(kind, prop, v)
    for begin, length, prop_begin, prop_end in FADES:
        b, n = profile.value(F, begin), profile.value(F, length)
        if b is not None and n is not None:
            floats[prop_begin] = shortest32(b)
            floats[prop_end] = shortest32(max(-1.0, min(1.0, b + n)))
    for feature, cols, rows, prop in SPRITES:
        if profile.enabled(feature):
            vectors[prop] = [shortest32(float(int(profile.value(F, cols) or 0))),
                             shortest32(float(int(profile.value(F, rows) or 0))), 0.0, 0.0]
    for feature, field, prop in STAR_DATA:
        if profile.enabled(feature):
            put(T, prop, profile.tree.get(field))
    for feature, point_key, prop, _, _ in BODIES.values():
        if profile.enabled(feature):
            d = space.vector(direction(profile.value("sphere", point_key)))
            vectors[prop] = [shortest32(c) for c in d] + [0.0]
    return {"colors": colors, "floats": floats, "vectors": vectors,
            "textures": sorted(textures.values(), key=lambda t: t["raw"])}


def body_light(profile: Profile, body: str) -> dict | None:
    """The sun's or moon's light as the controller sets it: None when off, else its Unity world rotation
    (x, y, z, w), colour and intensity. The orbit faces away from the body and its light has no rotation
    of its own (OrbitingBody, `transform.forward = -direction`)."""
    feature, point_key, _, color_key, intensity_key = BODIES[body]
    if not profile.enabled(feature):
        return None
    d = direction(profile.value("sphere", point_key))
    c = profile.value(C, color_key) or {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
    return {"rotation": look_rotation((-d[0], -d[1], -d[2])), "color": [c[k] for k in "rgba"],
            "intensity": float(profile.value(F, intensity_key) or 0.0)}
