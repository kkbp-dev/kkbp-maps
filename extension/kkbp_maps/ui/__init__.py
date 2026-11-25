"""The N-panel, its operators and the extension's preferences. Imports bpy."""

from __future__ import annotations

MODULES: tuple = ()


def register():
    for m in MODULES:
        m.register()


def unregister():
    for m in reversed(MODULES):
        m.unregister()
