"""Reads a checked Map Bundle into the sections the Builder works from.

    from bundle import read
    b = read(path)                # checks the bundle first; raises BundleRejected if it breaks the contract
    b.nodes[3]["name"], b.meshes[mesh_id], b.texture_path(texture_id)
    buffers = b.mesh_buffers(mesh_id)   # float32 and uint32 arrays, ready for foreach_set

Standard library only, like the rest of bundle/. The records are the bundle's own JSON objects; the
Bundle indexes them by id and adds the few lookups every Builder step needs.
"""

from __future__ import annotations

import json
import sys
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from .check import check
from .rules import DATA_FILES, FLOATS_PER_ATTRIBUTE


class BundleRejected(ValueError):
    def __init__(self, path: Path, problems: list[str]):
        self.problems = problems
        shown = "\n  ".join(problems[:20])
        more = f"\n  … and {len(problems) - 20} more" if len(problems) > 20 else ""
        super().__init__(f"{path} isn't a Map Bundle this Builder can read:\n  {shown}{more}")


@dataclass(frozen=True)
class MeshBuffers:
    """A mesh file's data: each attribute as a flat float32 array, each submesh's indices as uint32."""
    vertices: int
    attributes: dict[str, array]
    submeshes: list[array]


@dataclass
class Bundle:
    root: Path
    manifest: dict
    map: dict
    nodes: list[dict]
    meshes: dict[str, dict]
    materials: dict[str, dict]
    textures: dict[str, dict]
    lightmap_sets: dict[str, dict]
    variants: list[dict]
    candidates: list[dict]
    children: list[list[int]] = field(default_factory=list)
    winds: list[dict] = field(default_factory=list)   # scene.json's SpeedTree winds, by renderers' `wind`

    @property
    def game(self) -> str:
        return self.manifest["game"]

    @property
    def key(self) -> str:
        return self.map["key"]

    def texture_path(self, texture_id: str) -> Path:
        t = self.textures[texture_id]
        return self.root / "textures" / f"{texture_id}.{t['format']}"

    def mesh_path(self, mesh_id: str) -> Path:
        return self.root / "meshes" / f"{mesh_id}.bin"

    def mesh_buffers(self, mesh_id: str) -> MeshBuffers:
        m = self.meshes[mesh_id]
        data = self.mesh_path(mesh_id).read_bytes()
        n = m["vertices"]
        pos = 0
        attributes = {}
        for name in m["attributes"]:
            size = 4 * n * FLOATS_PER_ATTRIBUTE[name]
            attributes[name] = _array("f", data[pos:pos + size])
            pos += size
        submeshes = []
        for count in m["index_counts"]:
            submeshes.append(_array("I", data[pos:pos + 4 * count]))
            pos += 4 * count
        return MeshBuffers(n, attributes, submeshes)

    def subtree(self, node: int) -> list[int]:
        """The node and everything under it, parents before children."""
        out, stack = [], [node]
        while stack:
            i = stack.pop()
            out.append(i)
            stack.extend(reversed(self.children[i]))
        return out

    def hidden_in(self, variant: dict) -> set[int]:
        """Every node a Map Variant doesn't show: its hidden nodes with everything under them."""
        return {i for h in variant["hidden"] for i in self.subtree(h)}


def read(path, *, deep: bool = False) -> Bundle:
    """The Map Bundle at `path` (its folder or its manifest.json), after checking it against the contract."""
    root = Path(path).expanduser()
    if root.name == "manifest.json":
        root = root.parent
    problems = check(root, deep=deep)
    if problems:
        raise BundleRejected(root, problems)
    d = {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in DATA_FILES}
    nodes = d["scene"]["nodes"]
    children: list[list[int]] = [[] for _ in nodes]
    for n in nodes:
        if n["parent"] is not None:
            children[n["parent"]].append(n["id"])
    return Bundle(
        root=root,
        manifest=d["manifest"],
        map=d["map"],
        nodes=nodes,
        meshes={m["id"]: m for m in d["meshes"]["meshes"]},
        materials={m["id"]: m for m in d["materials"]["materials"]},
        textures={t["id"]: t for t in d["textures"]["textures"]},
        lightmap_sets={s["id"]: s for s in d["lightmaps"]["sets"]},
        variants=d["variants"]["variants"],
        candidates=d["assets"]["candidates"],
        children=children,
        winds=d["scene"].get("winds", []),
    )


def _array(code: str, data: bytes) -> array:
    a = array(code)
    if a.itemsize != 4:  # array's sizes aren't fixed by the language; 'L' is 4 bytes where 'I' isn't
        a = array("L" if code == "I" else code)
    a.frombytes(data)
    if sys.byteorder == "big":
        a.byteswap()
    return a
