"""Builds a Map Library from a plan, a file at a time (ADR 0022).

    build_library(plan, "out/KK Maps")                  # everything, in this Blender
    build_step(plan, "out/KK Maps", "map:map/scene/1f")  # one step, as the background build runs them

Steps: `map:<key>` writes Maps/<Map>.blend (kept as it is when its Map Bundle and the Builder haven't
changed), `assets` writes Props.blend and Structures.blend from every Map Bundle, `finish` writes the
catalog file, build.json and the Build Report. Each file starts from Blender's factory settings, is
saved with relative image paths, and holds its own copies of everything it uses.

Run from a shell (the harness does), with this repository's extension/ on Blender's path:

    blender -b --factory-startup --python tools/blender_build.py -- --library OUT --bundles B... [--step S]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import bpy

from ... import bundle as bundle_contract
from ... import compat
from .. import NAME, VERSION
from ..catalogs import FILE_NAME as CATALOG_FILE, catalog_file
from ..names import NameTables
from ..plan import LibraryPlan, plan_library
from ..report import build_report, markdown
from . import materials as mats
from . import previews
from .scene import FileBuilder, build_asset, build_map, mark_asset

STATE_FILE = "build.json"
PROPS_FILE, STRUCTURES_FILE = "Props.blend", "Structures.blend"


def steps(plan: LibraryPlan) -> list[str]:
    return [f"map:{m.key}" for m in plan.maps] + ["assets", "finish"]


def build_library(plan: LibraryPlan, library, *, previews_on: bool = True, log=print):
    for s in steps(plan):
        build_step(plan, library, s, previews_on=previews_on, log=log)


def build_step(plan: LibraryPlan, library, step: str, *, previews_on: bool = True, log=print) -> dict:
    compat.require()
    library = Path(library)
    library.mkdir(parents=True, exist_ok=True)
    state = _state(library)
    if step.startswith("map:"):
        m = plan.map_of(step[4:])
        entry = state["maps"].get(m.key)
        target = library / m.file
        if entry and entry["digest"] == m.digest and entry["file"] == m.file and target.is_file() \
                and state.get("builder") == VERSION:
            log(f"{m.key}: unchanged, kept")
            result = {"kept": True}
        else:
            result = _map_file(plan, m, library, previews_on)
            log(f"{m.key}: wrote {m.file}")
        state["maps"][m.key] = {"digest": m.digest, "file": m.file, **result}
    elif step == "assets":
        state["files"] = _asset_files(plan, library, previews_on)
        log(f"wrote {PROPS_FILE} and {STRUCTURES_FILE}")
    elif step == "finish":
        (library / CATALOG_FILE).write_text(catalog_file(plan.catalogs()), encoding="utf-8", newline="\n")
        results = {k: v for k, v in state["maps"].items()}
        results["files"] = state.get("files", {})
        report = build_report(plan, results)
        (library / "build-report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n",
                                                   encoding="utf-8", newline="\n")
        (library / "build-report.md").write_text(markdown(report), encoding="utf-8", newline="\n")
        log("wrote the catalogs and the Build Report")
    else:
        raise ValueError(f"no build step {step!r}")
    state["builder"] = VERSION
    state["schema_version"] = bundle_contract.SCHEMA_VERSION
    _save_state(library, state)
    return state


def _state(library: Path) -> dict:
    try:
        state = json.loads((library / STATE_FILE).read_text(encoding="utf-8"))
        if state.get("builder") == VERSION and state.get("schema_version") == bundle_contract.SCHEMA_VERSION:
            state.setdefault("maps", {})
            return state
    except (OSError, ValueError):
        pass
    return {"maps": {}}


def _save_state(library: Path, state: dict):
    tmp = library / (STATE_FILE + ".partial")
    tmp.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(library / STATE_FILE)


# --- files ------------------------------------------------------------------------------------------

def _new_file():
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    scene = bpy.context.scene
    scene.render.engine = compat.eevee_engine()
    scene.view_settings.view_transform = "Standard"  # D4
    scene.view_settings.look = "None"
    bpy.context.preferences.filepaths.save_version = 0
    return scene


def _save(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    bpy.ops.file.make_paths_relative()
    bpy.ops.wm.save_mainfile(compress=True)


def _map_file(plan: LibraryPlan, m, library: Path, previews_on: bool) -> dict:
    scene = _new_file()
    fb = FileBuilder(mats.Images(library))
    collections = build_map(plan, m, fb)
    catalog = plan.catalogs()[m.catalog]
    with_preview = 0
    for coll, vp in zip(collections, m.variants):
        scene.collection.children.link(coll)
        world = bpy.data.worlds[coll["kkbp_maps_world"]]
        tags = plan.variant_tags(m, vp)
        description = f"{m.name} ({m.key}) from {plan.game}"
        mark_asset(coll, catalog, tags, description)
        mark_asset(world, catalog, tags, f"The World of {vp.name}")
        if previews_on and vp.thumbnail and previews.from_image_file(coll, m.bundle.texture_path(vp.thumbnail)):
            previews.from_image_file(world, m.bundle.texture_path(vp.thumbnail))
            with_preview += 1
    for layer_coll in list(bpy.context.view_layer.layer_collection.children)[1:]:
        layer_coll.exclude = True   # the file opens on its first Map Variant
    scene.world = bpy.data.worlds[collections[0]["kkbp_maps_world"]]
    scene["kkbp_maps_map"] = m.key
    dropped = sum(x.dropped_triangles for x in fb.meshes.values())
    _save(library / m.file)
    return {"kept": False, "variants": len(collections), "previews": with_preview, "dropped_triangles": dropped}


def _day_grade(plan: LibraryPlan):
    """The Grade standalone Props and Structures show: the first Map's day Grade (ADR 0002)."""
    for m in plan.maps:
        for v in m.bundle.variants:
            if "day" in v["times_of_day"] and v["grade"]:
                return m.bundle, v["grade"]
    return None, None


