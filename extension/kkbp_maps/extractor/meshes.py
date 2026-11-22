"""The bundle's meshes: each unique Unity mesh as a raw file in Blender's space (ADR 0011), named by the
hash of its bytes."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..bundle import hashing
from . import space
from .unity import MeshData, Ref, Store


class Meshes:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.records: dict[str, dict] = {}
        self._ids: dict[Ref, str] = {}
        self._submeshes: dict[Ref, int] = {}
        self._uv: dict[Ref, set[str]] = {}

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
        data = store.mesh(ref)
        if not data.readable or data.positions is None:
            self._ids[ref] = None
            return None
        payload, record = mesh_file(data)
        mid = hashing.digest(payload)
        if mid not in self.records:
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / f"{mid}.bin").write_bytes(payload)
            self.records[mid] = {"id": mid, "name": data.name, **record}
        self._ids[ref] = mid
        self._submeshes[ref] = len(record["index_counts"])
        self._uv[ref] = {a for a in record["attributes"] if a.startswith("uv")}
        return mid

    def submesh_count(self, ref: Ref) -> int:
        return self._submeshes[ref]

    def uv_sets(self, ref: Ref) -> set[str]:
        return self._uv[ref]


def mesh_file(m: MeshData) -> tuple[bytes, dict]:
    """A mesh's file bytes and the rest of its record: position, normal and the UV sets it has, as
    little-endian float32 per vertex in turn, then each submesh's triangles as uint32 with their
    winding swapped (det C = -1)."""
    if m.positions is None or m.normals is None:
        raise ValueError(f"mesh {m.name} has no {'positions' if m.positions is None else 'normals'}")
    n = len(m.positions)
    attributes = {"position": space.vectors(m.positions), "normal": space.vectors(m.normals)}
    for name, uv in (("uv0", m.uv0), ("uv1", m.uv1)):
        if uv is not None and len(uv) == n:
            attributes[name] = uv
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
