"""What each Game's map data looks like, as data.

Game differences live here, not as checks of a Game's id in the code (CLAUDE.md). So do the few names
the game gives as the only marker of something: the Candidate prefixes and the Helper names
(docs/design/games.md). Only KK is filled in; KKS and SVS are known well enough to be detected and
refused until their phases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MapListSource:
    """A game list that names Maps: where its bundles are and how their records are laid out."""
    list: str        # the bundle's map-list set value: "map" or "studio"
    folder: str      # under the asset folder
    layout: str      # "mapinfo": records in a `param` array; "studio_rows": Excel-style string rows
    name_prefix: str = ""   # only MonoBehaviours whose name starts with this hold Map rows


@dataclass(frozen=True)
class Game:
    id: str
    data_folder: str                  # the player's <Name>_Data folder, which marks an install
    asset_folder: str = "abdata"
    supported: bool = False
    times_of_day: tuple[str, ...] = ()
    # SunLightInfo.Info.type -> Time of Day.
    sun_types: dict[int, str] = field(default_factory=dict)
    # The story list's thumbnail names end in a suffix per Time of Day.
    thumbnail_suffixes: dict[str, str] = field(default_factory=dict)
    map_lists: tuple[MapListSource, ...] = ()
    # The Camera Profile of a Map: the first list in this order that names it decides.
    camera_by_list: tuple[tuple[str, str], ...] = (("map", "game"), ("studio", "studio"))
    # Candidate rules by name prefix, tried in order; case-sensitive (ADR 0004).
    prefixes: tuple[tuple[str, str], ...] = (("p_", "p_prefix"), ("mo_", "mo_prefix"), ("o_", "o_prefix"))
    # Names of room containers: a node without a renderer of its own whose name matches one of these
    # regular expressions holds a whole room or shell, so it is walked into like a group (ADR 0019).
    containers: tuple[str, ...] = ()
    # Renderer types that are always Helpers (KK uses SpriteRenderers only for action-point icons).
    helper_renderers: frozenset[str] = frozenset()
    # Renderer types the bundle can't carry, by skip reason.
    skipped_renderers: tuple[tuple[str, str], ...] = (("ParticleSystemRenderer", "particles"),
                                                       ("SkinnedMeshRenderer", "skinned"))
    # How the game's Unity unpacks a normal map: X from A alone (Unity 5.6) or from R times A (2019).
    normal_x_from_alpha: bool = True
    # The Shader name prefix of a Sky Dome's material, on a built-in mesh.
    sky_shader_prefix: str = "Skybox/"
    # The player's own resource files under <data_folder>/Resources, which hold Unity's built-in
    # meshes and shaders; a Map may point into them (ADR 0031).
    builtin_resources: tuple[str, ...] = ("unity default resources", "unity_builtin_extra")
    # Lightmap RGBM decode: value = scale · a^exponent · srgb_to_linear(rgb) (kk-spike, section 3).
    rgbm: tuple[float, float] = (34.493242, 2.2)


KK = Game(
    id="KK",
    data_folder="Koikatu_Data",
    supported=True,
    times_of_day=("day", "evening", "night"),
    sun_types={0: "day", 1: "evening", 2: "night"},
    thumbnail_suffixes={"_00": "day", "_01": "evening", "_02": "night"},
    map_lists=(
        MapListSource(list="map", folder="map/list/mapinfo", layout="mapinfo"),
        MapListSource(list="studio", folder="studio/info", layout="studio_rows", name_prefix="Map_"),
    ),
    helper_renderers=frozenset({"SpriteRenderer"}),
    containers=(r"^(p_|o_|mo_)(o_)?koi_(stu_)?map",),
)

KKS = Game(id="KKS", data_folder="KoikatsuSunshine_Data", normal_x_from_alpha=False)
SVS = Game(id="SVS", data_folder="SamabakeScramble_Data", normal_x_from_alpha=False)

GAMES = (KK, KKS, SVS)


class NotAGameFolder(ValueError):
    pass


class UnsupportedGame(ValueError):
    pass


@dataclass(frozen=True)
class Install:
    game: Game
    root: Path

    @property
    def assets(self) -> Path:
        return self.root / self.game.asset_folder

    def builtin_resources(self) -> tuple[Path, ...]:
        """The player's built-in resource files that this install has."""
        folder = self.root / self.game.data_folder / "Resources"
        return tuple(folder / n for n in self.game.builtin_resources if (folder / n).is_file())

    def relative(self, path: Path) -> str:
        """A path in the install as a Manifest source names it: relative, with forward slashes."""
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()


def detect(folder, *, require_supported: bool = True) -> Install:
    """The Game installed in `folder`, which may also be its asset folder (abdata)."""
    folder = Path(folder).expanduser()
    candidates = [folder, folder.parent] if folder.name.lower() == "abdata" else [folder]
    for root in candidates:
        for game in GAMES:
            if (root / game.data_folder).is_dir() and (root / game.asset_folder).is_dir():
                if require_supported and not game.supported:
                    raise UnsupportedGame(f"{root} holds {game.id}, which the Extractor doesn't support yet")
                return Install(game, root)
    raise NotAGameFolder(f"{folder} isn't the folder of a KK, KKS or SVS install: it should hold "
                         f"{' or '.join(g.data_folder for g in GAMES)} and abdata")