def _asset_files(plan: LibraryPlan, library: Path, previews_on: bool) -> dict:
    out = {}
    for name, kind in ((PROPS_FILE, "prop"), (STRUCTURES_FILE, "structure")):
        scene = _new_file()
        fb = FileBuilder(mats.Images(library))
        grade_bundle, grade_record = _day_grade(plan)
        grade = fb.grade(grade_bundle, grade_record) if grade_bundle else None
        catalogs = plan.catalogs()
        cache: dict = {}
        made = []
        for asset in plan.assets.values():
            if asset.kind != kind:
                continue
            coll = build_asset(plan, asset, fb, cache, grade)
            mark_asset(coll, catalogs[asset.catalog], plan.tags(asset),
                       f"{asset.game_name} ({asset.rule}{', overridden' if asset.overridden else ''}) "
                       f"in {len(asset.maps)} Map{'s' if len(asset.maps) > 1 else ''}")
            made.append(coll)
        rendered = previews.render(made) if previews_on else 0
        scene["kkbp_maps_assets"] = kind
        _save(library / name)
        out[name] = {"assets": len(made), "previews": rendered}
    return out


# --- the command line ---------------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kkbp-maps build", description="Builds a Map Library from Map Bundles.")
    parser.add_argument("--library", required=True, help="the Map Library folder, such as out/KK Maps")
    parser.add_argument("--bundles", nargs="+", required=True, help="Map Bundle folders, in build order")
    parser.add_argument("--step", action="append", help="map:<key>, assets or finish; all of them by default")
    parser.add_argument("--no-previews", action="store_true")
    parser.add_argument("--camera", help="show every Map through this Camera Profile (game or studio), for the look check")
    args = parser.parse_args(argv)
    bundles = [bundle_contract.read(p) for p in args.bundles]
    plan = plan_library(bundles, NameTables.load(bundles[0].game), camera=args.camera)
    for s in args.step or steps(plan):
        build_step(plan, args.library, s, previews_on=not args.no_previews,
                   log=lambda text: print(f"  {text}", flush=True))
    print(f"{NAME} {VERSION}: done", flush=True)
    return 0
