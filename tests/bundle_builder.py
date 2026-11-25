"""Writes small, valid Map Bundles for tests, so they go through the real check.

    b = MapBundleBuilder()                     # the default Map: see _default_map
    b.nodes[4]["translation"] = [0.0, 1.0, 0.0]  # change the symbolic content before building
    path = b.build(tmp_path)                   # writes <tmp_path>/<name>/ and returns it
    edit_json(path, "scene", lambda d: d["nodes"].pop())   # break it after building

Content is symbolic until `build`: nodes name meshes and materials, and materials and the lighting
name textures, by short keys, which `build` turns into Content Hashes. The mesh, PNG and EXR files
are real: the EXRs are half-float, ZIP-compressed scanline files. Standard library only.
"""

from __future__ import annotations

import copy
import json
import struct
import zlib
from pathlib import Path

from bundle import SCHEMA_VERSION, hashing

ATTRIBUTE_FLOATS = {"position": 3, "normal": 3, "uv0": 2, "uv1": 2}
IDENTITY = [1.0, 0.0, 0.0, 0.0]


# --- files -----------------------------------------------------------------------------

def png_bytes(width: int, height: int, channels: int, pixels: bytes) -> bytes:
    """An 8-bit PNG; `pixels` interleaved, rows top first."""
    color_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    row = width * channels
    raw = b"".join(b"\0" + pixels[y * row:(y + 1) * row] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def exr_bytes(width: int, height: int, channels: int, values: list[float]) -> bytes:
    """A half-float, ZIP-compressed scanline OpenEXR; `values` interleaved R, G, B(, A), rows top first."""
    names = ["R", "G", "B", "A"][:channels]
    order = sorted(range(channels), key=lambda c: names[c])  # EXR stores channels by name

    def attribute(name: str, kind: str, data: bytes) -> bytes:
        return name.encode() + b"\0" + kind.encode() + b"\0" + struct.pack("<i", len(data)) + data

    chlist = b"".join(names[c].encode() + b"\0" + struct.pack("<iB3xii", 1, 0, 1, 1) for c in order) + b"\0"
    box = struct.pack("<iiii", 0, 0, width - 1, height - 1)
    header = (struct.pack("<ii", 20000630, 2)
              + attribute("channels", "chlist", chlist)
              + attribute("compression", "compression", bytes([3]))
              + attribute("dataWindow", "box2i", box)
              + attribute("displayWindow", "box2i", box)
              + attribute("lineOrder", "lineOrder", bytes([0]))
              + attribute("pixelAspectRatio", "float", struct.pack("<f", 1.0))
              + attribute("screenWindowCenter", "v2f", struct.pack("<ff", 0.0, 0.0))
              + attribute("screenWindowWidth", "float", struct.pack("<f", 1.0))
              + b"\0")
    blocks = []
    for y0 in range(0, height, 16):
        raw = bytearray()
        for y in range(y0, min(y0 + 16, height)):
            for c in order:
                raw += b"".join(struct.pack("<e", values[(y * width + x) * channels + c]) for x in range(width))
        blocks.append((y0, _exr_zip(bytes(raw))))
    offset = len(header) + 8 * len(blocks)
    table, body = bytearray(), bytearray()
    for y0, data in blocks:
        table += struct.pack("<Q", offset + len(body))
        body += struct.pack("<ii", y0, len(data)) + data
    return header + bytes(table) + bytes(body)


def _exr_zip(raw: bytes) -> bytes:
    """OpenEXR's ZIP compression: split even and odd bytes, delta-encode, deflate."""
    split = raw[0::2] + raw[1::2]
    delta = bytearray(split[:1])
    for i in range(1, len(split)):
        delta.append((split[i] - split[i - 1] + 128 + 256) & 0xFF)
    packed = zlib.compress(bytes(delta))
    return packed if len(packed) < len(raw) else raw


def mesh_bytes(attributes: dict[str, list], submeshes: list[list[int]]) -> bytes:
    """A mesh file: each attribute's floats in turn, then every submesh's uint32 indices."""
    out = bytearray()
    for name, values in attributes.items():
        for vertex in values:
            out += struct.pack(f"<{ATTRIBUTE_FLOATS[name]}f", *vertex)
    for indices in submeshes:
        out += struct.pack(f"<{len(indices)}I", *indices)
    return bytes(out)


# --- the builder -----------------------------------------------------------------------

class MapBundleBuilder:
    def __init__(self, game: str = "KK", key: str = "map/scene/test"):
        self.game = game
        self.key = key
        self.extracted_at = "2026-11-22T12:00:00Z"
        self.textures: dict[str, dict] = {}
        self.materials: dict[str, dict] = {}
        self.meshes: dict[str, dict] = {}
        self.nodes: list[dict] = []
        self.map: dict = {}
        self.lightmap_sets: list[dict] = []
        self.variants: list[dict] = []
        self.candidates: list[dict] = []
        self._default_map()

    # --- building blocks ---------------------------------------------------------------

    def add_texture(self, key, width, height, channels, *, fmt="png", color_space="srgb", name=None, fill=None):
        """A texture of a flat colour (`fill`, one value per channel; by default made from the key)."""
        if fill is None:
            seed = zlib.crc32(key.encode())
            fill = [((seed >> (8 * c)) & 0xFF) / 255.0 for c in range(channels)]
        self.textures[key] = {"name": name or key, "format": fmt, "width": width, "height": height,
                              "channels": channels, "color_space": color_space, "fill": list(fill),
                              "wrap": ["repeat", "repeat"], "filter": "bilinear"}

    def add_material(self, key, textures, *, shader="Standard", blend_mode="opaque", keywords=()):
        """A material; `textures` maps Raw Property to (texture key, Texture Role or None)."""
        self.materials[key] = {
            "name": key, "shader": shader, "keywords": sorted(keywords), "render_queue": 2000,
            "blend_mode": blend_mode, "double_sided": False,
            "colors": {"_Color": [1.0, 1.0, 1.0, 1.0]}, "floats": {"_Glossiness": 0.5}, "vectors": {},
            "textures": [dict({"raw": raw, "texture": tex, "offset": [0.0, 0.0], "scale": [1.0, 1.0]},
                              **({"role": role} if role else {})) for raw, (tex, role) in textures.items()],
        }

    def add_mesh(self, key, attributes, submeshes, name=None):
        self.meshes[key] = {"name": name or key, "attributes": attributes, "submeshes": submeshes}

    def add_node(self, name, parent, *, mesh=None, draws=(), translation=(0.0, 0.0, 0.0), rotation=IDENTITY,
                 scale=(1.0, 1.0, 1.0), sky=False) -> int:
        """A node; `draws` are (submesh, material key) pairs. Returns its id."""
        node = {"id": len(self.nodes), "name": name, "parent": parent, "translation": list(translation),
                "rotation": list(rotation), "scale": list(scale)}
        if mesh:
            node["renderer"] = {"mesh": mesh, "draws": [{"submesh": s, "material": m} for s, m in draws],
                                "shadows": "on", "receive_shadows": True,
                                "realtime_gi": False, "reflection_probes": "blend_probes"}
        if sky:
            node["sky"] = True
        self.nodes.append(node)
        return node["id"]

    def variant(self, times_of_day, **changes) -> dict:
        """A Map Variant with plain light, no sky and no Grade; `changes` replace its fields."""
        v = {
            "id": times_of_day[0], "times_of_day": list(times_of_day), "hidden": [], "lightmap_set": None,
            "lights": [{"type": "directional", "rotation": IDENTITY, "color": [1.0, 0.95, 0.9, 1.0],
                        "intensity": 1.45, "shadows": "soft", "mode": "realtime"}],
            "ambient": {"mode": "flat", "intensity": 1.0, "sky_color": [0.212, 0.227, 0.259, 1.0]},
            "fog": {"enabled": True, "mode": "linear", "color": [0.294, 0.883, 1.0, 1.0], "start": 0.0,
                    "end": 500.0, "density": 0.01},
            "reflection": {"source": "skybox", "intensity": 1.0, "texture": None, "probes": []},
            "sky": None, "sun_shafts": None, "grade": None,
        }
        v.update(changes)
        return v

    def _default_map(self):
        """A small KK-like Map: a wall Structure with a vase Prop on it, two desks (one Prop placed
        twice), clouds shown by day, a directional Lightmap Set, and evening and night merged."""
        self.add_texture("wall_main", 4, 4, 3)
        self.add_texture("wall_normal", 4, 4, 3, color_space="linear", fill=[0.5, 0.5, 1.0])
        self.add_texture("desk_main", 4, 4, 4)
        self.add_texture("cloud_main", 4, 4, 4)
        self.add_texture("lightmap_0", 4, 4, 3, fmt="exr", color_space="linear", name="Lightmap-0_comp_light",
                         fill=[0.8, 0.7, 2.5])
        self.add_texture("lightmap_0_dir", 4, 4, 4, color_space="linear", name="Lightmap-0_comp_dir",
                         fill=[0.5, 0.5, 1.0, 0.8])
        self.add_texture("sky_day", 8, 4, 3, fmt="exr", color_space="linear", name="mt_koi_sky_hiru00",
                         fill=[0.4, 0.6, 1.0])
        self.add_texture("lut_day", 1024, 32, 3, color_space="linear", name="Lut_Amount")
        self.add_texture("lut_night", 1024, 32, 3, color_space="linear", name="Lut_TimeNight1")
        self.add_texture("thumbnail", 8, 4, 3)

        self.add_material("wall", {"_MainTex": ("wall_main", "main"), "_BumpMap": ("wall_normal", "normal")},
                          keywords=["_NORMALMAP"])
        self.add_material("desk", {"_MainTex": ("desk_main", "main")})
        self.add_material("cloud", {"_MainTex": ("cloud_main", "main"), "_EmissionMap": ("cloud_main", "emission")},
                          blend_mode="alpha", keywords=["_ALPHABLEND_ON", "_EMISSION"])

        quad = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 0.0, 1.0], [0.0, 0.0, 1.0]]
        up = [[0.0, -1.0, 0.0]] * 4
        uv = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        self.add_mesh("quad", {"position": quad, "normal": up, "uv0": uv, "uv1": uv}, [[0, 2, 1, 0, 3, 2]])
        self.add_mesh("slab", {"position": quad, "normal": up, "uv0": uv}, [[0, 2, 1], [0, 3, 2]], name="desk_top")

        root = self.add_node("Map", None)
        room = self.add_node("n_room", root)
        wall = self.add_node("mo_wall_00", room, mesh="quad", draws=[(0, "wall")], translation=(0.0, 5.0, 0.0))
        self.add_node("p_vase_00", wall, mesh="slab", draws=[(0, "desk"), (1, "desk")], translation=(0.5, -0.1, 1.0))
        desks = []
        for i, x in enumerate((-2.0, 2.0)):
            desk = self.add_node("p_desk_00" + (f" ({i})" if i else ""), room, translation=(x, 0.0, 0.0),
                                 rotation=[0.70710677, 0.0, 0.0, 0.70710677] if i else IDENTITY)
            self.add_node("desk_top", desk, mesh="slab", draws=[(0, "desk"), (1, "desk")], translation=(0.0, 0.0, 0.75))
            self.add_node("desk_leg", desk, mesh="quad", draws=[(0, "desk")], scale=(0.05, 0.05, 0.75))
            desks.append(desk)
        clouds = self.add_node("mo_koi_sky_kumo00", root, sky=True, translation=(0.0, 0.0, 300.0))
        self.add_node("kumo_plane", clouds, mesh="quad", draws=[(0, "cloud")], sky=True, scale=(400.0, 1.0, 400.0))

        self.map = {
            "key": self.key, "times_of_day": ["day", "evening", "night"], "outdoor": False, "camera": "game",
            "list_entries": [{"list": "map", "no": 3, "name": "テスト教室"}],
            "thumbnails": [{"times_of_day": ["day", "evening", "night"], "texture": "thumbnail"}],
            "skipped": [{"reason": "particles", "count": 2}],
        }
        self.lightmap_sets = [{
            "id": "scene", "mode": "directional", "direction_space": "world",
            "lightmaps": [{"index": 0, "color": "lightmap_0", "direction": "lightmap_0_dir"}],
            "assignments": [{"node": wall, "lightmap": 0, "scale_offset": [0.5, 0.5, 0.0, 0.0], "uv": 1},
                            {"node": desks[0] + 1, "lightmap": 0, "scale_offset": [0.25, 0.25, 0.5, 0.5], "uv": 0}],
        }]
        day_sky = {"kind": "cubemap", "source": "dome", "texture": "sky_day", "tint": [0.669, 0.669, 0.669, 1.0],
                   "exposure": 1.0, "rotation": 0.0, "geometry": [clouds]}
        self.variants = [
            self.variant(["day"], lightmap_set="scene", sky=day_sky, sun_shafts={"color": [0.838, 0.838, 0.838, 1.0]},
                         grade={"kind": "amplify_color", "lut": "lut_day", "layout": "amplify_32x32"}),
            self.variant(["evening", "night"], lightmap_set="scene", hidden=[clouds],
                         grade={"kind": "amplify_color", "lut": "lut_night", "layout": "amplify_32x32"}),
        ]
        self.candidates = [
            {"kind": "structure", "rule": "mo_prefix", "placements": [wall]},
            {"kind": "prop", "rule": "p_prefix", "placements": [wall + 1]},
            {"kind": "prop", "rule": "p_prefix", "placements": desks},
        ]

    # --- writing -----------------------------------------------------------------------

    def build(self, folder: Path, name: str = "test_map") -> Path:
        """Writes the bundle into `folder`/`name`, Manifest last, and returns its path."""
        root = Path(folder) / name
        (root / "meshes").mkdir(parents=True)
        (root / "textures").mkdir()

        tex_id, tex_records = {}, []
        for key, t in self.textures.items():
            n = t["width"] * t["height"]
            if t["format"] == "png":
                pixels = bytes(round(v * 255) for v in t["fill"]) * n
                data = png_bytes(t["width"], t["height"], t["channels"], pixels)
            else:
                values = [hashing.float32(v) for v in t["fill"]] * n
                pixels = b"".join(struct.pack("<e", v) for v in values)
                data = exr_bytes(t["width"], t["height"], t["channels"], values)
            tid = hashing.texture_hash(t["width"], t["height"], t["channels"], pixels)
            tex_id[key] = tid
            (root / "textures" / f"{tid}.{t['format']}").write_bytes(data)
            tex_records.append({"id": tid, "name": t["name"], "format": t["format"], "width": t["width"],
                                "height": t["height"], "color_space": t["color_space"], "wrap": t["wrap"],
                                "filter": t["filter"]})

        mat_id, mat_records = {}, []
        for key, m in self.materials.items():
            record = _shortest(copy.deepcopy(m))
            for t in record["textures"]:
                t["texture"] = tex_id.get(t["texture"], t["texture"])
            record = {"id": hashing.material_hash(record), **record}
            mat_id[key] = record["id"]
            mat_records.append(record)

        mesh_id, mesh_records = {}, []
        for key, m in self.meshes.items():
            data = mesh_bytes(m["attributes"], m["submeshes"])
            mid = hashing.digest(data)
            mesh_id[key] = mid
            (root / "meshes" / f"{mid}.bin").write_bytes(data)
            mesh_records.append({"id": mid, "name": m["name"], "vertices": len(m["attributes"]["position"]),
                                 "attributes": list(m["attributes"]), "index_counts": [len(s) for s in m["submeshes"]]})

        nodes = _shortest(copy.deepcopy(self.nodes))
        for n in nodes:
            r = n.get("renderer")
            if r:
                r["mesh"] = mesh_id.get(r["mesh"], r["mesh"])
                for d in r["draws"]:
                    d["material"] = mat_id.get(d["material"], d["material"])

        map_record = copy.deepcopy(self.map)
        for thumb in map_record["thumbnails"]:
            thumb["texture"] = tex_id.get(thumb["texture"], thumb["texture"])
        map_record["geometry_hash"] = hashing.geometry_hash(nodes)

        sets = copy.deepcopy(self.lightmap_sets)
        for s in sets:
            for lm in s["lightmaps"]:
                for field in ("color", "direction"):
                    if field in lm:
                        lm[field] = tex_id.get(lm[field], lm[field])

        variants = copy.deepcopy(self.variants)
        for v in variants:
            if v["sky"] and "texture" in v["sky"]:
                v["sky"]["texture"] = tex_id.get(v["sky"]["texture"], v["sky"]["texture"])
            if v["reflection"]["texture"]:
                v["reflection"]["texture"] = tex_id.get(v["reflection"]["texture"], v["reflection"]["texture"])
            for p in v["reflection"]["probes"]:
                p["texture"] = tex_id.get(p["texture"], p["texture"])
            if v["grade"]:
                v["grade"]["lut"] = tex_id.get(v["grade"]["lut"], v["grade"]["lut"])

        roots = {r for c in self.candidates for r in c["placements"]}
        shapes = hashing.candidate_shapes(nodes, roots)
        candidates = [{"hash": shapes[c["placements"][0]], **copy.deepcopy(c)} for c in self.candidates]

        files = {
            "map": map_record,
            "scene": {"nodes": nodes},
            "meshes": {"meshes": mesh_records},
            "materials": {"materials": mat_records},
            "textures": {"textures": tex_records},
            "lightmaps": {"sets": sets},
            "variants": {"variants": variants},
            "assets": {"candidates": candidates},
        }
        for stem, value in files.items():
            write_json(root, stem, value)
        write_json(root, "manifest", {
            "game": self.game, "schema_version": SCHEMA_VERSION,
            "extractor": {"name": "kkbp-maps test bundle builder", "version": "0"},
            "extracted_at": self.extracted_at, "map": self.key, "options": {"max_texture_size": None},
            "sources": [{"path": f"abdata/{self.key}.unity3d", "bytes": 1234, "sha256": "0" * 64}],
            "contents": {},
        })
        refresh_manifest(root)
        return root


