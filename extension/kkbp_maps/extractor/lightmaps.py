"""The Map's Lightmap Set: its lightmaps decoded, and the lightmap each renderer uses.

The renderer's own m_LightmapIndex and m_LightmapTilingOffset apply, replaced by its LightmapPrefab
entry where it has one, as LightmapPrefab.Start does (kk-spike, section 4). A mesh without uv1 is lit
through uv0.
"""

from __future__ import annotations

from ..bundle.hashing import shortest32
from .meshes import Meshes
from .scene import NO_LIGHTMAP, Graph, Unsupported, Walk
from .textures import Textures

SET_ID = "scene"
DIRECTIONAL = 1  # LightmapSettings.m_LightmapsMode: combined directional


def prefab_entries(graph: Graph) -> dict:
    """renderer Ref -> (index, scale-offset) from every LightmapPrefab whose Start runs."""
    store = graph.store
    out = {}
    for mb in graph.behaviours.get("LightmapPrefab", []):
        t = store.tree(mb)
        owner = graph.obj_of(mb)
        if not t.get("m_Enabled", 1) or owner is None:
            continue
        if not any(graph.world_active(owner, tod) for tod in graph.game.times_of_day):
            continue
        for e in t.get("lightmapParameters", []):
            renderer = store.resolve(mb, e.get("renderer"))
            if renderer is None or e.get("lightmapIndex", -1) < 0:
                continue
            so = e["scaleOffset"]
            out[renderer] = (e["lightmapIndex"], (so["x"], so["y"], so["z"], so["w"]))
    return out


def lightmap_set(graph: Graph, walk: Walk, meshes: Meshes, textures: Textures) -> dict | None:
    """lightmaps.json's set for the Map, or None if no kept renderer uses a lightmap."""
    store = graph.store
    settings = store.refs("LightmapSettings")
    if not settings:
        return None
    s = store.tree(settings[0])
    slots = s.get("m_Lightmaps", [])
    prefab = prefab_entries(graph)
    assignments, used = [], set()
    for i, node in enumerate(walk.nodes):
        r = node.renderer
        if r is None or node.sky:
            continue
        index, so = prefab.get(r.ref, (r.lightmap_index, r.lightmap_scale_offset))
        if index >= NO_LIGHTMAP or index >= len(slots):
            continue
        if store.resolve(settings[0], slots[index].get("m_Lightmap")) is None:
            continue
        uv_sets = meshes.uv_sets(r.mesh)
        uv = 1 if "uv1" in uv_sets else 0 if "uv0" in uv_sets else None
        if uv is None:
            continue
        assignments.append({"node": i, "lightmap": int(index), "scale_offset": [shortest32(v) for v in so], "uv": uv})
        used.add(index)
    if not assignments:
        return None
    directional = s.get("m_LightmapsMode") == DIRECTIONAL
    lightmaps = []
    for index in sorted(used):
        slot = slots[index]
        color = store.resolve(settings[0], slot["m_Lightmap"])
        entry = {"index": int(index), "color": textures.lightmap_color(store, color, graph.game)}
        if directional:
            direction = store.resolve(settings[0], slot.get("m_DirLightmap"))
            if direction is None:
                raise Unsupported(f"lightmap {index} has no direction lightmap in a directional Map")
            entry["direction"] = textures.lightmap_direction(store, direction)
        lightmaps.append(entry)
    out = {"id": SET_ID, "mode": "directional" if directional else "non_directional"}
    if directional:
        out["direction_space"] = "world"
    return {**out, "lightmaps": lightmaps, "assignments": assignments}
