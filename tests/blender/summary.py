"""The summary of a built Map Library file, for the committed snapshots (ADR 0007): counts, names,
hashes and tags only, never positions, pixels or values. Runs inside Blender on a saved file:

    blender -b <file.blend> --python tests/blender/summary.py -- <out.json> <catalog file>

Node groups are compared by a structural fingerprint: a hash of their nodes, settings, links, and the
input values (rounded to 5 places) that differ from a fresh node of the same kind, so a change to a graph
shows without its values entering the snapshot, and a socket a newer Blender adds at its default doesn't.
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import bpy

PREFIX = "kkbp_maps_"


def catalogs(path: Path) -> dict:
    out = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#") and not line.startswith("VERSION"):
                uid, cat, _ = line.split(":", 2)
                out[uid] = cat
    return out


def _value(v):
    if isinstance(v, float):
        return round(v, 5) + 0.0
    if hasattr(v, "__len__") and not isinstance(v, str):
        try:
            return [_value(x) for x in v]
        except TypeError:
            return str(v)
    if isinstance(v, bpy.types.ID):
        return v.get(PREFIX + "hash") or v.name
    return v


SETTINGS = ("operation", "data_type", "blend_type", "interpolation", "extension", "attribute_type", "attribute_name",
            "uv_map", "target", "use_clamp", "clamp_factor", "vector_type")


_fresh = {}


def _fresh_inputs(n) -> dict:
    """The input defaults of a new node of n's kind and settings (which decide its sockets)."""
    settings = tuple((k, str(getattr(n, k))) for k in SETTINGS if hasattr(n, k))
    key = (n.bl_idname, settings)
    if key not in _fresh:
        tree = bpy.data.node_groups.new(".fresh", "ShaderNodeTree")
        ref = tree.nodes.new(n.bl_idname)
        for k in SETTINGS:
            if hasattr(n, k) and k != "attribute_name":
                try:
                    setattr(ref, k, getattr(n, k))
                except (AttributeError, TypeError):
                    pass
        _fresh[key] = {s.identifier: _value(s.default_value) for s in ref.inputs if hasattr(s, "default_value")}
        bpy.data.node_groups.remove(tree)
    return _fresh[key]


def fingerprint(tree) -> str:
    nodes = []
    for n in tree.nodes:
        entry = [n.name, n.bl_idname]
        fresh = _fresh_inputs(n)
        entry += [(k, _value(getattr(n, k))) for k in SETTINGS if hasattr(n, k)]
        if getattr(n, "image", None) is not None:
            entry.append(("image", _value(n.image)))
        if getattr(n, "node_tree", None) is not None:
            entry.append(("group", n.node_tree.name))
        entry += [(s.identifier, _value(s.default_value)) for s in n.inputs
                  if not s.is_linked and hasattr(s, "default_value")
                  and (s.identifier not in fresh or _value(s.default_value) != fresh[s.identifier])]
        if n.bl_idname in ("ShaderNodeValue", "ShaderNodeRGB"):
            entry.append(("out", _value(n.outputs[0].default_value)))
        nodes.append(entry)
    links = sorted((l.from_node.name, l.from_socket.identifier, l.to_node.name, l.to_socket.identifier)
                   for l in tree.links)
    interface = [(i.name, getattr(i, "socket_type", ""), getattr(i, "in_out", "")) for i in tree.interface.items_tree]
    data = json.dumps([nodes, links, interface], sort_keys=True, default=str)
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def asset(idb, cats):
    a = idb.asset_data
    return {
        "type": type(idb).__name__,
        "catalog": cats.get(a.catalog_id, f"<unknown {a.catalog_id}>"),
        "tags": [t.name for t in a.tags],
        "preview": bool(idb.preview and idb.preview.image_size[0]),
    }


def collection(c):
    objs = list(c.all_objects)
    types = Counter(o.type for o in objs)
    meshes = [o for o in objs if o.type == "MESH"]
    slots = Counter()
    for o in meshes:
        for s in o.material_slots:
            slots["left out" if s.material and s.material.get(PREFIX + "left_out") else
                  "material" if s.material else "empty"] += 1
    return {
        "objects": dict(sorted(types.items())),
        "placements": sum(1 for o in objs if PREFIX + "asset" in o),
        "lightmapped": sum(1 for o in meshes if o.get(PREFIX + "lightmap_tile", 0) > 0),
        "in_probe": sum(1 for o in meshes if o.get(PREFIX + "reflection_probe", 0) > 0),
        "no_shadow": sum(1 for o in meshes if not o.visible_shadow),
        "slots": dict(sorted(slots.items())),
        "meshes": sorted({o.data[PREFIX + "hash"] for o in meshes}),
    }


def summarize(cats: dict) -> dict:
    trees = list(bpy.data.node_groups)  # fingerprint() adds and removes a scratch group as it goes
    groups = {g.name: fingerprint(g) for g in trees if not g.get(PREFIX + "hash")}
    base = sorted((g[PREFIX + "hash"], g.get(PREFIX + "tier", ""), fingerprint(g)) for g in trees
                  if g.get(PREFIX + "hash"))
    images = []
    for i in bpy.data.images:
        if i.source == "TILED":
            images.append({"name": i.name, "colorspace": i.colorspace_settings.name,
                           "tiles": [[t.number, list(t.size)] for t in i.tiles]})
        else:
            images.append({"name": i.get(PREFIX + "hash", i.name), "colorspace": i.colorspace_settings.name,
                           "relative": i.filepath.startswith("//")})
    return {
        "scene": {"engine": bpy.context.scene.render.engine, "view_transform": bpy.context.scene.view_settings.view_transform,
                  "world": bpy.context.scene.world.name if bpy.context.scene.world else None},
        "assets": {f"{type(idb).__name__} {idb.name}": asset(idb, cats)
                   for idb in list(bpy.data.collections) + list(bpy.data.worlds) if idb.asset_data},
        "collections": {c.name: collection(c) for c in bpy.data.collections},
        "worlds": {w.name: {"sky": w.get(PREFIX + "sky"), "fingerprint": fingerprint(w.node_tree)}
                   for w in list(bpy.data.worlds)},
        "lights": sorted(f"{l.type} shadow={l.use_shadow}" for l in bpy.data.lights),
        "counts": {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials),
                   "node_groups": len(bpy.data.node_groups), "images": len(bpy.data.images)},
        "meshes": sorted(m[PREFIX + "hash"] for m in bpy.data.meshes if PREFIX + "hash" in m),
        "materials": sorted(Counter(m.get(PREFIX + "hash", m.name) for m in bpy.data.materials).items()),
        "base_materials": base,
        "groups": dict(sorted(groups.items())),
        "images": sorted(images, key=lambda x: x["name"]),
    }


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:]
    out = Path(args[0])
    out.write_text(json.dumps(summarize(catalogs(Path(args[1]))), indent=1, sort_keys=True) + "\n", encoding="utf-8")
