"""The N-panel: the 3D Viewport's sidebar, tab "KKBP Maps" (D18)."""

from __future__ import annotations

import json
import time

import bpy

from ..jobs import driver
from . import library
from .operators import bundle_folder, library_folder, output_folder
from .props import preferences
from .session import session

CATEGORY = "KKBP Maps"


def draw_dependencies(layout) -> bool:
    """The dependency problems, if any; whether there were any."""
    problems = session().problems
    if problems:
        box = layout.box()
        box.alert = True
        for p in problems:
            _wrapped(box, p, icon="ERROR")
    return bool(problems)


def _wrapped(layout, text: str, icon: str = "NONE", width: int = 48):
    """Text over as many lines as it needs, since a panel label doesn't wrap."""
    words, line, first = text.split(), "", True
    col = layout.column(align=True)
    for w in words:
        if line and len(line) + len(w) + 1 > width:
            col.label(text=line, icon=icon if first else "BLANK1")
            line, first = w, False
        else:
            line = f"{line} {w}".strip()
    if line:
        col.label(text=line, icon=icon if first else "BLANK1")


class KKBPMAPS_UL_maps(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index=0, flt_flag=0):
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="SCENE_DATA" if item.studio_only else "WORLD")
        sub = row.row()
        sub.alignment = "RIGHT"
        sub.label(text=f"{item.megabytes:.0f} MB")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item] * len(items)
        if self.filter_name:
            needle = self.filter_name.lower()
            flags = [self.bitflag_filter_item if needle in (i.name + " " + i.key).lower() else 0 for i in items]
        return flags, []


class Base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY


class KKBPMAPS_PT_main(Base, bpy.types.Panel):
    bl_label = "KKBP Maps"

    def draw(self, context):
        layout = self.layout
        prefs = preferences(context)
        s = session()
        if draw_dependencies(layout):
            return
        if s.install is None and not s.install_error and prefs.game_folder:
            s.detect(prefs.game_folder)
        layout.prop(prefs, "game_folder", text="Game")
        if s.install_error:
            _wrapped(layout.box(), s.install_error, icon="ERROR")
        elif s.install:
            layout.label(text=f"{s.install.game.id} at {s.install.root.name}", icon="CHECKMARK")
        layout.prop(prefs, "output_folder", text="Output")
        out = output_folder(context)
        if out and s.install:
            layout.label(text=f"Library: {library_folder(context).name}, Map Bundles: {driver.BUNDLE_FOLDER}",
                         icon="ASSET_MANAGER")


class KKBPMAPS_PT_maps(Base, bpy.types.Panel):
    bl_label = "Maps"
    bl_parent_id = "KKBPMAPS_PT_main"

    @classmethod
    def poll(cls, context):
        return session().install is not None and not session().problems

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.kkbp_maps
        s = session()
        row = layout.row(align=True)
        row.operator("kkbp_maps.list_maps", icon="FILE_REFRESH",
                     text="Listing Maps..." if s.listing else ("List Maps Again" if settings.maps else "List Maps"))
        if s.list_error:
            _wrapped(layout, s.list_error, icon="INFO")
        if not settings.maps:
            return
        layout.template_list("KKBPMAPS_UL_maps", "", settings, "maps", settings, "index", rows=8)
        row = layout.row(align=True)
        row.operator("kkbp_maps.select", text="All").select = True
        row.operator("kkbp_maps.select", text="None").select = False
        chosen = [m for m in settings.maps if m.selected]
        disk, seconds = driver.estimate([int(m.megabytes * 2**20) for m in chosen])
        layout.label(text=f"{len(chosen)} of {len(settings.maps)} Maps: about {disk / 2**30:.1f} GB, "
                          f"{_duration(seconds)}", icon="TIME")


class KKBPMAPS_PT_options(Base, bpy.types.Panel):
    bl_label = "Options"
    bl_parent_id = "KKBPMAPS_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return session().install is not None and not session().problems

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        settings = context.window_manager.kkbp_maps
        layout.prop(settings, "camera")
        layout.prop(settings, "texture_limit")
        layout.prop(settings, "previews")


