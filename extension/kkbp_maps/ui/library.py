"""Adding a Map Library to Blender's asset libraries (D18), each Game's folder as a library of its own
(D10). Never saves the preferences itself: Blender does that when its auto-save is on."""

from __future__ import annotations

from pathlib import Path

import bpy


def _same(a: str, b: Path) -> bool:
    try:
        return Path(bpy.path.abspath(a)).resolve() == b.resolve()
    except OSError:
        return False


def registered(directory: Path):
    """The asset library entry for `directory`, or None."""
    for lib in bpy.context.preferences.filepaths.asset_libraries:
        if _same(lib.path, directory):
            return lib
    return None


def register_library(name: str, directory: Path) -> str:
    """Adds `directory` to the asset libraries as `name`, or renames the entry that has it. Says what it did."""
    prefs = bpy.context.preferences
    lib = registered(directory)
    if lib is not None:
        lib.name = name
        what = f"'{name}' is in your asset libraries already"
    else:
        prefs.filepaths.asset_libraries.new(name=name, directory=str(directory))
        what = f"Added '{name}' to your asset libraries"
    prefs.is_dirty = True
    if prefs.use_preferences_save:
        return what + "; Blender saves it with your preferences"
    return what + ". Auto-save of preferences is off: save them (Preferences > Save Preferences) to keep it"
