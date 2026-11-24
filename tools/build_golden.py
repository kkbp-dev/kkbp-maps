"""Builds the Golden Maps into a Map Library on each Blender build, summarizes the files, and compares
the summaries with the committed snapshot.

Usage (any Python 3.11 or later; Blender does the building):

    python3 tools/build_golden.py                       # every build, one at a time, and compare
    python3 tools/build_golden.py --blender min         # one build
    python3 tools/build_golden.py --update-snapshot     # record the snapshot from the first build, then compare

The Golden Maps (golden/<Game>/, made by tools/golden.py) are copied into tests/.work/build/bundles/
first and built from there, never in place. Each build gets its own library folder and its own Blender
profile (BLENDER_USER_RESOURCES), and runs `blender -b --factory-startup` with this repository's
extension/ on the path (tools/blender_build.py): nothing is installed into Blender or the user's
profile. Every Blender process runs under the memory watchdog (tools/memory_watch.py).

The snapshot, tests/snapshots/build/<Game>.json, holds counts, names, hashes and tags only (ADR 0007).
Set KKBP_MAPS_BLENDER_<NAME> to use another binary for a build.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from memory_watch import Limits, run_watched  # noqa: E402

GOLDEN = {"KK": ["map/scene/1f", "map/scene/ground", "map/scene/park"]}
BUILDS = {  # the snap's launcher can't start from every process, so the snap's binary is named directly
    "min": "~/.local/opt/blender-5.2.2/blender",
    "latest": "/snap/blender/current/blender",
}
WORK = REPO / "tests" / ".work" / "build"   # under home: the snap can't see /tmp
SNAPSHOTS = REPO / "tests" / "snapshots" / "build"
STEP_TIMEOUT = 1800


def blender_path(name: str) -> Path:
    return Path(os.environ.get(f"KKBP_MAPS_BLENDER_{name.upper()}", BUILDS[name])).expanduser()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game", default="KK", choices=sorted(GOLDEN))
    parser.add_argument("--golden", default=str(REPO / "golden"))
    parser.add_argument("--blender", action="append", choices=sorted(BUILDS), help="the builds; all by default")
    parser.add_argument("--update-snapshot", action="store_true")
    parser.add_argument("--no-previews", action="store_true")
    parser.add_argument("--max-rss-gb", type=float, default=8.0)
    parser.add_argument("--min-available-gb", type=float, default=1.5)
    parser.add_argument("--min-swap-free-gb", type=float, default=6.0)
    args = parser.parse_args(argv)
    limits = Limits(args.max_rss_gb, args.min_available_gb, args.min_swap_free_gb)

    bundles = copy_golden(Path(args.golden) / args.game, GOLDEN[args.game])
    if bundles is None:
        return 0
    builds = args.blender or list(BUILDS)
    summaries, failed = {}, False
    for name in builds:
        exe = blender_path(name)
        if not exe.is_file():
            print(f"{name}: {exe} isn't there, skipped")
            continue
        print(f"{name}: building with {exe}")
        result = build(name, exe, args.game, bundles, limits, not args.no_previews)
        if result is None:
            failed = True
            continue
        summaries[name] = result
    if not summaries:
        return 1
    return compare(args.game, summaries, args.update_snapshot) or (1 if failed else 0)


def copy_golden(source: Path, keys: list[str]) -> list[Path] | None:
    """Copies of the Golden Maps to build from; a copy whose Manifest matches its Golden Map is reused."""
    out = []
    for key in keys:
        src = source / Path(*key.split("/"))
        if not (src / "manifest.json").is_file():
            print(f"{src} isn't there: make the Golden Maps first (tools/golden.py)")
            return None
        dst = WORK / "bundles" / Path(*key.split("/"))
        if not (dst / "manifest.json").is_file() or (dst / "manifest.json").read_bytes() != (src / "manifest.json").read_bytes():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"{key}: copied")
        out.append(dst)
    return out


def blender(exe: Path, profile: Path, args: list[str], limits: Limits, log: Path) -> tuple[int, int, str]:
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile))
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n$ {exe} {' '.join(args)}\n")
        f.flush()
        return run_watched([str(exe), "-b", "--factory-startup", *args], limits, env=env, stdout=f, stderr=f)


def build(name: str, exe: Path, game: str, bundles: list[Path], limits: Limits, previews: bool) -> dict | None:
    root = WORK / name
    library = root / f"{game} Maps"
    if root.exists():
        shutil.rmtree(root)
    profile = root / "profile"
    profile.mkdir(parents=True)
    log = root / "build.log"
    steps = [f"map:{k}" for k in GOLDEN[game]] + ["assets", "finish"]
    for step in steps:
        cmd = ["--python", str(REPO / "tools" / "blender_build.py"), "--", "--library", str(library),
               "--bundles", *map(str, bundles), "--step", step]
        if not previews:
            cmd.append("--no-previews")
        start = time.time()
        code, peak, reason = blender(exe, profile, cmd, limits, log)
        print(f"  {step}: {'done' if code == 0 else f'failed {reason}'} in {time.time() - start:.0f} s, "
              f"peak {peak / 2**30:.2f} GB")
        if code != 0:
            print(f"  see {log}")
            return None
    summaries = {}
    for blend in sorted(library.rglob("*.blend")):
        rel = blend.relative_to(library).as_posix()
        out = root / "summaries" / (rel.replace("/", "__") + ".json")
        out.parent.mkdir(parents=True, exist_ok=True)
        code, _, reason = blender(exe, profile, [str(blend), "--python", str(REPO / "tests" / "blender" / "summary.py"),
                                                 "--", str(out), str(library / "blender_assets.cats.txt")], limits, log)
        if code != 0 or not out.is_file():
            print(f"  summary of {rel} failed {reason}; see {log}")
            return None
        summaries[rel] = json.loads(out.read_text(encoding="utf-8"))
    report = json.loads((library / "build-report.json").read_text(encoding="utf-8"))
    report.pop("builder", None)
    for m in report["maps"]:
        m.pop("kept", None)
    return {"files": summaries, "report": report,
            "library_files": sorted(p.relative_to(library).as_posix() for p in library.iterdir())}


def compare(game: str, summaries: dict, update: bool) -> int:
    path = SNAPSHOTS / f"{game}.json"
    names = list(summaries)
    if update:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summaries[names[0]], indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        print(f"recorded {path.relative_to(REPO)} from {names[0]}; review the diff before committing")
    if not path.is_file():
        print(f"no snapshot yet; record one with --update-snapshot")
        return 1
    expected = json.loads(path.read_text(encoding="utf-8"))
    failed = 0
    for name, actual in summaries.items():
        actual = json.loads(json.dumps(actual, sort_keys=True))
        differences = list(diff(expected, actual))
        if differences:
            failed = 1
            print(f"{name}: {len(differences)} differences from the snapshot:")
            for d in differences[:40]:
                print(f"  {d}")
        else:
            print(f"{name}: matches the snapshot")
    return failed


def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                yield f"{path}/{k}: new"
            elif k not in b:
                yield f"{path}/{k}: missing"
            else:
                yield from diff(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{path}[{i}]")
    elif a != b:
        yield f"{path}: {json.dumps(a, ensure_ascii=False)[:80]} → {json.dumps(b, ensure_ascii=False)[:80]}"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
