"""Look switches: Builder choices the look check (Phase 5) measures against the Reference Captures before
one is settled. Developer-only; a user's build always takes the defaults. Never imports bpy.

    blender ... tools/blender_build.py -- ... --look shadow_cull=none --look sun_angle=0

Each switch is a name, its choices (or a type), and its default, which is the current answer. A settled
switch is removed and its answer becomes plain Builder code, recorded in kk-spike.md or an ADR.
"""

from __future__ import annotations

SWITCHES: dict[str, tuple[object, str]] = {
    # Whether a one-sided material casts shadows from its front faces only, as Unity's shadow pass culls.
    "shadow_cull": (("front", "none"), "front"),
    # 1F's ambient: the Flat colour its mode names, or the (stale) SH probe it also holds (kk-spike 6).
    "flat_ambient": (("flat", "probe"), "flat"),
    # The sun's soft shadow angle in degrees (EEVEE); Unity's soft shadows have no angle.
    "sun_angle": (float, "0.5"),
    # The reflection: sampled sharp from the top mip, or left out (to measure what it adds).
    "reflection": (("sharp", "off"), "sharp"),
}

_current: dict[str, str] = {}


def set_switches(pairs: list[str] | None):
    """`name=value` pairs, checked against SWITCHES."""
    _current.clear()
    for pair in pairs or ():
        name, _, value = pair.partition("=")
        if name not in SWITCHES:
            raise ValueError(f"no look switch {name!r}; there are {sorted(SWITCHES)}")
        kind, _ = SWITCHES[name]
        if isinstance(kind, tuple) and value not in kind:
            raise ValueError(f"look switch {name} takes {list(kind)}, not {value!r}")
        if kind is float:
            float(value)
        _current[name] = value


def get(name: str) -> str:
    return _current.get(name, SWITCHES[name][1])


def number(name: str) -> float:
    return float(get(name))


def current() -> dict[str, str]:
    """Every switch that differs from its default, for the Build Report."""
    return dict(_current)
