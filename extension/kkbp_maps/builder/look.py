"""Look switches: Builder choices the look check (Phase 5) measures against the Reference Captures before
one is settled. Developer-only; a user's build always takes the defaults. Never imports bpy.

    blender ... tools/blender_build.py -- ... --look shadow_cull=none --look sun_angle=0

Each switch is a name, its choices (or a type), and its default, which is the current answer. A settled
switch is removed and its answer becomes plain Builder code, recorded in kk-spike.md or an ADR.
"""

from __future__ import annotations

SWITCHES: dict[str, tuple[object, str]] = {
    # The reflection term on or off, to measure what it adds to a view.
    "reflection": (("on", "off"), "on"),
}

# Settled by the look check (kk-spike.md, "Settled by the look check"): shadow culling as Unity's
# per-renderer mode (ADR 0024), 1F's Flat ambient over its stale probe, reflections blurred by roughness,
# and the sun's soft angle, which changes no view.

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
