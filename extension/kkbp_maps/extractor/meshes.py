"""The bundle's meshes: each unique Unity mesh as a raw file in Blender's space (ADR 0011), named by the
hash of its bytes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..bundle import hashing
from ..bundle.matching import candidates_key, meshes_match
from . import space
from .unity import MeshData, Ref, Store


@dataclass(frozen=True)
class BatchPiece:
    """A renderer's part of a statically batched mesh (KKS): the Combined Mesh, the renderer's submesh
    range, and the inverse of its Unity world matrix (row by row), which moves the piece back into
    the renderer's space (kks-spike.md, section 7)."""
    ref: Ref
    first: int
    count: int
    inverse: tuple = field(repr=False)


class Meshes:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.records: dict[str, dict] = {}
        self._ids: dict = {}
        self._submeshes: dict = {}
        self._uv: dict = {}
        self._data: dict[str, bytes] = {}   # file bytes of the meshes a batched piece may match
        self.full: set = set()   # meshes whose every channel is carried (Game.vertex_data_shaders)

    def add(self, store: Store, ref: Ref) -> str:
        """The Content Hash of a mesh, writing its file the first time."""
        mid = self.try_add(store, ref)
        if mid is None:
            raise ValueError(f"mesh {ref} has no vertex data")
        return mid

    def try_add(self, store: Store, ref: Ref) -> str | None:
        """The Content Hash of a mesh, or None for one without vertex data (unreadable)."""
        if ref in self._ids:
            return self._ids[ref]
        batched = isinstance(ref, BatchPiece)
        data = store.mesh(ref.ref if batched else ref)
        if not data.readable or data.positions is None:
            self._ids[ref] = None
            return None
        if batched:
            data = split(data, ref)
        payload, record = mesh_file(data, full=ref in self.full)
        mid = hashing.digest(payload)
        if batched:
            record["batched"] = True
            mid = self._match(record, payload) or mid
        if mid not in self.records:
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / f"{mid}.bin").write_bytes(payload)
            self.records[mid] = {"id": mid, "name": data.name, **record}
            self._data[mid] = payload
        self._ids[ref] = mid
        self._submeshes[ref] = len(record["index_counts"])
        self._uv[ref] = {a for a in record["attributes"] if a.startswith("uv")}
        return mid

    def _match(self, record: dict, payload: bytes) -> str | None:
        """An earlier mesh of this Map that a batched piece matches (ADR 0034), unbatched ones first."""
        key = candidates_key(record)
        found = [m for m in self.records.values() if candidates_key(m) == key
                 and meshes_match(record, payload, m, self._data[m["id"]])]
        found.sort(key=lambda m: bool(m.get("batched")))
        return found[0]["id"] if found else None

    def submesh_count(self, ref) -> int:
        return self._submeshes[ref]

    def uv_sets(self, ref: Ref) -> set[str]:
        return self._uv[ref]


def split(m: MeshData, piece: BatchPiece) -> MeshData:
    """A batched renderer's submeshes cut out of the Combined Mesh: only the vertices they use, in
    their order, with positions and normals moved back by the inverse of the renderer's world matrix."""
    subs = m.submeshes[piece.first:piece.first + piece.count]
    if len(subs) != piece.count:
        raise ValueError(f"mesh {m.name} has no submeshes {piece.first} to {piece.first + piece.count - 1}")
    used = np.unique(np.concatenate(subs))
    remap = np.full(len(m.positions), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    inv = np.asarray(piece.inverse, dtype=np.float64).reshape(4, 4)
    pos = m.positions[used].astype(np.float64) @ inv[:3, :3].T + inv[:3, 3]
    normals = None
    if m.normals is not None:   # world normal -> local: the transpose of the world matrix's 3 × 3
        world = np.linalg.inv(inv)[:3, :3]
        normals = m.normals[used].astype(np.float64) @ world
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    def pick(a):
        return None if a is None else np.ascontiguousarray(a[used])

    return MeshData(m.name, pos.astype(np.float32), None if normals is None else normals.astype(np.float32),
                    pick(m.uv0), pick(m.uv1), [remap[s] for s in subs], colors=pick(m.colors),
                    uv0_zw=pick(m.uv0_zw), uv1_zw=pick(m.uv1_zw), uv2=pick(m.uv2), uv3=pick(m.uv3))


def mesh_file(m: MeshData, full: bool = False) -> tuple[bytes, dict]:
    """A mesh's file bytes and the rest of its record: position, normal and the UV sets it has, as
    little-endian float32 per vertex in turn, then each submesh's triangles as uint32 with their
    winding swapped (det C = -1)."""
    if m.positions is None or m.normals is None:
        raise ValueError(f"mesh {m.name} has no {'positions' if m.positions is None else 'normals'}")
    n = len(m.positions)
    attributes = {"position": space.vectors(m.positions), "normal": space.vectors(m.normals)}
    # In the contract's order (Map Bundle 0.10); a _zw half only with its UV set.
    for name, values in (("color0", m.colors), ("uv0", m.uv0), ("uv0_zw", m.uv0_zw if m.uv0 is not None else None),
                         ("uv1", m.uv1), ("uv1_zw", m.uv1_zw if m.uv1 is not None else None), ("uv2", m.uv2),
                         ("uv3", m.uv3)):
        if name not in ("uv0", "uv1") and not full:
            continue
        if values is not None and len(values) == n:
            attributes[name] = values
    parts = [np.ascontiguousarray(a, dtype="<f4").tobytes() for a in attributes.values()]
    counts = []
    for indices in m.submeshes:
        tris = space.triangles(np.asarray(indices, dtype=np.int64))
        if len(tris) and (tris.min() < 0 or tris.max() >= n):
            raise ValueError(f"mesh {m.name} has an index outside its {n} vertices")
        parts.append(tris.astype("<u4").tobytes())
        counts.append(int(len(tris)))
    if not counts or 0 in counts:
        raise ValueError(f"mesh {m.name} has an empty submesh")
    return b"".join(parts), {"vertices": n, "attributes": list(attributes), "index_counts": counts}
