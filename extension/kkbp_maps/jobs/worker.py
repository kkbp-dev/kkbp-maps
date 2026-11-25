"""The Extractor's side of a Build, run by the driver on Blender's own Python, never inside Blender:

    <python> -I worker.py --extension <folder> [--site <folder>]... --result <file> list --game-folder <install>
    <python> -I worker.py ... extract --game-folder <install> --out <Bundle Folder> --key <Map> [--max-texture-size N]

`--extension` is the folder holding the kkbp_maps package and each `--site` a folder Blender installed
the extension's wheels into (deps.site_folders()). They go on the path before anything of the
extension is imported, since `-I` leaves both out. The result is written as JSON to `--result`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kkbp-maps worker")
    parser.add_argument("--extension", required=True)
    parser.add_argument("--site", action="append", default=[])
    parser.add_argument("--result", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--game-folder", required=True)
    extract = sub.add_parser("extract")
    extract.add_argument("--game-folder", required=True)
    extract.add_argument("--out", required=True)
    extract.add_argument("--key", required=True)
    extract.add_argument("--max-texture-size", type=int)
    args = parser.parse_args(argv)
    sys.path[:0] = [args.extension, *args.site]

    from kkbp_maps.extractor.games import NotAGameFolder, UnsupportedGame, detect

    try:
        install = detect(args.game_folder)
    except (NotAGameFolder, UnsupportedGame) as e:
        return _result(args.result, {"error": str(e)}, 2)
    try:
        if args.command == "list":
            return _result(args.result, list_result(install), 0)
        return _result(args.result, extract_result(install, args), 0)
    except Exception as e:   # the whole traceback goes to the log; its last line to the Build Report
        import traceback

        traceback.print_exc()
        return _result(args.result, {"error": f"{type(e).__name__}: {e}"}, 1)


def list_result(install) -> dict:
    from kkbp_maps.extractor.maplist import camera_profile, list_maps

    maps, missing = list_maps(install)
    return {"game": install.game.id, "maps": [{
        "key": m.key,
        "lists": sorted(m.lists),
        "list_names": [e.name for e in m.entries],
        "outdoor": m.outdoor,
        "camera": camera_profile(install, m),
        "bytes": m.bundle.stat().st_size,
    } for m in maps], "missing": missing}


def extract_result(install, args) -> dict:
    from kkbp_maps.extractor.extract import Options, extract_map
    from kkbp_maps.extractor.maplist import list_maps

    maps, _ = list_maps(install)
    m = next((m for m in maps if m.key == args.key), None)
    if m is None:
        return {"error": f"{args.key} isn't a Map of this install"}
    kept = []
    path = extract_map(install, m, Path(args.out), Options(max_texture_size=args.max_texture_size),
                       log=lambda text: (kept.append(text.endswith("fresh, kept")), print(f"  {text}", flush=True)))
    return {"bundle": str(path), "kept": any(kept)}


def _result(path: str, result: dict, code: int) -> int:
    if "error" in result:
        print(result["error"], flush=True)
        code = code or 2
    Path(path).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
