"""The build plan: what a Map Library will hold, decided from the Map Bundles and the Name Tables
without Blender. Never imports bpy.

- **Assets.** Each Candidate is a Prop or a Structure by its kind, or by an override (ADR 0004). It is
  kept once per Map Library by its Content Hash, built from its first Placement in build order, and
  tagged with every Map it is placed in. A Candidate whose renderers are all skipped is no asset.
- **Map Variants.** One asset each, named "<Map>, <Time of Day>", or "<Map>" alone where one Map
  Variant covers all of the Map's Times of Day (ADR 0009).
- **Draws.** Every renderer's draws get their material's Shader Tier; a skipped draw is left out, and
  a renderer with nothing left is an empty in its Map Variant.
- **Names** are unique per kind of asset across the Library; a repeat gets " (2)", " (3)", ...
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..bundle import Bundle
from . import shaders
from .catalogs import catalog_uuid
from .names import NameTables

OTHER_AREA = "Other"
UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class AssetPlan:
    hash: str
    kind: str                     # "prop" or "structure", after the overrides
    rule: str                     # the Extractor's Candidate rule
    overridden: bool
    game_name: str                # its first Placement root's game name
    name: str
    category: str                 # a Prop's category, a Structure's area
    unknown_words: tuple[str, ...]
    source: tuple[str, int]       # (Map key, Placement root) it is built from
    maps: list[str] = field(default_factory=list)
    placements: int = 0
    outdoor: set[bool] = field(default_factory=set)

    @property
    def catalog(self) -> str:
        return f"{'Props' if self.kind == 'prop' else 'Structures'}/{self.category}"


@dataclass
class VariantPlan:
    id: str
    name: str
    times_of_day: list[str]
    thumbnail: str | None         # the game's thumbnail for the first of its Times of Day that has one


@dataclass
class MapPlan:
    key: str
    bundle: Bundle
    name: str
    named: bool                   # whether the Name Tables know the Map
    area: str
    outdoor: bool
    file: str                     # relative to the Map Library: Maps/<name>.blend
    digest: str                   # the SHA-256 of the bundle's Manifest, for freshness
    variants: list[VariantPlan]
    draws: dict[int, list[shaders.Tier]]       # renderer node -> each draw's tier
    roots: dict[int, str]                      # Placement root -> asset hash
    shader_use: Counter = field(default_factory=Counter)   # (shader, tier) -> draws
    shader_materials: dict = field(default_factory=dict)   # (shader, tier) -> material ids
    notes: Counter = field(default_factory=Counter)        # (note) -> materials, for the Build Report

    @property
    def catalog(self) -> str:
        return f"Maps/{self.area}"

    def drawn(self, node: int) -> bool:
        return any(t.level != shaders.SKIPPED for t in self.draws.get(node, ()))


@dataclass
class LibraryPlan:
    game: str
    tables: NameTables
    maps: list[MapPlan]
    assets: dict[str, AssetPlan]           # by Content Hash, in order of first appearance
    left_out_assets: dict[str, AssetPlan]  # Candidates with nothing drawn
    grades: list[tuple[str, str, str]]     # (LUT texture id, LUT name, Map key) of each distinct Grade

    def props(self) -> list[AssetPlan]:
        return [a for a in self.assets.values() if a.kind == "prop"]

    def structures(self) -> list[AssetPlan]:
        return [a for a in self.assets.values() if a.kind == "structure"]

    def catalogs(self) -> dict[str, str]:
        """Every catalog path the Library uses, parents included, with its UUID."""
        paths = {m.catalog for m in self.maps} | {a.catalog for a in self.assets.values()}
        full = set()
        for p in paths:
            parts = p.split("/")
            full.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
        return {p: catalog_uuid(self.game, p) for p in sorted(full)}

    def map_of(self, key: str) -> MapPlan:
        return next(m for m in self.maps if m.key == key)

    def tags(self, asset: AssetPlan) -> list[str]:
        maps = [self.map_of(k).name for k in asset.maps]
        places = ["Outdoor" if o else "Indoor" for o in sorted(asset.outdoor, reverse=True)]
        return _unique([self.game, *maps, *places, asset.category])

    def variant_tags(self, m: MapPlan, v: VariantPlan) -> list[str]:
        return _unique([self.game, m.name, *(self.tables.time_of_day(t) for t in v.times_of_day),
                        "Outdoor" if m.outdoor else "Indoor"])


def plan_library(bundles: list[Bundle], tables: NameTables) -> LibraryPlan:
    """The plan for one Game's Map Library; `bundles` in build order, all of one Game."""
    games = {b.game for b in bundles}
    if len(games) != 1:
        raise ValueError(f"a Map Library holds one Game's Maps; these are of {sorted(games)}")
    game = games.pop()
    maps: list[MapPlan] = []
    assets: dict[str, AssetPlan] = {}
    left_out: dict[str, AssetPlan] = {}
    used_names: dict[str, set[str]] = {"prop": set(), "structure": set(), "map": set()}
    grades: dict[str, tuple[str, str, str]] = {}

    for b in bundles:
        m = _plan_map(b, tables, used_names["map"])
        roots = _all_roots(b)
        maps.append(m)
        for v in b.variants:
            g = v["grade"]
            if g and g["lut"] not in grades:
                grades[g["lut"]] = (g["lut"], b.textures[g["lut"]]["name"], b.key)
        for c in b.candidates:
            first = c["placements"][0]
            asset = assets.get(c["hash"]) or left_out.get(c["hash"])
            if asset is None:
                asset = _plan_asset(b, m, c, tables, used_names)
                drawn = any(m.drawn(n) for n in _asset_nodes(b, first, roots))
                (assets if drawn else left_out)[c["hash"]] = asset
            if b.key not in asset.maps:
                asset.maps.append(b.key)
            asset.placements += len(c["placements"])
            asset.outdoor.add(m.outdoor)
            for root in c["placements"]:
                m.roots[root] = c["hash"]
    return LibraryPlan(game, tables, maps, assets, left_out, list(grades.values()))


