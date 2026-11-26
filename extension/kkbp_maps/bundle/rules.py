"""The contract rules the schemas can't express (README, "Rules the schemas can't express").

Runs on files that already passed their schemas, so every field has its type.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from array import array
from collections import Counter
from pathlib import Path

from . import hashing, images

DATA_FILES = ("manifest", "map", "scene", "meshes", "materials", "textures", "lightmaps", "variants", "assets")
FLOATS_PER_ATTRIBUTE = {"position": 3, "normal": 3, "uv0": 2, "uv1": 2}


def check(root: Path, d: dict, sets: dict, deep: bool) -> list[str]:
    """Every rule problem in a bundle. `d` maps each data file's stem to its parsed JSON; `sets` maps a
    closed set's name to its values in order."""
    c = _Context(root, d, sets)
    c.meshes()
    c.textures()
    c.materials()
    tree_ok = c.nodes()
    c.map(tree_ok)
    c.lightmaps()
    c.variants()
    c.assets(tree_ok)
    c.use()
    c.manifest()
    if deep:
        c.deep_meshes()
    return c.problems


class _Context:
    def __init__(self, root, d, sets):
        self.root = root
        self.d = d
        self.sets = sets
        self.problems: list[str] = []
        self.nodes_ = d["scene"]["nodes"]
        self.mesh = {m["id"]: m for m in d["meshes"]["meshes"]}
        self.material = {m["id"]: m for m in d["materials"]["materials"]}
        self.texture = {t["id"]: t for t in d["textures"]["textures"]}
        self.lightmap_set = {s["id"]: s for s in d["lightmaps"]["sets"]}
        self.used_textures: set[str] = set()

    def add(self, file: str, message: str):
        self.problems.append(f"{file}.json: {message}")

    def unique(self, file: str, what: str, values):
        for value, n in Counter(values).items():
            if n > 1:
                self.add(file, f"{what} {value} appears {n} times")

    def ordered(self, file: str, where: str, values, set_name: str):
        """A list of set values in the set's order, each once."""
        order = self.sets[set_name]
        positions = [order.index(v) for v in values]
        if positions != sorted(set(positions)):
            self.add(file, f"{where} {values} should name each value once, in the order {order}")

    def node_exists(self, file: str, where: str, node: int) -> bool:
        if node >= len(self.nodes_):
            self.add(file, f"{where} names node {node}, which doesn't exist")
            return False
        return True

    def texture_of(self, file: str, where: str, tid: str, fmt=None, color_space=None, size=None):
        """A texture reference: it exists, and is of the format, colour space and size it must be."""
        self.used_textures.add(tid)
        t = self.texture.get(tid)
        if t is None:
            self.add(file, f"{where} names texture {tid}, which doesn't exist")
            return None
        if fmt and t["format"] != fmt:
            self.add(file, f"{where} names texture {tid}, a {t['format']}; it should be a {fmt}")
        if color_space and t["color_space"] != color_space:
            self.add(file, f"{where} names texture {tid}, which is {t['color_space']}; it should be {color_space}")
        if size and (t["width"], t["height"]) != size:
            self.add(file, f"{where} names texture {tid} of {t['width']} × {t['height']}; it should be {size[0]} × {size[1]}")
        return t

    # --- meshes, textures, materials ------------------------------------------------------

    def meshes(self):
        self.unique("meshes", "mesh", (m["id"] for m in self.d["meshes"]["meshes"]))
        for m in self.mesh.values():
            where = f"mesh {m['id']}"
            if m["attributes"][:2] != ["position", "normal"]:
                self.add("meshes", f"{where}: its attributes should start with position and normal")
            self.ordered("meshes", f"{where}: attributes", m["attributes"], "mesh-attribute")
            for i, n in enumerate(m["index_counts"]):
                if n % 3:
                    self.add("meshes", f"{where}: submesh {i} has {n} indices, not a multiple of 3")
            path = self.root / "meshes" / f"{m['id']}.bin"
            if not path.is_file():
                self.add("meshes", f"{where}: meshes/{m['id']}.bin is missing")
                continue
            expected = 4 * (m["vertices"] * sum(FLOATS_PER_ATTRIBUTE[a] for a in m["attributes"])
                            + sum(m["index_counts"]))
            if path.stat().st_size != expected:
                self.add("meshes", f"{where}: meshes/{m['id']}.bin is {path.stat().st_size} bytes; its record says {expected}")

    def deep_meshes(self):
        for m in self.mesh.values():
            path = self.root / "meshes" / f"{m['id']}.bin"
            if not path.is_file():
                continue
            data = path.read_bytes()
            if hashing.digest(data) != m["id"]:
                self.add("meshes", f"mesh {m['id']}: its file's hash is {hashing.digest(data)}")
            start = 4 * m["vertices"] * sum(FLOATS_PER_ATTRIBUTE.get(a, 0) for a in m["attributes"])
            indices = array("I")
            if indices.itemsize != 4:  # not on any supported platform, but array's sizes aren't fixed
                indices = array("L")
            tail = data[start:]
            indices.frombytes(tail[:len(tail) - len(tail) % 4])
            if sys.byteorder == "big":
                indices.byteswap()
            if indices and max(indices) >= m["vertices"]:
                self.add("meshes", f"mesh {m['id']}: index {max(indices)} is beyond its {m['vertices']} vertices")

    def textures(self):
        self.unique("textures", "texture", (t["id"] for t in self.d["textures"]["textures"]))
        for t in self.texture.values():
            name = f"textures/{t['id']}.{t['format']}"
            where = f"texture {t['id']}"
            if t["format"] == "exr" and t["color_space"] != "linear":
                self.add("textures", f"{where}: an EXR is linear, not {t['color_space']}")
            path = self.root / name
            if not path.is_file():
                self.add("textures", f"{where}: {name} is missing")
                continue
            try:
                header = (images.png_header if t["format"] == "png" else images.exr_header)(path)
            except (OSError, ValueError, struct.error) as ex:
                self.add("textures", f"{where}: {name} {ex}")
                continue
            for problem in header.problems:
                self.add("textures", f"{where}: {name} {problem}")
            if (header.width, header.height) != (t["width"], t["height"]):
                self.add("textures", f"{where}: {name} is {header.width} × {header.height}; "
                                     f"its record says {t['width']} × {t['height']}")

    def materials(self):
        self.unique("materials", "material", (m["id"] for m in self.d["materials"]["materials"]))
        for m in self.material.values():
            where = f"material {m['id']}"
            if hashing.material_hash(m) != m["id"]:
                self.add("materials", f"{where}: its Content Hash is {hashing.material_hash(m)}")
            if m["keywords"] != sorted(set(m["keywords"])):
                self.add("materials", f"{where}: keywords should be sorted, each once")
            self.unique("materials", f"{where}: Raw Property", (t["raw"] for t in m["textures"]))
            self.unique("materials", f"{where}: Texture Role", (t["role"] for t in m["textures"] if "role" in t))
            for t in m["textures"]:
                self.texture_of("materials", f"{where}: {t['raw']}", t["texture"])

    # --- nodes and the Map ----------------------------------------------------------------

    def nodes(self) -> bool:
        """Checks the nodes, and says whether the tree is sound enough to hash."""
        tree_ok = True
        for i, n in enumerate(self.nodes_):
            where = f"node {i}"
            if n["id"] != i:
                self.add("scene", f"{where} has id {n['id']}; a node's id is its position in the list")
                tree_ok = False
            if n["parent"] is not None and n["parent"] >= i:
                self.add("scene", f"{where} has parent {n['parent']}, which doesn't come before it")
                tree_ok = False
            if abs(math.sqrt(sum(q * q for q in n["rotation"])) - 1) > 1e-3:
                self.add("scene", f"{where}: rotation {n['rotation']} isn't a unit quaternion")
            if 0 in n["scale"]:
                self.add("scene", f"{where}: scale {n['scale']} has a 0")
            r = n.get("renderer")
            if r:
                mesh = self.mesh.get(r["mesh"])
                if mesh is None:
                    self.add("scene", f"{where}: mesh {r['mesh']} doesn't exist")
                for draw in r["draws"]:
                    if draw["material"] not in self.material:
                        self.add("scene", f"{where}: material {draw['material']} doesn't exist")
                    if mesh and draw["submesh"] >= len(mesh["index_counts"]):
                        self.add("scene", f"{where}: draws submesh {draw['submesh']}, but its mesh has "
                                          f"{len(mesh['index_counts'])}")
            if tree_ok and n["parent"] is not None and self.nodes_[n["parent"]].get("sky") and not n.get("sky"):
                self.add("scene", f"{where} is a child of sky node {n['parent']} but not a sky node")
        return tree_ok

    def map(self, tree_ok: bool):
        m = self.d["map"]
        self.ordered("map", "times_of_day", m["times_of_day"], "time-of-day")
        seen = Counter()
        for i, thumb in enumerate(m["thumbnails"]):
            self.ordered("map", f"thumbnail {i}: times_of_day", thumb["times_of_day"], "time-of-day")
            for tod in thumb["times_of_day"]:
                seen[tod] += 1
                if tod not in m["times_of_day"]:
                    self.add("map", f"thumbnail {i} is for {tod}, which the Map doesn't have")
            self.texture_of("map", f"thumbnail {i}", thumb["texture"], fmt="png")
        for tod, n in seen.items():
            if n > 1:
                self.add("map", f"{n} thumbnails are for {tod}")
        self.unique("map", "list entry", (f"{e['list']} {e['no']}" for e in m["list_entries"]))
        self.unique("map", "skip reason", (s["reason"] for s in m["skipped"]))
        if tree_ok and hashing.geometry_hash(self.nodes_) != m["geometry_hash"]:
            self.add("map", f"geometry_hash should be {hashing.geometry_hash(self.nodes_)}")

    # --- light ----------------------------------------------------------------------------

    def lightmaps(self):
        self.unique("lightmaps", "Lightmap Set", (s["id"] for s in self.d["lightmaps"]["sets"]))
        for s in self.lightmap_set.values():
            where = f"Lightmap Set {s['id']}"
            self.unique("lightmaps", f"{where}: lightmap", (lm["index"] for lm in s["lightmaps"]))
            indices = {lm["index"] for lm in s["lightmaps"]}
            for lm in s["lightmaps"]:
                at = f"{where}: lightmap {lm['index']}"
                color = self.texture_of("lightmaps", f"{at}: color", lm["color"], fmt="exr")
                if "direction" in lm:
                    size = (color["width"], color["height"]) if color else None
                    self.texture_of("lightmaps", f"{at}: direction", lm["direction"], fmt="png",
                                    color_space="linear", size=size)
            self.unique("lightmaps", f"{where}: assignment for node", (a["node"] for a in s["assignments"]))
            for a in s["assignments"]:
                at = f"{where}: node {a['node']}"
                if not self.node_exists("lightmaps", at, a["node"]):
                    continue
                node = self.nodes_[a["node"]]
                if "renderer" not in node or node.get("sky"):
                    self.add("lightmaps", f"{at} has no renderer or is a sky node")
                    continue
                if a["lightmap"] not in indices:
                    self.add("lightmaps", f"{at} uses lightmap {a['lightmap']}, which the set doesn't have")
                mesh = self.mesh.get(node["renderer"]["mesh"])
                if mesh and f"uv{a['uv']}" not in mesh["attributes"]:
                    self.add("lightmaps", f"{at} uses uv{a['uv']}, which its mesh doesn't have")

    def variants(self):
        variants = self.d["variants"]["variants"]
        times = self.d["map"]["times_of_day"]
        covered = Counter()
        for v in variants:
            where = f"Map Variant {v['id']}"
            self.ordered("variants", f"{where}: times_of_day", v["times_of_day"], "time-of-day")
            covered.update(v["times_of_day"])
            if v["id"] != v["times_of_day"][0]:
                self.add("variants", f"{where}: its id should be its first Time of Day, {v['times_of_day'][0]}")
            for tod in v["times_of_day"]:
                if tod not in times:
                    self.add("variants", f"{where} covers {tod}, which the Map doesn't have")
            if v["hidden"] != sorted(set(v["hidden"])):
                self.add("variants", f"{where}: hidden should be sorted, each node once")
            hidden = {h for h in v["hidden"] if self.node_exists("variants", f"{where}: hidden", h)}
            if v["lightmap_set"] is not None and v["lightmap_set"] not in self.lightmap_set:
                self.add("variants", f"{where}: Lightmap Set {v['lightmap_set']} doesn't exist")
            sky = v["sky"]
            if sky:
                for g in sky["geometry"]:
                    if not self.node_exists("variants", f"{where}: sky geometry", g):
                        continue
                    if not self.nodes_[g].get("sky"):
                        self.add("variants", f"{where}: sky geometry node {g} isn't a sky node")
                    if any(a in hidden for a in self._ancestry(g)):
                        self.add("variants", f"{where}: hides its own sky geometry node {g}")
                if sky["kind"] == "cubemap":
                    self.texture_of("variants", f"{where}: sky", sky["texture"], fmt="exr")
            r = v["reflection"]
            if r["texture"] is not None:
                self.texture_of("variants", f"{where}: reflection", r["texture"], fmt="exr")
            for i, probe in enumerate(r["probes"]):
                self.texture_of("variants", f"{where}: probe {i}", probe["texture"], fmt="exr")
            if v["grade"]:
                self.texture_of("variants", f"{where}: Grade LUT", v["grade"]["lut"], fmt="png",
                                color_space="linear", size=(1024, 32))
                blend = v["grade"].get("blend")
                if blend:
                    self.texture_of("variants", f"{where}: Grade blend LUT", blend["lut"], fmt="png",
                                    color_space="linear", size=(1024, 32))
                    if blend["amount"] == 0:
                        self.add("variants", f"{where}: a Grade blend of amount 0 should be left out")
        for tod in times:
            if covered[tod] != 1:
                self.add("variants", f"{tod} is covered by {covered[tod]} Map Variants; it should be by exactly one")
        lighting = [json.dumps(_numbers_as_floats({k: x for k, x in v.items() if k not in ("id", "times_of_day")}),
                               sort_keys=True) for v in variants]
        for v, key in zip(variants, lighting):
            if lighting.count(key) > 1:
                self.add("variants", f"Map Variant {v['id']} lights the Map the same as another; they should be one")
        shown = {g for v in variants if v["sky"] for g in v["sky"]["geometry"] if g < len(self.nodes_)}
        for n in self.nodes_:
            if n.get("sky") and "renderer" in n and not shown.intersection(self._ancestry(n["id"])):
                self.add("variants", f"sky node {n['id']} isn't in any Map Variant's sky geometry")

    def _ancestry(self, node: int):
        """The node and its ancestors."""
        seen = set()
        while node is not None and node not in seen and node < len(self.nodes_):
            seen.add(node)
            yield node
            node = self.nodes_[node]["parent"]

    # --- Candidates and Placements ----------------------------------------------------------

    def assets(self, tree_ok: bool):
        candidates = self.d["assets"]["candidates"]
        self.unique("assets", "Candidate", (c["hash"] for c in candidates))
        kind_of_root = {}
        for c in candidates:
            if (c["rule"] == "p_prefix") != (c["kind"] == "prop"):
                self.add("assets", f"Candidate {c['hash']}: rule {c['rule']} makes a "
                                   f"{'prop' if c['rule'] == 'p_prefix' else 'structure'}, not a {c['kind']}")
            for root in c["placements"]:
                if not self.node_exists("assets", f"Candidate {c['hash']}: Placement", root):
                    continue
                if self.nodes_[root].get("sky"):
                    self.add("assets", f"Candidate {c['hash']}: Placement root {root} is a sky node")
                if root in kind_of_root:
                    self.add("assets", f"node {root} roots more than one Placement")
                kind_of_root[root] = c["kind"]
        if not tree_ok:
            return
        for root, kind in kind_of_root.items():
            for a in list(self._ancestry(root))[1:]:
                outer = kind_of_root.get(a)
                if outer == "prop" or (outer == "structure" and kind == "structure"):
                    self.add("assets", f"the {kind} Placement at node {root} lies inside the {outer} Placement at node {a}")
        for n in self.nodes_:
            if "renderer" in n and not n.get("sky") and n["renderer"]["shadows"] != "shadows_only" \
                    and not any(a in kind_of_root for a in self._ancestry(n["id"])):
                self.add("assets", f"node {n['id']} has a renderer but belongs to no Placement")
        shapes = hashing.candidate_shapes(self.nodes_, set(kind_of_root))
        for c in candidates:
            for root in c["placements"]:
                if root < len(self.nodes_) and shapes[root] != c["hash"]:
                    self.add("assets", f"Candidate {c['hash']}: the Placement at node {root} has shape {shapes[root]}")

    # --- use and the Manifest ---------------------------------------------------------------

    def use(self):
        used_meshes = {n["renderer"]["mesh"] for n in self.nodes_ if "renderer" in n}
        used_materials = {d["material"] for n in self.nodes_ if "renderer" in n for d in n["renderer"]["draws"]}
        for m in sorted(set(self.mesh) - used_meshes):
            self.add("meshes", f"mesh {m} isn't used by any renderer")
        for m in sorted(set(self.material) - used_materials):
            self.add("materials", f"material {m} isn't used by any renderer")
        for t in sorted(set(self.texture) - self.used_textures):
            self.add("textures", f"texture {t} isn't used by anything")
        used_sets = {v["lightmap_set"] for v in self.d["variants"]["variants"]}
        for s in sorted(set(self.lightmap_set) - used_sets):
            self.add("lightmaps", f"Lightmap Set {s} isn't used by any Map Variant")

    def manifest(self):
        m = self.d["manifest"]
        if m["map"] != self.d["map"]["key"]:
            self.add("manifest", f"map {m['map']} isn't map.json's key {self.d['map']['key']}")
        self.unique("manifest", "source", (s["path"] for s in m["sources"]))
        counts = {
            "nodes": len(self.nodes_),
            "meshes": len(self.d["meshes"]["meshes"]),
            "materials": len(self.d["materials"]["materials"]),
            "textures": len(self.d["textures"]["textures"]),
            "lightmap_sets": len(self.d["lightmaps"]["sets"]),
            "variants": len(self.d["variants"]["variants"]),
            "candidates": len(self.d["assets"]["candidates"]),
            "placements": sum(len(c["placements"]) for c in self.d["assets"]["candidates"]),
        }
        allowed = {f"{name}.json" for name in DATA_FILES}
        allowed |= {f"meshes/{i}.bin" for i in self.mesh}
        allowed |= {f"textures/{t['id']}.{t['format']}" for t in self.texture.values()}
        total = 0
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(self.root).as_posix()
            if rel not in allowed:
                self.add("manifest", f"{rel} doesn't belong in the bundle")
            if rel != "manifest.json":
                total += path.stat().st_size
        counts["bytes"] = total
        for key, actual in counts.items():
            if m["contents"][key] != actual:
                self.add("manifest", f"contents.{key} is {m['contents'][key]}; the bundle has {actual}")


def _numbers_as_floats(value):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value) + 0.0
    if isinstance(value, list):
        return [_numbers_as_floats(v) for v in value]
    return {k: _numbers_as_floats(v) for k, v in value.items()}

