"""When two meshes match: a batched mesh and the one it was split from (ADR 0034).

Standard library only, so the checker, the Extractor and the Builder's plan share one definition.
"""

from __future__ import annotations

import struct

from .rules import FLOATS_PER_ATTRIBUTE

TOLERANCE = 1e-4   # metres for positions; the same for normal components
TOLERANT = ("position", "normal")   # what batching transformed; every other attribute must be equal


def candidates_key(record: dict) -> tuple:
    """Meshes that can match share this key: vertex count, attributes and submesh sizes."""
    return record["vertices"], tuple(record["attributes"]), tuple(record["index_counts"])


def meshes_match(a: dict, a_data: bytes, b: dict, b_data: bytes, tolerance: float = TOLERANCE) -> bool:
    """Whether two meshes (records and file bytes) match: one of them batched, the same key, every
    attribute but position and normal and every index equal, positions and normals within tolerance."""
    if not (a.get("batched") or b.get("batched")) or candidates_key(a) != candidates_key(b):
        return False
    n, pos = a["vertices"], 0
    for name in a["attributes"]:
        size = 4 * n * FLOATS_PER_ATTRIBUTE[name]
        x, y = a_data[pos:pos + size], b_data[pos:pos + size]
        if name in TOLERANT:
            fx, fy = struct.unpack(f"<{size // 4}f", x), struct.unpack(f"<{size // 4}f", y)
            if any(abs(p - q) > tolerance for p, q in zip(fx, fy)):
                return False
        elif x != y:
            return False
        pos += size
    return a_data[pos:] == b_data[pos:]
