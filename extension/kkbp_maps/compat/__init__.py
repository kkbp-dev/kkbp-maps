"""The only place that checks Blender's version (CLAUDE.md, "Layers"). Every Blender build the Builder
supports goes through here; what differs between them is named by what it does, not by a version."""

from __future__ import annotations

import bpy

MINIMUM = (5, 2, 0)  # D19: Blender 5.2 LTS
EEVEE = "BLENDER_EEVEE"


class UnsupportedBlender(RuntimeError):
    pass


def version_string() -> str:
    return bpy.app.version_string


def require():
    if tuple(bpy.app.version) < MINIMUM:
        raise UnsupportedBlender(f"kkbp-maps needs Blender {'.'.join(map(str, MINIMUM))} or later; this is "
                                 f"{bpy.app.version_string}")


def eevee_engine() -> str:
    return EEVEE
