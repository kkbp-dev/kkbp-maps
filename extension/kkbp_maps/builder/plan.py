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
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .games import camera_profile
from ..bundle import Bundle
from . import shaders
from .catalogs import catalog_uuid
from .names import NameTables

OTHER_AREA = "Other"
SKYSTUDIO = "Funly/Sky Studio/Skybox/3D Standard"   # rebuilt in builder/blender/sky.py
SKY_LEFT_OUT = {"STAR_LAYER_1": "stars", "STAR_LAYER_2": "stars", "STAR_LAYER_3": "stars", "STARS_BASIC": "stars",
                "MOON_CUSTOM_TEXTURE": "the moon's texture", "SUN_CUSTOM_TEXTURE": "the sun's texture",
                "CUBEMAP_CLOUDS": "cubemap clouds", "CUBEMAP_NORMAL_CLOUDS": "cubemap clouds",
                "HORIZON_FOG": "horizon fog"}


def sky_notes(sky: dict | None) -> list[str]:
    """For the Build Report: what a Map Variant's Sky asks for that the World doesn't draw."""
    if not sky or sky["kind"] == "cubemap":
        return []
    if sky["kind"] == "procedural":
        return ["procedural skybox not drawn"]
    if sky["shader"] != SKYSTUDIO:
        return [f"sky {sky['shader']} not drawn"]
    kw = set(sky["keywords"])
    left = sorted({SKY_LEFT_OUT[k] for k in kw if k in SKY_LEFT_OUT
                   and not (k == "MOON_CUSTOM_TEXTURE" and "MOON" not in kw)
                   and not (k == "SUN_CUSTOM_TEXTURE" and "SUN" not in kw)})
    return [f"SkyStudio sky approximated: {', '.join(left)} not drawn"] if left else []
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
    from_batched: bool = False    # its source holds a batched mesh (ADR 0034)

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
    renderer_notes: Counter = field(default_factory=Counter)  # (note) -> renderers, for the Build Report
    twins: list[str] = field(default_factory=list)         # Maps of the same geometry, kept as this one (D22)
    variant_notes: Counter = field(default_factory=Counter)   # (note) -> Map Variants, for the Build Report

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
    camera: str | None = None              # a Camera Profile for every Map instead of each Map's own

    def camera_of(self, m: "MapPlan") -> str:
        """The Camera Profile that shows Map m."""
        return self.camera or m.bundle.map["camera"]

    def grade_of(self, m: "MapPlan", variant: dict) -> tuple[Bundle, dict | None]:
        """The Grade a Map Variant is shown with, and the Map Bundle that holds its LUT: the Map's own,
        unless its Camera Profile grades every Map with a LUT of its own (found by name in any Map)."""
        name = camera_profile(self.game, self.camera_of(m)).grade_lut
        if name is None:
            return m.bundle, variant["grade"]
        for b in [m.bundle] + [x.bundle for x in self.maps]:
            for tid, t in b.textures.items():
                if t["name"] == name:
                    return b, {"kind": "amplify_color", "lut": tid, "layout": "amplify_32x32"}
        raise ValueError(f"Camera Profile '{self.camera_of(m)}' grades with {name}, which no Map holds")

    def as_shown(self, m: "MapPlan", variant: dict) -> dict:
        """The Map Variant as its Camera Profile shows it: without the Map's fog where the camera replaces
        it, and with the camera's height fog ("height_fog": top and density, or None) where it has one and
        the Map's fog is drawn (ADR 0028). Where the Map sets the camera's GlobalFog itself (KKS, Map
        Bundle 0.9), its switch and top replace the profile's; the density stays the profile's. A trilight
        ambient comes as the probe Unity shades it with (trilight_sh)."""
        profile = camera_profile(self.game, self.camera_of(m))
        fog = variant["fog"] if profile.map_fog else {**variant["fog"], "enabled": False}
        height = profile.height_fog
        shown = {"top": height.top, "density": height.density} if height and fog["enabled"] else None
        own = variant["fog"].get("camera")
        if own is None and height is not None and profile.height_fog_from_map:
            shown = None   # the camera has GlobalFog, but only a Map's own settings switch it on
        if own is not None and height is not None:
            shown = {"top": own["top"], "density": height.density} if own["height"] and fog["enabled"] else None
        ambient = variant["ambient"]
        if ambient["mode"] == "trilight":
            ambient = {"mode": "skybox_sh", "intensity": 1.0, "sh": trilight_sh(ambient)}
        return {**variant, "fog": fog, "height_fog": shown, "ambient": ambient}

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


