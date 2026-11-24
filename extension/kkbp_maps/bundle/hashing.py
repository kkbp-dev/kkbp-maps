"""The Content Hashes and the float32 number rule of the contract (README, "Content Hashes", "Conventions").

The Extractor hashes with these functions and the checker re-computes with them, so the definitions
live in one place.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct

TEXTURE_HEADER = b"kkbp-maps texture\0"


# --- numbers ---------------------------------------------------------------------------

def float32(x: float) -> float:
    """x rounded to the nearest float32. Raises OverflowError beyond float32's range."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def shortest32(x: float) -> float:
    """The float32 nearest to x, as the float of its shortest round-trip decimal: what a bundle writes."""
    v = float32(x)
    if not math.isfinite(v):
        raise OverflowError(f"{x!r} isn't a finite float32")
    for digits in range(1, 10):
        candidate = float(format(v, f".{digits}g"))
        if float32(candidate) == v:
            return candidate
    return float(repr(v))  # not reached: 9 significant digits always round-trip a float32


def is_shortest32(text: str) -> bool:
    """Whether a JSON number's text is a float32 written as its shortest round-trip decimal."""
    try:
        x = float(text)
        return math.isfinite(x) and shortest32(x) == x
    except (OverflowError, ValueError):
        return False


# --- hashing ---------------------------------------------------------------------------

def digest(data: bytes) -> str:
    """H(x): the first 32 hex digits of the SHA-256 of `data`."""
    return hashlib.sha256(data).hexdigest()[:32]


def canonical(value) -> bytes:
    """C(v): the canonical JSON of a value whose number fields the caller has already made floats."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def json_hash(value) -> str:
    return digest(canonical(value))


def _f(x) -> float:
    return float(x) + 0.0  # an int becomes a float, and -0.0 becomes 0.0


def _fs(xs) -> list[float]:
    return [_f(x) for x in xs]


def texture_hash(width: int, height: int, channels: int, pixels: bytes) -> str:
    """A texture's Content Hash, from its full-size pixels as its file holds them, rows top first."""
    return digest(TEXTURE_HEADER + struct.pack("<III", width, height, channels) + pixels)


def material_hash(material: dict) -> str:
    """A material's Content Hash, from its record in materials.json."""
    return json_hash({
        "shader": material["shader"],
        "keywords": list(material["keywords"]),
        "render_queue": int(material["render_queue"]),
        "colors": {k: _fs(v) for k, v in material["colors"].items()},
        "floats": {k: _f(v) for k, v in material["floats"].items()},
        "vectors": {k: _fs(v) for k, v in material["vectors"].items()},
        "textures": sorted(({"raw": t["raw"], "texture": t["texture"], "offset": _fs(t["offset"]),
                             "scale": _fs(t["scale"])} for t in material["textures"]), key=lambda t: t["raw"]),
    })


def tree_hashes(nodes: list[dict], cut=lambda node: False) -> tuple[list[str], list[str]]:
    """The shape and placed hash of every node of scene.json's `nodes`, as two lists by node id.

    `cut(child)` says whether a child is left out of its parent's parts: for Candidates, sky nodes and
    the roots of other Placements; for the geometry hash, nothing. Parents come before their children,
    so walking the list backwards meets every child before its parent.
    """
    parts: list[list[str]] = [[] for _ in nodes]
    shape = [""] * len(nodes)
    placed = [""] * len(nodes)
    for node in reversed(nodes):
        i = node["id"]
        renderer = node.get("renderer")
        record = {
            "mesh": renderer["mesh"] if renderer else None,
            "draws": [[int(d["submesh"]), d["material"]] for d in renderer["draws"]] if renderer else [],
            "parts": sorted(parts[i]),
        }
        if renderer and renderer["shadows"] == "shadows_only":
            record["shadows_only"] = True
        shape[i] = json_hash(record)
        placed[i] = json_hash({"shape": shape[i], "translation": _fs(node["translation"]),
                               "rotation": _fs(node["rotation"]), "scale": _fs(node["scale"])})
        if node["parent"] is not None and not cut(node):
            parts[node["parent"]].append(placed[i])
    return shape, placed


def candidate_shapes(nodes: list[dict], roots: set[int]) -> list[str]:
    """The shape of every node with sky nodes and the Placement roots in `roots` cut from their parents."""
    shape, _ = tree_hashes(nodes, cut=lambda n: n.get("sky", False) or n["id"] in roots)
    return shape


def geometry_hash(nodes: list[dict]) -> str:
    """The Map's geometry hash: the sorted placed hashes of its root nodes, nothing left out."""
    _, placed = tree_hashes(nodes)
    return json_hash({"roots": sorted(placed[n["id"]] for n in nodes if n["parent"] is None)})
