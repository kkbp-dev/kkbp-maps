"""Funly SkyStudio's skybox (KKS), `Funly/Sky Studio/Skybox/3D Standard`, as World nodes.

Rebuilt from the shader's own D3D11 programs (KKBP's dump.py on KKS's map/materials/00), with the values
the Map Bundle's `material` Sky holds (extractor/skystudio.py). What is drawn, by keyword:

- GRADIENT_BACKGROUND (and VERTEX_GRADIENT_BACKGROUND, the same per vertex): lower colour to middle to
  upper, each step a smoothstep over the height, the middle at _GradientFadeMiddlePosition between
  _GradientFadeBegin and _GradientFadeEnd.
- SUN and MOON: a disc of _SunRadius (_MoonRadius) around the body's direction, feathered by its edge fade,
  times its colour and HDR boost, added to the sky; inside the moon's disc the sky is replaced.
- NOISE_CLOUDS: the noise texture looked up along the view bent towards the cloud height, mixed from two
  colours and faded towards the horizon. The game's time is 0, so the clouds stand where they start.

Left out, and so approximated: the star layers, the moon's and sun's custom textures, cubemap clouds and
the horizon fog. Every direction is Blender's (ADR 0011); the shader's are Unity's, (x, y, z) =
(-X, Z, -Y).
"""

from __future__ import annotations

from .materials import linear, linear_rgb
from .nodes import Graph, io, new_group

from ..plan import SKYSTUDIO as SHADER   # noqa: F401  (what the Build Report says isn't drawn: plan.sky_notes)


def _smooth01(g: Graph, x):
    """saturate(x), then x² (3 − 2x): the shader's smoothstep."""
    t = g.math("MAXIMUM", g.math("MINIMUM", x, 1.0), 0.0)
    return g.math("MULTIPLY", g.math("MULTIPLY", t, t), g.math("MULTIPLY_ADD", t, -2.0, 3.0))


def _rgb(g, sky, prop, default=(0.0, 0.0, 0.0, 1.0)):
    """A colour as the shader receives it: serialized sRGB, which Unity sets on the material as linear."""
    return g.rgb(linear_rgb(sky["colors"].get(prop, default)))


def _f(sky, prop, default=0.0) -> float:
    return float(sky["floats"].get(prop, default))


def _disc(g, sky, n, position, radius, edge, color, boost):
    """A body's disc: (inside, feathered colour). n is the unit view direction in Blender's axes."""
    p = sky["vectors"].get(position, [0.0, 0.0, 1.0, 0.0])[:3]
    r, e = _f(sky, radius), _f(sky, edge)
    dist = g.vmath("DISTANCE", n, tuple(p))
    inside = g.math("LESS_THAN", dist, r + 1e-6)
    # (|n − p| − r) / (r(1 − e) − r), saturated and smoothed
    denom = r * (1.0 - e) - r
    fade = _smooth01(g, g.math("DIVIDE", g.math("SUBTRACT", dist, r), denom if abs(denom) > 1e-9 else -1e-9))
    lit = g.mix(1.0, _rgb(g, sky, color), g.combine(fade, fade, fade), blend_type="MULTIPLY")
    lit = g.mix(1.0, lit, g.rgb((_f(sky, boost, 1.0),) * 3), blend_type="MULTIPLY")
    return inside, lit


def group(sky: dict, images, bundle, name: str):
    """`.KKM Sky <Map Variant>`: the sky as a node group, a direction in Blender's world axes in and its
    colour out, for the World."""
    import bpy
    tree = bpy.data.node_groups.get(f".KKM Sky {name}")
    if tree is not None:
        return tree
    tree = new_group(f".KKM Sky {name}", inputs=[("Vector", "NodeSocketVector", (0.0, 0.0, 1.0))],
                     outputs=[("Color", "NodeSocketColor")])
    g, i, o = io(tree)
    g.link(skystudio(g, sky, images, bundle, (i, "Vector")), (o, "Color"))
    return tree


def skystudio(g: Graph, sky: dict, images, bundle, direction):
    """The sky's colour along `direction` (a vector socket, Blender's world axes)."""
    kw = set(sky["keywords"])
    n = g.vmath("NORMALIZE", direction)
    sep = g.node("ShaderNodeSeparateXYZ", Vector=n)
    y = (sep, "Z")                                   # Unity's height
    ux, uz = g.math("MULTIPLY", (sep, "X"), -1.0), g.math("MULTIPLY", (sep, "Y"), -1.0)   # Unity's x and z

    # The gradient.
    begin, end, middle = _f(sky, "_GradientFadeBegin"), _f(sky, "_GradientFadeEnd", 1.0), _f(sky, "_GradientFadeMiddlePosition", 0.5)
    mid = (end - begin) * middle + begin
    low_span = (end - begin) * middle
    t1 = _smooth01(g, g.math("DIVIDE", g.math("SUBTRACT", y, begin), low_span if abs(low_span) > 1e-9 else 1e-9))
    t2 = _smooth01(g, g.math("DIVIDE", g.math("SUBTRACT", y, mid), (end - mid) if abs(end - mid) > 1e-9 else 1e-9))
    lower = g.mix(t1, _rgb(g, sky, "_GradientSkyLowerColor"), _rgb(g, sky, "_GradientSkyMiddleColor"))
    upper = g.mix(t2, _rgb(g, sky, "_GradientSkyMiddleColor"), _rgb(g, sky, "_GradientSkyUpperColor"))
    color = g.mix(g.math("GREATER_THAN", y, mid - 1e-6), lower, upper)

    if "SUN" in kw:
        inside, lit = _disc(g, sky, n, "_SunPosition", "_SunRadius", "_SunEdgeFade", "_SunColor", "_SunHDRBoost")
        color = g.mix(inside, color, g.mix(1.0, color, lit, blend_type="ADD"))
    if "MOON" in kw:   # inside its disc the sky is replaced (its texture isn't drawn)
        inside, lit = _disc(g, sky, n, "_MoonPosition", "_MoonRadius", "_MoonEdgeFade", "_MoonColor", "_MoonHDRBoost")
        color = g.mix(inside, color, lit)
    if "CLOUDS" in kw and "NOISE_CLOUDS" in kw:
        color = _noise_clouds(g, sky, images, bundle, n, y, ux, uz, color)
    return color