class KKBPMAPS_PT_build(Base, bpy.types.Panel):
    bl_label = "Build"
    bl_parent_id = "KKBPMAPS_PT_main"

    @classmethod
    def poll(cls, context):
        return session().install is not None and not session().problems

    def draw(self, context):
        layout = self.layout
        s = session()
        folder = bundle_folder(context)
        if folder is not None:
            s.watch(folder)
        state = s.state
        if s.running():
            if state:
                _progress(layout, state)
            layout.operator("kkbp_maps.cancel", icon="CANCEL")
            return
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("kkbp_maps.build", icon="PLAY")
        if state and state.status in ("cancelled", "stopped", "failed"):
            _wrapped(layout, _finished_text(state), icon="ERROR" if state.status == "failed" else "PAUSE")
            layout.operator("kkbp_maps.resume", icon="RECOVER_LAST")
        elif state and state.status == "done":
            _wrapped(layout, _finished_text(state), icon="CHECKMARK")
        row = layout.row(align=True)
        row.operator("kkbp_maps.open_report", text="Log", icon="TEXT").log = True
        row.operator("kkbp_maps.delete_bundles", text="Delete Map Bundles", icon="TRASH")


class KKBPMAPS_PT_report(Base, bpy.types.Panel):
    bl_label = "Build Report"
    bl_parent_id = "KKBPMAPS_PT_main"

    @classmethod
    def poll(cls, context):
        folder = library_folder(context) if session().install else None
        return folder is not None and (folder / "build-report.json").is_file()

    def draw(self, context):
        layout = self.layout
        folder = library_folder(context)
        report = _report(folder / "build-report.json")
        if report is None:
            layout.label(text="The Build Report can't be read", icon="ERROR")
            return
        col = layout.column(align=True)
        col.label(text=f"{len(report['maps'])} Maps, {report['map_variants']} Map Variants", icon="WORLD")
        col.label(text=f"{report['props']} Props, {report['structures']} Structures", icon="ASSET_MANAGER")
        approximated = sum(1 for m in report["maps"] for t in m["shader_tiers"] if t["level"] != "skipped")
        skipped = sum(1 for m in report["maps"] for t in m["shader_tiers"] if t["level"] == "skipped")
        if approximated or skipped:
            col.label(text=f"Shaders: {approximated} approximated, {skipped} left out", icon="SHADING_RENDERED")
        if report.get("not_built"):
            col.label(text=f"{len(report['not_built'])} Maps not built", icon="ERROR")
        if report["unknown_words"]:
            col.label(text=f"{len(report['unknown_words'])} words the Name Tables don't know", icon="QUESTION")
        layout.operator("kkbp_maps.open_report", icon="TEXT").log = False
        if library.registered(folder) is None:
            layout.operator("kkbp_maps.register_library", icon="ADD")
        else:
            layout.label(text="In your asset libraries", icon="CHECKMARK")


_reports: dict = {}


def _report(path):
    """The Build Report, read again only when it changes."""
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    cached = _reports.get(path)
    if cached is None or cached[0] != stamp:
        try:
            cached = (stamp, json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            cached = (stamp, None)
        _reports[path] = cached
    return cached[1]


def _progress(layout, state: driver.State):
    total = len(state.steps)
    finished = sum(1 for s in state.steps if s.status not in ("pending", "running"))
    current = state.current()
    text = f"{finished} of {total} steps"
    if current:
        text = f"{_step_text(current.id)} ({finished + 1} of {total})"
    layout.progress(factor=finished / total if total else 0, type="BAR", text=text)
    layout.label(text=f"Running for {_duration(time.time() - state.started)}", icon="TIME")


def _step_text(step_id: str) -> str:
    kind, _, key = step_id.partition(":")
    return {"extract": f"Extracting {key}", "map": f"Building {key}", "assets": "Building the Props and Structures",
            "finish": "Writing the catalogs and the report"}[kind]


def _finished_text(state: driver.State) -> str:
    words = {"done": "Built", "failed": "The Build failed", "cancelled": "Cancelled",
             "stopped": "Stopped when Blender closed"}[state.status]
    took = f" in {_duration(state.finished - state.started)}" if state.finished else ""
    return f"{words}{took}{f': {state.message}' if state.message else ''}"


def _duration(seconds: float) -> str:
    minutes = round(seconds / 60)
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes // 60} h {minutes % 60:02d} min"


CLASSES = (KKBPMAPS_UL_maps, KKBPMAPS_PT_main, KKBPMAPS_PT_maps, KKBPMAPS_PT_options, KKBPMAPS_PT_build,
           KKBPMAPS_PT_report)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