def trilight_sh(ambient: dict) -> list[float]:
    """A trilight (gradient) ambient as the 27-float probe the bundle's skybox_sh holds, in Blender's axes:
    the sky colour straight up, the equator's at the horizon and the ground's straight down, linearly in
    height between them, projected onto L2 spherical harmonics and convolved with the cosine lobe, as
    Unity makes its ambient probe from a gradient. It has no intensity multiplier (Unity's applies to the
    skybox source only). Only the z-symmetric terms are non-zero: 1, z and 3z² − 1."""
    def linear(x):   # Unity's GammaToLinearSpace: the colours are serialized sRGB-encoded
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    sky, equator, ground = ([linear(float(x)) for x in ambient[k][:3]] for k in ("sky_color", "equator_color", "ground_color"))
    steps = 2000
    out = []
    for c in range(3):
        l0 = l1 = l2 = 0.0
        for i in range(steps):
            z = -1.0 + (i + 0.5) * 2.0 / steps
            if z >= 0:
                value = equator[c] + (sky[c] - equator[c]) * z
            else:
                value = equator[c] + (ground[c] - equator[c]) * -z
            w = 2.0 * math.pi * 2.0 / steps   # dω = 2π dz
            l0 += value * 0.282095 * w
            l1 += value * 0.488603 * z * w
            l2 += value * 0.315392 * (3 * z * z - 1) * w
        # irradiance / π with A0 = π, A1 = 2π/3, A2 = π/4, back into the polynomial basis
        coeffs = [0.0] * 9
        coeffs[0] = 0.282095 * l0
        coeffs[2] = 0.488603 * l1 * 2.0 / 3.0
        coeffs[6] = 0.315392 * l2 / 4.0
        out += coeffs
    return out


def plan_library(bundles: list[Bundle], tables: NameTables, camera: str | None = None) -> LibraryPlan:
    """The plan for one Game's Map Library; `bundles` in build order, all of one Game. `camera` shows
    every Map through that Camera Profile instead of its own (the look check builds Studio's view)."""
    games = {b.game for b in bundles}
    if len(games) != 1:
        raise ValueError(f"a Map Library holds one Game's Maps; these are of {sorted(games)}")
    game = games.pop()
    maps: list[MapPlan] = []
    assets: dict[str, AssetPlan] = {}
    left_out: dict[str, AssetPlan] = {}
    used_names: dict[str, set[str]] = {"prop": set(), "structure": set(), "map": set()}
    grades: dict[str, tuple[str, str, str]] = {}

    for b in bundles:   # the Blend Mode each material is drawn with (shaders.blend_mode), once, here
        for material in b.materials.values():
            material["blend_mode"] = shaders.blend_mode(material)
    canonical = match_batched(bundles)
    by_geometry: dict[str, MapPlan] = {}
    for b in bundles:
        twin = by_geometry.get(b.map["geometry_hash"])
        if twin is not None:   # D22: a Studio Map with its story Map's geometry is that Map
            twin.twins.append(b.key)
            continue
        m = _plan_map(b, tables, used_names["map"])
        by_geometry[b.map["geometry_hash"]] = m
        roots = _all_roots(b)
        keys = candidate_keys(b, canonical)
        maps.append(m)
        for v in b.variants:
            g = v["grade"]
            if g and g["lut"] not in grades:
                grades[g["lut"]] = (g["lut"], b.textures[g["lut"]]["name"], b.key)
        for c, key in zip(b.candidates, keys):
            first = c["placements"][0]
            asset = assets.get(key) or left_out.get(key)
            if asset is None:
                asset = _plan_asset(b, m, c, tables, used_names)
                asset.hash = key
                asset.from_batched = key != c["hash"]
                drawn = any(m.drawn(n) for n in _asset_nodes(b, first, roots))
                (assets if drawn else left_out)[key] = asset
            elif asset.from_batched and key == c["hash"]:   # build it from an unbatched copy (ADR 0034)
                asset.source, asset.from_batched = (b.key, first), False
            if b.key not in asset.maps:
                asset.maps.append(b.key)
            asset.placements += len(c["placements"])
            asset.outdoor.add(m.outdoor)
            for root in c["placements"]:
                m.roots[root] = key
    return LibraryPlan(game, tables, maps, assets, left_out, list(grades.values()), camera)


def match_batched(bundles: list[Bundle]) -> dict[str, str]:
    """Batched mesh id -> the mesh it matches in any of the bundles (ADR 0034): an unbatched one where
    there is one, else the first batched one in build order. Meshes that match nothing are left out."""
    from ..bundle.matching import candidates_key, meshes_match
    groups: dict[tuple, list[tuple[Bundle, dict]]] = {}
    for b in bundles:
        for mesh in b.meshes.values():
            groups.setdefault(candidates_key(mesh), []).append((b, mesh))
    out: dict[str, str] = {}
    for group in groups.values():
        if not any(m.get("batched") for _, m in group):
            continue
        data = {}
        def bytes_of(b, m):
            if m["id"] not in data:
                data[m["id"]] = b.mesh_path(m["id"]).read_bytes()
            return data[m["id"]]
        ordered = [x for x in group if not x[1].get("batched")] + [x for x in group if x[1].get("batched")]
        for b, mesh in group:
            if not mesh.get("batched") or mesh["id"] in out:
                continue
            for ob, other in ordered:
                if other["id"] == mesh["id"]:
                    break   # nothing earlier matches: it stands for itself
                if meshes_match(mesh, bytes_of(b, mesh), other, bytes_of(ob, other)):
                    out[mesh["id"]] = out.get(other["id"], other["id"])
                    break
    return out