def _noise_clouds(g, sky, images, bundle, n, y, ux, uz, color):
    tex = next((t for t in sky["textures"] if t["raw"] == "_CloudNoiseTexture"), None)
    if tex is None:
        return color
    # The vertex program: the view bent by the cloud height, turned by the cloud direction, tiled.
    import math
    height = (1.0 - _f(sky, "_CloudHeight", 0.5)) * 70.0 + 30.0
    d = _f(sky, "_CloudDirection")
    ry = g.math("MULTIPLY", y, height * 0.2)
    rx = g.math("ADD", g.math("MULTIPLY", ux, math.cos(d)), g.math("MULTIPLY", uz, -math.sin(d)))
    rz = g.math("ADD", g.math("MULTIPLY", ux, math.sin(d)), g.math("MULTIPLY", uz, math.cos(d)))
    length = g.vmath("LENGTH", g.node("ShaderNodeCombineXYZ", X=rx, Y=ry, Z=rz))
    tiling = _f(sky, "_CloudTextureTiling", 1.0)
    u = g.math("MULTIPLY", g.math("DIVIDE", rx, length), tiling)
    v = g.math("MULTIPLY", g.math("DIVIDE", rz, length), tiling)
    img = images.get(bundle, tex["texture"])
    s = g.node("ShaderNodeTexImage", image=img, interpolation="Linear", extension="REPEAT",
               Vector=g.node("ShaderNodeCombineXYZ", X=u, Y=v, Z=0.0))
    rgb = g.node("ShaderNodeSeparateColor", Color=(s, "Color"))

    def enc(c):   # the shader re-encodes the sampled channels to sRGB
        c = g.math("MAXIMUM", c, 0.0)
        return g.math("MAXIMUM", g.math("MULTIPLY_ADD", g.math("POWER", c, 1.0 / 2.4), 1.055, -0.055), 0.0)
    r, gg, b = enc((rgb, "Red")), enc((rgb, "Green")), enc((rgb, "Blue"))
    # Both lookups land on the same texel at time 0: x·w = r·b, (y + z) = 2·g.
    a = g.math("SQRT", g.math("MULTIPLY", r, b))
    q4 = g.math("POWER", g.math("MULTIPLY", gg, 2.0), 0.25)
    q = g.math("MULTIPLY", a, q4)

    def gamma(prop):   # the shader raises the (linear) colour it receives to 2.2 itself
        c = sky["colors"].get(prop, [1.0, 1.0, 1.0, 1.0])
        return g.rgb(tuple(max(0.0, linear(x)) ** 2.2 for x in c[:3]))
    c1 = g.mix(1.0, gamma("_CloudColor1"), g.combine(a, a, a), blend_type="MULTIPLY")
    c2 = g.mix(1.0, gamma("_CloudColor2"), g.combine(q4, q4, q4), blend_type="MULTIPLY")
    # c2 + q (1.5 c1 − c2)
    diff = g.mix(1.0, g.mix(1.0, c1, g.rgb((1.5, 1.5, 1.5)), blend_type="MULTIPLY"), c2, blend_type="SUBTRACT")
    cloud = g.mix(1.0, c2, g.mix(1.0, diff, g.combine(q, q, q), blend_type="MULTIPLY"), blend_type="ADD")
    alpha = g.math("MINIMUM", g.math("POWER", q, (1.0 - _f(sky, "_CloudDensity", 0.5)) * 7.0), 1.0)
    fade_at = _f(sky, "_CloudFadePosition")
    horizontal = g.math("SQRT", g.math("ADD", g.math("MULTIPLY", ux, ux), g.math("MULTIPLY", uz, uz)))
    f = _smooth01(g, g.math("DIVIDE", g.math("SUBTRACT", horizontal, fade_at), max(1e-6, 1.0 - fade_at)))
    alpha = g.math("MULTIPLY", alpha, g.math("MULTIPLY_ADD", f, -_f(sky, "_CloudFadeAmount"), 1.0))
    alpha = g.math("MULTIPLY", alpha, g.math("GREATER_THAN", y, -1e-6))
    return g.mix(alpha, color, cloud)
