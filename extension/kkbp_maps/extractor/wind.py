"""SpeedTree wind and WindZones (Map Bundle 0.10): how the game moves its trees, kept as data.

A SpeedTree renderer's GameObject has a `Tree` whose SpeedTreeWindAsset holds the tree's wind: m_sParams,
its numbers (some grouped, kept by dotted path), and the asset's own fields, numbers and switches. Each
distinct asset becomes one entry of scene.json's `winds`, which the renderer names by index. A WindZone
is kept on its node. None of it is part of a Content Hash, and the Builder draws trees at rest.
"""

from __future__ import annotations

import json

from ..bundle.hashing import shortest32

ZONE_MODES = {0: "directional", 1: "spherical"}


def _flatten(prefix: str, value, out: dict):
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out[prefix] = shortest32(float(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}" if prefix else k, v, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _flatten(f"{prefix}[{i}]", v, out)


def wind_record(asset: dict) -> dict:
    """A SpeedTreeWindAsset's tree as a `winds` entry."""
    w = asset.get("m_Wind", {})
    floats: dict[str, float] = {}
    _flatten("", w.get("m_sParams", {}), floats)
    own = {k: v for k, v in w.items() if k != "m_sParams"}
    _flatten("", {k: v for k, v in own.items() if not isinstance(v, bool)}, floats)
    flags = sorted(k for k, v in own.items() if v is True)
    return {"kind": "speedtree", "floats": dict(sorted(floats.items())), "flags": flags}


def zone_record(zone: dict) -> dict | None:
    """A WindZone component as a node's `wind_zone`, or None for one that is off."""
    if not zone.get("m_Enabled", 1):
        return None
    return {"mode": ZONE_MODES.get(int(zone.get("m_Mode", 0)), "directional"),
            "radius": shortest32(zone.get("m_Radius", 20.0)), "main": shortest32(zone.get("m_WindMain", 1.0)),
            "turbulence": shortest32(zone.get("m_WindTurbulence", 1.0)),
            "pulse_magnitude": shortest32(zone.get("m_WindPulseMagnitude", 0.5)),
            "pulse_frequency": shortest32(zone.get("m_WindPulseFrequency", 0.01))}


class Winds:
    """The Map's `winds`, each distinct asset once, in the order renderers first name them."""

    def __init__(self, store):
        self.store = store
        self.records: list[dict] = []
        self._keys: dict[str, int] = {}

    def of(self, obj) -> int | None:
        """The `winds` index of the tree on `obj` (a scene Obj), or None."""
        tree = obj.component("Tree") if obj is not None else None
        if tree is None:
            return None
        asset = self.store.resolve(tree, self.store.tree(tree).get("m_SpeedTreeWindAsset"))
        if asset is None or not self.store.is_loaded(asset):
            return None
        record = wind_record(self.store.tree(asset))
        key = json.dumps(record, sort_keys=True)
        if key not in self._keys:
            self._keys[key] = len(self.records)
            self.records.append(record)
        return self._keys[key]

    def zone(self, obj) -> dict | None:
        z = obj.component("WindZone") if obj is not None else None
        return zone_record(self.store.tree(z)) if z is not None else None
