"""The extension's preferences (the game and output folders, kept with Blender's preferences) and
the panel's settings for this session (the Maps listed and the build options)."""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, \
    StringProperty

CAMERAS = [
    ("MAP", "Each Map's own", "Each Map through the camera that shows it in the game: Studio's for Studio Maps, "
                              "the story game's for the rest"),
    ("studio", "Studio", "Every Map through CharaStudio's camera"),
    ("game", "Story game", "Every Map through the story game's camera, with its height fog"),
]
TEXTURE_LIMITS = [
    ("0", "No limit", "Keep every texture at the game's size"),
    ("4096", "4096", "Scale textures larger than 4096 pixels down"),
    ("2048", "2048", "Scale textures larger than 2048 pixels down"),
    ("1024", "1024", "Scale textures larger than 1024 pixels down"),
]


def _game_changed(self, context):
    from .session import session

    session().detect(self.game_folder)
    context.window_manager.kkbp_maps.maps.clear()


class KKBPMapsPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__.rpartition(".")[0]

    game_folder: StringProperty(name="Game Folder", subtype="DIR_PATH", update=_game_changed,
                                description="The folder of your KK install, the one that holds Koikatu_Data and abdata")
    output_folder: StringProperty(name="Output Folder", subtype="DIR_PATH",
                                  description="Where the Map Library (KK Maps) and its Map Bundles go")

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "game_folder")
        layout.prop(self, "output_folder")
        from .panel import draw_dependencies
        draw_dependencies(layout)


class KKBPMapsMap(bpy.types.PropertyGroup):
    key: StringProperty()
    name: StringProperty()
    selected: BoolProperty(name="Build", default=True)
    studio_only: BoolProperty()
    megabytes: FloatProperty()


class KKBPMapsSettings(bpy.types.PropertyGroup):
    maps: CollectionProperty(type=KKBPMapsMap)
    index: IntProperty()
    camera: EnumProperty(name="Camera Profile", items=CAMERAS, default="MAP")
    texture_limit: EnumProperty(name="Texture Limit", items=TEXTURE_LIMITS, default="0")
    previews: BoolProperty(name="Asset Previews", default=True,
                           description="Render a preview for every Prop and Structure (takes longer)")


CLASSES = (KKBPMapsPreferences, KKBPMapsMap, KKBPMapsSettings)


def preferences(context) -> KKBPMapsPreferences:
    return context.preferences.addons[KKBPMapsPreferences.bl_idname].preferences


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.kkbp_maps = PointerProperty(type=KKBPMapsSettings)


def unregister():
    del bpy.types.WindowManager.kkbp_maps
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
