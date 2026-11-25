"""The N-panel's operators: listing Maps, starting, cancelling and resuming a Build, opening its
report, adding the Map Library to the asset libraries, and deleting a Game's Map Bundles."""

from __future__ import annotations

import shutil
from pathlib import Path

import bpy
from bpy.props import BoolProperty

from ..jobs import driver
from . import library
from .props import preferences
from .session import request_for, session


def output_folder(context) -> Path | None:
    folder = preferences(context).output_folder
    return Path(bpy.path.abspath(folder)).resolve() if folder else None


def bundle_folder(context) -> Path | None:
    s, out = session(), output_folder(context)
    return out / driver.BUNDLE_FOLDER / s.install.game.id if out and s.install else None


def library_folder(context) -> Path | None:
    s, out = session(), output_folder(context)
    return out / f"{s.install.game.id} Maps" if out and s.install else None


class KKBPMAPS_OT_list_maps(bpy.types.Operator):
    bl_idname = "kkbp_maps.list_maps"
    bl_label = "List Maps"
    bl_description = "Read the game's Map lists (takes a few seconds)"

    @classmethod
    def poll(cls, context):
        s = session()
        return s.install is not None and s.listing is None and not s.problems

    def execute(self, context):
        out = output_folder(context)
        work = (out / driver.BUNDLE_FOLDER) if out else Path(bpy.app.tempdir)
        session().list_maps(work)
        return {"FINISHED"}


class KKBPMAPS_OT_select(bpy.types.Operator):
    bl_idname = "kkbp_maps.select"
    bl_label = "Select Maps"
    bl_description = "Select every Map or none"
    bl_options = {"INTERNAL"}

    select: BoolProperty()

    def execute(self, context):
        for m in context.window_manager.kkbp_maps.maps:
            m.selected = self.select
        return {"FINISHED"}


class KKBPMAPS_OT_build(bpy.types.Operator):
    bl_idname = "kkbp_maps.build"
    bl_label = "Build"
    bl_description = "Extract and build the selected Maps in the background; Blender stays usable"

    @classmethod
    def poll(cls, context):
        s = session()
        return (s.install is not None and not s.problems and not s.running() and output_folder(context) is not None
                and any(m.selected for m in context.window_manager.kkbp_maps.maps))

    def execute(self, context):
        settings = context.window_manager.kkbp_maps
        keys = [m.key for m in settings.maps if m.selected]
        request = request_for(session().install, str(output_folder(context)), keys,
                              None if settings.camera == "MAP" else settings.camera,
                              int(settings.texture_limit) or None, settings.previews)
        session().start(request)
        self.report({"INFO"}, f"Building {len(keys)} Maps into {request.library}")
        return {"FINISHED"}


class KKBPMAPS_OT_resume(bpy.types.Operator):
    bl_idname = "kkbp_maps.resume"
    bl_label = "Resume"
    bl_description = "Run the last Build again: what it finished is kept"

    @classmethod
    def poll(cls, context):
        folder = bundle_folder(context)
        return (folder is not None and (folder / driver.REQUEST_FILE).is_file() and not session().running()
                and not session().problems)

    def execute(self, context):
        old = driver.Request.load(bundle_folder(context) / driver.REQUEST_FILE)
        s = session()
        request = request_for(s.install, old.output, old.maps, old.camera, old.max_texture_size, old.previews)
        s.start(request)
        return {"FINISHED"}


class KKBPMAPS_OT_cancel(bpy.types.Operator):
    bl_idname = "kkbp_maps.cancel"
    bl_label = "Cancel"
    bl_description = "Stop the Build after stopping its current step; Resume carries on from there"

    @classmethod
    def poll(cls, context):
        return session().running()

    def execute(self, context):
        session().cancel()
        return {"FINISHED"}


class KKBPMAPS_OT_open_report(bpy.types.Operator):
    bl_idname = "kkbp_maps.open_report"
    bl_label = "Open Build Report"
    bl_description = "Open the Build Report in the program your system uses for Markdown files"

    log: BoolProperty(description="Open the Build's log instead")

    @classmethod
    def poll(cls, context):
        return library_folder(context) is not None

    def execute(self, context):
        path = (bundle_folder(context) / driver.LOG_FILE) if self.log else (library_folder(context) / "build-report.md")
        if not path.is_file():
            self.report({"WARNING"}, f"{path} isn't there yet")
            return {"CANCELLED"}
        bpy.ops.wm.path_open(filepath=str(path))
        return {"FINISHED"}


class KKBPMAPS_OT_register_library(bpy.types.Operator):
    bl_idname = "kkbp_maps.register_library"
    bl_label = "Add to Asset Libraries"
    bl_description = "Add the Map Library to Blender's asset libraries, so the Asset Browser shows it"

    @classmethod
    def poll(cls, context):
        folder = library_folder(context)
        return folder is not None and (folder / "blender_assets.cats.txt").is_file()

    def invoke(self, context, event):
        folder = library_folder(context)
        return context.window_manager.invoke_confirm(
            self, event, title="Add to Asset Libraries?",
            message=f"Adds '{folder.name}' ({folder}) to Blender's asset libraries", confirm_text="Add")

    def execute(self, context):
        folder = library_folder(context)
        self.report({"INFO"}, library.register_library(folder.name, folder))
        return {"FINISHED"}


class KKBPMAPS_OT_delete_bundles(bpy.types.Operator):
    bl_idname = "kkbp_maps.delete_bundles"
    bl_label = "Delete Map Bundles"
    bl_description = ("Delete this Game's Map Bundles to free disk space. The Map Library stays; "
                      "the next Build extracts every Map again")

    @classmethod
    def poll(cls, context):
        folder = bundle_folder(context)
        return folder is not None and folder.is_dir() and not session().running()

    def invoke(self, context, event):
        folder = bundle_folder(context)
        return context.window_manager.invoke_confirm(
            self, event, title="Delete the Map Bundles?",
            message=f"Deletes {folder} for good. The Map Library stays", confirm_text="Delete", icon="WARNING")

    def execute(self, context):
        folder = bundle_folder(context)
        shutil.rmtree(folder)
        session().state, session().state_folder = None, None
        self.report({"INFO"}, f"Deleted {folder}")
        return {"FINISHED"}


CLASSES = (KKBPMAPS_OT_list_maps, KKBPMAPS_OT_select, KKBPMAPS_OT_build, KKBPMAPS_OT_resume, KKBPMAPS_OT_cancel,
           KKBPMAPS_OT_open_report, KKBPMAPS_OT_register_library, KKBPMAPS_OT_delete_bundles)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
