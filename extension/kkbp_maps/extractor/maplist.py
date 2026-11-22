"""The Maps a Game lists: which Scene Bundles are Maps, and the list entries, thumbnails and flags of each.

A Map is a Scene Bundle that one of the Game's lists names; entries in several lists that name the same
bundle are one Map with several list entries. Reading the list bundles goes through a function given
by the caller (unity.list_records by default), so the logic runs on synthetic records in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .games import Install, MapListSource

BUNDLE_SUFFIX = ".unity3d"

# (MonoBehaviour name, its typetree) for every MonoBehaviour of a list bundle.
ListReader = Callable[[Path], Iterable[tuple[str, dict]]]


@dataclass(frozen=True)
class ListEntry:
    list: str
    no: int
    name: str

    def record(self) -> dict:
        return {"list": self.list, "no": self.no, "name": self.name}


@dataclass(frozen=True)
class Thumbnail:
    """A thumbnail the story list names: its bundle under the asset folder, and its sprite's name."""
    bundle: str
    asset: str


@dataclass
class MapSource:
    key: str                      # the Scene Bundle's path under the asset folder, without the suffix
    bundle: Path
    entries: list[ListEntry] = field(default_factory=list)
    outdoor: bool | None = None   # the story list's flag; None where only Studio lists the Map
    thumbnail: Thumbnail | None = None
    list_files: set[Path] = field(default_factory=set)

    @property
    def lists(self) -> set[str]:
        return {e.list for e in self.entries}


def map_key(bundle_name: str) -> str:
    name = bundle_name.strip().replace("\\", "/")
    return name[:-len(BUNDLE_SUFFIX)] if name.lower().endswith(BUNDLE_SUFFIX) else name


def list_maps(install: Install, read: ListReader | None = None) -> tuple[list[MapSource], list[str]]:
    """Every Map the Game's lists name, in key order, and the bundles they name that aren't installed."""
    if read is None:
        from .unity import list_records
        read = list_records
    maps: dict[str, MapSource] = {}
    missing: set[str] = set()
    for source in install.game.map_lists:
        folder = install.assets / source.folder
        for path in sorted(folder.glob(f"*{BUNDLE_SUFFIX}")):
            for bundle_name, entry, extra in _entries(source, read(path)):
                key = map_key(bundle_name)
                bundle = install.assets / f"{key}{BUNDLE_SUFFIX}"
                if not bundle.is_file():
                    missing.add(key)
                    continue
                m = maps.setdefault(key, MapSource(key=key, bundle=bundle))
                if entry not in m.entries:
                    m.entries.append(entry)
                m.list_files.add(path)
                if source.list == "map":
                    if m.outdoor is None:
                        m.outdoor = bool(extra.get("outdoor"))
                    if m.thumbnail is None and extra.get("thumbnail"):
                        m.thumbnail = extra["thumbnail"]
    for m in maps.values():
        m.entries.sort(key=lambda e: ([s.list for s in install.game.map_lists].index(e.list), e.no))
    return [maps[k] for k in sorted(maps)], sorted(missing)


def _entries(source: MapListSource, behaviours):
    """(bundle name, ListEntry, extra fields) for each Map row of a list bundle's MonoBehaviours."""
    for name, tree in behaviours:
        if source.name_prefix and not name.startswith(source.name_prefix):
            continue
        if source.layout == "mapinfo":
            for p in tree.get("param", []):
                if p.get("is2D"):
                    continue
                thumb = None
                if p.get("ThumbnailBundle") and p.get("ThumbnailAsset"):
                    thumb = Thumbnail(map_key(p["ThumbnailBundle"]) + BUNDLE_SUFFIX, p["ThumbnailAsset"])
                yield (p["AssetBundleName"], ListEntry(source.list, int(p["No"]), p["MapName"]),
                       {"outdoor": p.get("isOutdoors"), "thumbnail": thumb})
        elif source.layout == "studio_rows":
            for row in tree.get("list", []):
                cells = row.get("list", [])
                if len(cells) < 3 or not cells[0].strip().lstrip("-").isdigit() or not cells[2].strip():
                    continue  # the two header rows, and rows without a bundle
                yield cells[2], ListEntry(source.list, int(cells[0]), cells[1]), {}
        else:
            raise ValueError(f"unknown map list layout {source.layout!r}")


def camera_profile(install: Install, m: MapSource) -> str:
    for list_name, camera in install.game.camera_by_list:
        if list_name in m.lists:
            return camera
    raise ValueError(f"{m.key} is in no list that names a Camera Profile")


def thumbnail_names(install: Install, thumb: Thumbnail) -> dict[str, str]:
    """The sprite name for each Time of Day, from the one the list names: the others share its stem."""
    for suffix in install.game.thumbnail_suffixes:
        if thumb.asset.endswith(suffix):
            stem = thumb.asset[:-len(suffix)]
            return {tod: stem + s for s, tod in install.game.thumbnail_suffixes.items()}
    return {}
