"""kkbp-maps: builds Blender asset libraries from the maps of a user's own game install.

Importing this package imports nothing but the standard library, so `kkbp_maps.extractor`,
`kkbp_maps.bundle` and the Builder's plan load on any Python; bpy is imported only when Blender
registers the extension.
"""

NAME = "kkbp-maps"
VERSION = "0.1.0"  # the same as blender_manifest.toml's version (tests/host/test_package.py)


def register():
    from . import compat, ui

    compat.require()
    ui.register()


def unregister():
    from . import ui

    ui.unregister()