def candidate_keys(b: Bundle, canonical: dict[str, str]) -> list[str]:
    """Each Candidate's key in the Map Library: its hash, or, where its shape holds batched meshes that
    match others (ADR 0034), the hash of its shape with those meshes replaced."""
    if not any(n.get("renderer", {}).get("mesh") in canonical for n in b.nodes):
        return [c["hash"] for c in b.candidates]
    from ..bundle.hashing import candidate_shapes
    nodes = [dict(n, renderer={**n["renderer"], "mesh": canonical.get(n["renderer"]["mesh"], n["renderer"]["mesh"])})
             if "renderer" in n else n for n in b.nodes]
    roots = {r for c in b.candidates for r in c["placements"]}
    shapes = candidate_shapes(nodes, roots)
    return [shapes[c["placements"][0]] for c in b.candidates]


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
        for note in renderer_notes(b, n, tiers):
            m.renderer_notes[note] += 1
    for mid, material in b.materials.items():
        for note in material_notes(material):
            m.notes[note] += 1
    for v in b.variants:
        for note in sky_notes(v["sky"]):
            m.variant_notes[note] += 1
    return m


def passes(draws, tiers) -> list[dict]:
    """A renderer's draws as passes over its mesh: each pass draws a submesh at most once, so one Blender
    object with a material slot per submesh holds it. The first pass takes each submesh's first draw; a
    submesh drawn again (Unity draws a material slot past the last submesh over that submesh once more)
    goes into a later pass, an extra object over the same mesh. A submesh no draw names isn't drawn.
    Returns one {submesh: (draw, tier)} per pass."""
    out: list[dict] = []
    for draw, tier in zip(draws, tiers):
        for p in out:
            if draw["submesh"] not in p:
                p[draw["submesh"]] = (draw, tier)
                break
        else:
            out.append({draw["submesh"]: (draw, tier)})
    return out


def renderer_notes(b: Bundle, node: dict, tiers) -> list[str]:
    """What a renderer's draws need beyond one object with a slot per submesh, for the Build Report."""
    r = node["renderer"]
    notes = []
    if len(passes(r["draws"], tiers)) > 1:
        notes.append("a submesh drawn twice: the second pass is an extra object over the same mesh")
    if len({d["submesh"] for d in r["draws"]}) < len(b.meshes[r["mesh"]]["index_counts"]):
        notes.append("submeshes the game doesn't draw: left out")
    return notes


def koikano_tint(game: str, variant: dict) -> tuple[float, float, float]:
    """The light tint Koikano's map shader gives its albedo in a Map Variant: saturate(0.6 · L + 0.4),
    mixed towards max(0.6 · L + 0.4, the ambient shadow colour) by the ramp's corner (games.KOIKANO). L is
    _LightColor0, the main directional light's colour as the shader receives it: the brightest directional
    light of the Map Variant."""
    from .games import KOIKANO, light_convention
    k = KOIKANO.get(game)
    if k is None:
        return (1.0, 1.0, 1.0)

    def linear(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    linear_intensity = light_convention(game).lights_use_linear_intensity
    best = (0.0, 0.0, 0.0)
    for light in variant["lights"]:
        if light["type"] != "directional" or light["mode"] == "baked":
            continue
        c, i = light["color"][:3], light["intensity"]
        rgb = tuple(linear(x) * i for x in c) if linear_intensity else tuple(linear(x * i) for x in c)
        if sum(rgb) > sum(best):
            best = rgb
    out = []
    for c in range(3):
        raw = 0.6 * best[c] + 0.4
        out.append((1 - k.ramp_corner) * min(max(raw, 0.0), 1.0) + k.ramp_corner * max(raw, k.ambient_shadow[c]))
    return tuple(out)


def material_notes(material: dict) -> list[str]:
    """What a rebuilt material loses, for the Build Report."""
    t = shaders.tier(material["shader"])
    if t.model == "koikano":
        used = {x["raw"] for x in material["textures"]}
        lost = sorted(used & {"_LineMask", "_DetailMask", "_AnimationMask"})
        if lost or material["floats"].get("_SpecularPower", 0.0) > 0 or material["floats"].get("_EmissionPower", 0.0) > 0:
            return ["Koikano's masks, specular and emission aren't drawn"]
        return []
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
