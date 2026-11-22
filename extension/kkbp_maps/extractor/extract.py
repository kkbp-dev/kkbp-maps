"""Extracting a Map: read its Scene Bundle, resolve what the game would show, and write its Map Bundle.

A bundle is written into `<out>/<Game>/<key>.partial/`, Manifest last, and then renamed into place,
so a folder at the final path is always finished. extract_map skips a Map whose bundle is fresh: the
same Schema Version, Extractor version and options, and every source file unchanged.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import bundle
from ..bundle.hashing import geometry_hash, shortest32
from . import NAME, VERSION
from .candidates import candidates
from .games import Install
from .lightmaps import lightmap_set
from .maplist import MapSource, camera_profile, thumbnail_names
from .materials import Materials
from .meshes import Meshes
from .scene import Graph, Node, Unsupported, node_records, read_graph, walk
from .textures import Textures
from .variants import variants

DATA_FILES = ("map", "scene", "meshes", "materials", "textures", "lightmaps", "variants", "assets")


@dataclass(frozen=True)
class Options:
    max_texture_size: int | None = None

    def record(self) -> dict:
        return {"max_texture_size": self.max_texture_size}


def bundle_path(out: Path, install: Install, m: MapSource) -> Path:
    return Path(out) / install.game.id / Path(*m.key.split("/"))


def extract_map(install: Install, m: MapSource, out, options: Options = Options(), *, force: bool = False,
                store_factory=None, log=print) -> Path:
    """Writes the Map Bundle of `m` under `out` and returns its folder; a fresh one is kept as it is."""
    target = bundle_path(out, install, m)
    sources = source_files(install, m)
    if not force and is_fresh(target, install, sources, options):
        log(f"{m.key}: fresh, kept")
        return target
    partial = target.with_name(target.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    if store_factory is None:
        from .unity import UnityStore
        store_factory = UnityStore
    store = store_factory(m.bundle)
    try:
        write_bundle(install, m, store, partial, options, sources)
    finally:
        close = getattr(store, "close", None)
        if close:
            close()
    problems = bundle.check(partial)
    if problems:
        raise BundleError(m.key, problems)
    if target.exists():
        shutil.rmtree(target)
    partial.rename(target)
    log(f"{m.key}: written")
    return target


class BundleError(RuntimeError):
    def __init__(self, key: str, problems: list[str]):
        self.problems = problems
        shown = "\n  ".join(problems[:20])
        more = f"\n  … and {len(problems) - 20} more" if len(problems) > 20 else ""
        super().__init__(f"{key}: the bundle breaks the contract:\n  {shown}{more}")


def write_bundle(install: Install, m: MapSource, store, folder: Path, options: Options, sources: list[Path]):
    game = install.game
    for ref in store.refs("LightProbes"):  # the bundle has no place for them yet (map-bundle.md, "Later Games")
        if store.tree(ref).get("m_Data", {}).get("m_Positions"):
            raise Unsupported("the Map has light probes")
    graph = read_graph(store, game)
    textures = Textures(folder / "textures", options.max_texture_size)
    meshes = Meshes(folder / "meshes")
    materials = Materials(textures, game)
    w = walk(graph, lambda ref: meshes.try_add(store, ref) is not None)
    queues = _render_queues(graph)
    nodes = node_records(w, graph, lambda ref: meshes.add(store, ref), lambda n: draws(store, n, meshes, materials, queues))
    lm = lightmap_set(graph, w, meshes, textures)
    vs = variants(graph, w, textures, lm["id"] if lm else None)
    assets = candidates(nodes, game.prefixes, game.containers)
    map_record = {
        "key": m.key,
        "times_of_day": list(game.times_of_day),
        "outdoor": m.outdoor if m.outdoor is not None else bool(w.domes),
        "camera": camera_profile(install, m),
        "list_entries": [e.record() for e in m.entries],
        "thumbnails": thumbnails(install, m, textures),
        "geometry_hash": geometry_hash(nodes),
        "skipped": skipped(w.census.counts),
    }
    data = {
        "map": map_record,
        "scene": {"nodes": nodes},
        "meshes": {"meshes": list(meshes.records.values())},
        "materials": {"materials": list(materials.records.values())},
        "textures": {"textures": list(textures.records.values())},
        "lightmaps": {"sets": [lm] if lm else []},
        "variants": {"variants": vs},
        "assets": {"candidates": assets},
    }
    for stem in DATA_FILES:
        write_json(folder / f"{stem}.json", data[stem])
    total = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    manifest = {
        "game": game.id,
        "schema_version": bundle.SCHEMA_VERSION,
        "extractor": {"name": NAME, "version": VERSION},
        "extracted_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "map": m.key,
        "options": options.record(),
        "sources": [source_record(install, p) for p in sources],
        "contents": {
            "nodes": len(nodes), "meshes": len(meshes.records), "materials": len(materials.records),
            "textures": len(textures.records), "lightmap_sets": 1 if lm else 0, "variants": len(vs),
            "candidates": len(assets), "placements": sum(len(c["placements"]) for c in assets), "bytes": total,
        },
    }
    write_json(folder / "manifest.json", manifest)


def _render_queues(graph: Graph) -> dict:
    """renderer Ref -> {material slot: render queue} from SetRenderQueue, which sets them in Awake."""
    store = graph.store
    out = {}
    for mb in graph.behaviours.get("SetRenderQueue", []):
        t = store.tree(mb)
        obj = graph.obj_of(mb)
        renderer = obj.component("MeshRenderer") if obj else None
        if renderer is None or not t.get("m_Enabled", 1):
            continue
        slots = len(store.tree(renderer).get("m_Materials", []))
        data = t.get("m_queueDatas", [])
        queues = {}
        for i in range(min(slots, len(data))):  # as Awake loops, indexing the slots by each entry's id
            if 0 <= data[i]["id"] < slots:
                queues[data[i]["id"]] = int(data[i]["m_queues"])
        out[renderer] = queues
    return out


def draws(store, node: Node, meshes: Meshes, materials: Materials, queues: dict) -> list[dict]:
    """A renderer's draws as Unity pairs submeshes with material slots: slot i draws submesh i, a slot
    past the last submesh draws the last one again, a submesh past the last slot isn't drawn, and an
    empty slot draws nothing."""
    r = node.renderer
    count = meshes.submesh_count(r.mesh)
    overrides = queues.get(r.ref, {})
    out = []
    for i, material in enumerate(r.materials):
        if material is None or not store.is_loaded(material):
            continue
        out.append({"submesh": min(i, count - 1), "material": materials.add(store, material, overrides.get(i))})
    if not out:
        raise Unsupported(f"{node.obj.name} draws nothing")
    return out


def thumbnails(install: Install, m: MapSource, textures: Textures) -> list[dict]:
    if m.thumbnail is None:
        return []
    from .unity import sprite_textures

    names = thumbnail_names(install, m.thumbnail) or {}
    found = sprite_textures(install.assets / m.thumbnail.bundle, set(names.values()) | {m.thumbnail.asset})
    by_texture: dict[str, list[str]] = {}
    for tod in install.game.times_of_day:
        name = names.get(tod)
        if name in found:
            pixels, color_space = found[name]
            by_texture.setdefault(textures.thumbnail(pixels, name, color_space), []).append(tod)
    if not by_texture and m.thumbnail.asset in found:  # a name without a Time of Day suffix
        pixels, color_space = found[m.thumbnail.asset]
        by_texture[textures.thumbnail(pixels, m.thumbnail.asset, color_space)] = list(install.game.times_of_day)
    return [{"times_of_day": tods, "texture": tid} for tid, tods in by_texture.items()]


def skipped(counts: dict[str, int]) -> list[dict]:
    order = bundle.closed_sets()["skip-reason"]
    return [{"reason": r, "count": counts[r]} for r in order if counts.get(r)]


# --- sources and freshness -------------------------------------------------------------------------

def source_files(install: Install, m: MapSource) -> list[Path]:
    files = [m.bundle] + sorted(m.list_files)
    if m.thumbnail is not None:
        files.append(install.assets / m.thumbnail.bundle)
    return files


def source_record(install: Install, path: Path) -> dict:
    return {"path": install.relative(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def is_fresh(target: Path, install: Install, sources: list[Path], options: Options) -> bool:
    try:
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if (manifest.get("schema_version") != bundle.SCHEMA_VERSION or manifest.get("options") != options.record()
            or manifest.get("extractor", {}).get("version") != VERSION):
        return False
    recorded = {s["path"]: s for s in manifest.get("sources", [])}
    if set(recorded) != {install.relative(p) for p in sources}:
        return False
    for p in sources:
        s = recorded[install.relative(p)]
        if not p.is_file() or p.stat().st_size != s["bytes"] or sha256(p) != s["sha256"]:
            return False
    return True


# --- JSON ----------------------------------------------------------------------------------------

def write_json(path: Path, value):
    """Bundle JSON: UTF-8 without a byte order mark, floats as float32 shortest decimals."""
    path.write_text(json.dumps(_shortest(value), ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                    newline="\n")


def _shortest(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return shortest32(value + 0.0)
    if isinstance(value, list):
        return [_shortest(v) for v in value]
    if isinstance(value, dict):
        return {k: _shortest(v) for k, v in value.items()}
    return value
