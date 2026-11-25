"""The N-panel, its operators and the extension's preferences. Imports bpy."""

from __future__ import annotations

from . import operators, panel, props, session

MODULES = (props, operators, panel)


def register():
    for m in MODULES:
        m.register()


def unregister():
    session.unregister()
    for m in reversed(MODULES):
        m.unregister()
