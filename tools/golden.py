"""Makes the Golden Maps from your own install, checks them, and compares them with the snapshot.

Usage (on a Python with UnityPy, such as KKBP's dev venv):

    ../kkbp/importer/.venv/bin/python -I tools/golden.py            # extract what is stale, check, compare
    ... tools/golden.py --force                                     # extract every Golden Map again
    ... tools/golden.py --update-snapshot                           # record the snapshot after an intended change
    ... tools/golden.py --maps map/scene/park                       # only some Maps

The Golden Maps go to golden/<Game>/ (ignored by git; ADR 0007). Each Map is extracted in a process of
its own, watched: it is stopped if it grows past --max-rss-gb, or if the machine runs low on memory or
swap, before the desktop would freeze (extension/kkbp_maps/jobs/memory.py; the swap rule is Linux only). The snapshot, tests/snapshots/extract/<Game>.json, holds
counts, hashes and names only, never game content.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "extension"))
sys.path.insert(0, str(REPO / "extension" / "kkbp_maps"))
sys.path.insert(0, str(REPO / "tools"))

from kkbp_maps.jobs.memory import Limits, run_watched  # noqa: E402

from golden_maps import GAME_FOLDERS, GOLDEN  # noqa: E402
SNAPSHOTS = REPO / "tests" / "snapshots" / "extract"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game", default="KK", choices=sorted(GOLDEN))
    parser.add_argument("--games-dir", default=os.environ.get("KKBP_GAMES_DIR", str(REPO.parent / "games")))
    parser.add_argument("--out", default=str(REPO / "golden"))
    parser.add_argument("--maps", nargs="*", help="Map keys; the Game's Golden Maps by default")
    parser.add_argument("--force", action="store_true", help="extract even fresh bundles again")
    parser.add_argument("--max-texture-size", type=int, default=None)
    parser.add_argument("--update-snapshot", action="store_true")
    parser.add_argument("--max-rss-gb", type=float, default=3.0)
    parser.add_argument("--min-available-gb", type=float, default=1.5)
    parser.add_argument("--min-swap-free-gb", type=float, default=6.0)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return worker(args)

    game_root = Path(args.games_dir) / GAME_FOLDERS[args.game]
    if not game_root.is_dir():
        print(f"{game_root} isn't there: no {args.game} install, so no Golden Maps to make")
        return 0
    keys = args.maps or GOLDEN[args.game]
    failed = False
    for key in keys:
        cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", key, "--game", args.game,
               "--games-dir", args.games_dir, "--out", args.out]
        if args.force:
            cmd.append("--force")
        if args.max_texture_size:
            cmd += ["--max-texture-size", str(args.max_texture_size)]
        start = time.time()
        code, peak, reason = run_watched(cmd, Limits(args.max_rss_gb, args.min_available_gb, args.min_swap_free_gb))
        took = time.time() - start
        peak_text = f", peak {peak / 2**30:.2f} GB" if peak else ""
        if code != 0:
            print(f"{key}: failed{f' ({reason})' if reason else ''} after {took:.0f} s{peak_text}")
            failed = True
            continue
        print(f"{key}: done in {took:.0f} s{peak_text}")

    from bundle import check
    summaries = {}
    for key in keys:
        path = Path(args.out) / args.game / Path(*key.split("/"))
        if not (path / "manifest.json").is_file():
            continue
        problems = check(path, deep=True)
        print(f"{key}: {'passes the deep check' if not problems else f'{len(problems)} problems'}")
        for p in problems[:30]:
            print(f"  {p}")
        failed |= bool(problems)
        summaries[key] = summary(path)
    return compare_snapshot(args.game, summaries, args.update_snapshot, keys) or (1 if failed else 0)


def worker(args) -> int:
    from kkbp_maps.extractor.extract import Options, extract_map
    from kkbp_maps.extractor.games import detect
    from kkbp_maps.extractor.maplist import list_maps

    install = detect(Path(args.games_dir) / GAME_FOLDERS[args.game], require_supported=False)   # a developer tool
    maps, _ = list_maps(install)
    m = next((m for m in maps if m.key == args.worker), None)
    if m is None:
        print(f"{args.worker} isn't a Map of this install")
        return 2
    extract_map(install, m, Path(args.out), Options(max_texture_size=args.max_texture_size), force=args.force,
                log=lambda text: print(f"  {text}", flush=True))
    return 0


# --- the snapshot -----------------------------------------------------------------------------------

def summary(path: Path) -> dict:
    """What the snapshot holds of a bundle: counts, hashes, names and tags, no game content."""
    def load(stem):
        return json.loads((path / f"{stem}.json").read_text(encoding="utf-8"))
    manifest, m, variants, assets, lightmaps = (load(s) for s in ("manifest", "map", "variants", "assets", "lightmaps"))
    contents = {k: v for k, v in manifest["contents"].items() if k != "bytes"}
    rules: dict[str, list[int]] = {}
    for c in assets["candidates"]:
        r = rules.setdefault(c["rule"], [0, 0])
        r[0] += 1
        r[1] += len(c["placements"])
    return {
        "contents": contents,
        "geometry_hash": m["geometry_hash"],
        "outdoor": m["outdoor"],
        "camera": m["camera"],
        "skipped": {s["reason"]: s["count"] for s in m["skipped"]},
        "thumbnails": [t["times_of_day"] for t in m["thumbnails"]],
        "variants": [{"times_of_day": v["times_of_day"], "lights": len(v["lights"]),
                      "sky": v["sky"]["kind"] + "/" + v["sky"]["source"] if v["sky"] else None,
                      "reflection": v["reflection"]["source"] + ("" if v["reflection"]["texture"] else " (none)"),
                      "probes": len(v["reflection"]["probes"]), "hidden": len(v["hidden"]),
                      "grade": bool(v["grade"]), "sun_shafts": bool(v["sun_shafts"])} for v in variants["variants"]],
        "lightmaps": [{"mode": s["mode"], "lightmaps": len(s["lightmaps"]), "assignments": len(s["assignments"])}
                      for s in lightmaps["sets"]],
        "candidates": {rule: {"candidates": n, "placements": p} for rule, (n, p) in sorted(rules.items())},
    }


def compare_snapshot(game: str, summaries: dict, update: bool, keys: list[str]) -> int:
    path = SNAPSHOTS / f"{game}.json"
    recorded = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if update:
        recorded.update(summaries)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recorded, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8",
                        newline="\n")
        print(f"recorded {', '.join(summaries)} in {path.relative_to(REPO)}")
        return 0
    status = 0
    for key in keys:
        if key not in summaries:
            continue
        if key not in recorded:
            print(f"{key}: not in the snapshot yet (run with --update-snapshot to record it)")
            continue
        if recorded[key] != summaries[key]:
            status = 1
            print(f"{key}: differs from the snapshot:")
            for field in sorted(set(recorded[key]) | set(summaries[key])):
                if recorded[key].get(field) != summaries[key].get(field):
                    print(f"  {field}: snapshot {recorded[key].get(field)!r}, now {summaries[key].get(field)!r}")
        else:
            print(f"{key}: matches the snapshot")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