def _plan_map(b: Bundle, tables: NameTables, used: set[str]) -> MapPlan:
    name = tables.map_name(b.key)
    named = name is not None
    if not named:
        name = b.map["list_entries"][0]["name"]
    name = _unique_name(name, used)
    area = tables.map_area(b.key) or OTHER_AREA
    variants = []
    for v in b.variants:
        covers_all = v["times_of_day"] == b.map["times_of_day"]
        vname = name if covers_all else f"{name}, {', '.join(tables.time_of_day(t) for t in v['times_of_day'])}"
        thumb = next((t["texture"] for tod in v["times_of_day"] for t in b.map["thumbnails"]
                      if tod in t["times_of_day"]), None)
        variants.append(VariantPlan(v["id"], vname, list(v["times_of_day"]), thumb))
    m = MapPlan(key=b.key, bundle=b, name=name, named=named, area=area, outdoor=b.map["outdoor"],
                file=str(PurePosixPath("Maps") / f"{safe_file_name(name)}.blend"),
                digest=hashlib.sha256((b.root / "manifest.json").read_bytes()).hexdigest(),
                variants=variants, draws={}, roots={})
    for n in b.nodes:
        r = n.get("renderer")
        if not r:
            continue
        tiers = []
        for d in r["draws"]:
            material = b.materials[d["material"]]
            t = shaders.tier(material["shader"])
            tiers.append(t)
            m.shader_use[(material["shader"], t)] += 1
            m.shader_materials.setdefault((material["shader"], t), set()).add(material["id"])
        m.draws[n["id"]] = tiers
    for mid, material in b.materials.items():
        for note in material_notes(material):
            m.notes[note] += 1
    return m


def material_notes(material: dict) -> list[str]:
    """What a rebuilt Standard material loses, for the Build Report."""
    t = shaders.tier(material["shader"])
    if t.model != "standard":
        return []
    notes = []
    if "_PARALLAXMAP" in material["keywords"]:
        notes.append("parallax (height map) ignored")
    return notes


def _plan_asset(b: Bundle, m: MapPlan, c: dict, tables: NameTables, used: dict[str, set[str]]) -> AssetPlan:
    root = c["placements"][0]
    game_name = b.nodes[root]["name"]
    o = tables.override(game_name, c["hash"])
    kind = (o.kind if o and o.kind else c["kind"])
    n = tables.name(game_name)
    if kind == "prop":
        category = (o.category if o and o.category else tables.category(n))
    else:
        category = (o.category if o and o.category else m.area)
    base = o.name if o and o.name else n.english
    name = _unique_name(base, used[kind])
    return AssetPlan(hash=c["hash"], kind=kind, rule=c["rule"], overridden=bool(o and o.kind and o.kind != c["kind"]),
                     game_name=game_name, name=name, category=category, unknown_words=n.unknown,
                     source=(b.key, root))


def _all_roots(b: Bundle) -> set[int]:
    return {r for c in b.candidates for r in c["placements"]}


def asset_nodes(b: Bundle, root: int) -> list[int]:
    """The nodes a Prop or Structure asset is made of: its Placement root and everything under it,
    leaving out sky nodes and the subtrees of other Placements (the Candidate hash's parts)."""
    return _asset_nodes(b, root, _all_roots(b))


def _asset_nodes(b: Bundle, root: int, roots: set[int]) -> list[int]:
    out, stack = [], [root]
    while stack:
        i = stack.pop()
        out.append(i)
        for c in reversed(b.children[i]):
            if not b.nodes[c].get("sky") and c not in roots:
                stack.append(c)
    return out


def _unique_name(name: str, used: set[str]) -> str:
    candidate, n = name, 2
    while candidate in used:
        candidate = f"{name} ({n})"
        n += 1
    used.add(candidate)
    return candidate


def _unique(values):
    seen, out = set(), []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def safe_file_name(name: str) -> str:
    """A name usable as a file name on Windows, macOS and Linux."""
    return UNSAFE_FILE_CHARS.sub("_", name).strip(" .") or "_"
