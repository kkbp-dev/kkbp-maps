"""The Map Bundle contract: its schemas (schema/), its rules (README.md) and the checker.

Never imports bpy, uses only the standard library, and imports only relatively within itself, so the
Extractor, the Builder, the tests and the developer tools can all load it.
"""

from .check import SCHEMA_VERSION, check, closed_sets, schemas
from .reader import Bundle, BundleRejected, MeshBuffers, read

__all__ = ["SCHEMA_VERSION", "Bundle", "BundleRejected", "MeshBuffers", "check", "closed_sets", "read", "schemas"]
