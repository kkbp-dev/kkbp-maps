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
    display_name: str = ""

    def record(self) -> dict:
        r = {"list": self.list, "no": self.no, "name": self.name}
        if self.display_name and self.display_name != self.name:
            r["display_name"] = self.display_name
        return r


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
    thumbnail: Thumbnail | None = None              # KK: one, the others named by suffix
    thumbnails: dict[str, Thumbnail] = field(default_factory=dict)   # KKS: one per Time of Day
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
        ids, id_files = _thumbnail_ids(install, source, read)
        for path in sorted(folder.glob(f"*{BUNDLE_SUFFIX}")):
            for bundle_name, entry, extra in _entries(source, read(path)):
                if not bundle_name.strip():
                    continue   # an entry with no Scene Bundle (KKS's shops and corners)
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
                    by_id = {tod: ids[i] for tod, i in extra.get("thumbnail_ids", {}).items() if i in ids}
                    if by_id and not m.thumbnails:
                        m.thumbnails = by_id
                        m.list_files.update(id_files)
    for m in maps.values():
        m.entries.sort(key=lambda e: ([s.list for s in install.game.map_lists].index(e.list), e.no))
    return [maps[k] for k in sorted(maps)], sorted(missing)


def _thumbnail_ids(install: Install, source: MapListSource, read: ListReader) -> tuple[dict, set]:
    """KKS: thumbnail ID -> Thumbnail, from the lists in `source.thumbnail_lists`, and those files."""
    if not source.thumbnail_lists:
        return {}, set()
    ids, files = {}, set()
    for path in sorted((install.assets / source.thumbnail_lists).glob(f"*{BUNDLE_SUFFIX}")):
        files.add(path)
        for _name, tree in read(path):
            for p in tree.get("param", []):
                if p.get("Bundle") and p.get("Asset"):
                    ids.setdefault(int(p["ID"]), Thumbnail(map_key(p["Bundle"]) + BUNDLE_SUFFIX, p["Asset"]))
    return ids, files


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
                ids = {tod: int(p[f]) for f, tod in source.thumbnail_ids if int(p.get(f, -1)) >= 0}
                entry = ListEntry(source.list, int(p["No"]), p["MapName"], p.get("DisplayName") or "")
                yield p["AssetBundleName"], entry, {"outdoor": p.get("isOutdoors"), "thumbnail": thumb,
                                                    "thumbnail_ids": ids}
        elif source.layout == "studio_rows":
            no, name, bundle = source.columns
            for row in tree.get("list", []):
                cells = row.get("list", [])
                if (len(cells) <= max(source.columns) or not cells[no].strip().lstrip("-").isdigit()
                        or not cells[bundle].strip()):
                    continue  # the two header rows, and rows without a bundle
                yield cells[bundle], ListEntry(source.list, int(cells[no]), cells[name]), {}
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