# --- editing built bundles ---------------------------------------------------------------

def write_json(root: Path, stem: str, value):
    (root / f"{stem}.json").write_text(json.dumps(_shortest(value), ensure_ascii=False, indent=1) + "\n",
                                       encoding="utf-8", newline="\n")


def read_json(root: Path, stem: str):
    return json.loads((root / f"{stem}.json").read_text(encoding="utf-8"))


def edit_json(root: Path, stem: str, change, *, refresh: bool = True):
    """Changes a data file in place: `change(data)` edits it, and what it returns is ignored. Then brings
    the Manifest's contents up to date, unless `refresh` is False, so a test sees only the problem it made."""
    data = read_json(root, stem)
    change(data)
    write_json(root, stem, data)
    if refresh and stem != "manifest":
        refresh_manifest(root)


def refresh_manifest(root: Path):
    """Recounts the Manifest's contents from the data files and the folder."""
    m = read_json(root, "manifest")
    d = {stem: read_json(root, stem) for stem in ("scene", "meshes", "materials", "textures", "lightmaps",
                                                  "variants", "assets")}
    m["contents"] = {
        "nodes": len(d["scene"]["nodes"]), "meshes": len(d["meshes"]["meshes"]),
        "materials": len(d["materials"]["materials"]), "textures": len(d["textures"]["textures"]),
        "lightmap_sets": len(d["lightmaps"]["sets"]), "variants": len(d["variants"]["variants"]),
        "candidates": len(d["assets"]["candidates"]),
        "placements": sum(len(c["placements"]) for c in d["assets"]["candidates"]),
        "bytes": 0,
    }
    write_json(root, "manifest", m)  # the size of manifest.json doesn't count, so this is final
    m["contents"]["bytes"] = sum(p.stat().st_size for p in root.rglob("*")
                                 if p.is_file() and p.relative_to(root).as_posix() != "manifest.json")
    write_json(root, "manifest", m)


def _shortest(value):
    """Floats as the shortest decimal of their float32, as the Extractor writes them."""
    if isinstance(value, float):
        return hashing.shortest32(value)
    if isinstance(value, list):
        return [_shortest(v) for v in value]
    if isinstance(value, dict):
        return {k: _shortest(v) for k, v in value.items()}
    return value
