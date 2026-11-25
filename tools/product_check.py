"""Checks a packaged zip the way a user gets it: installed into a throwaway Blender profile, with its
wheels, building the Golden Maps through the extension, and compared with both snapshots.

Usage (any Python 3.11 or later), in the background (a few minutes per Blender build):

    python3 tools/package.py              # first: the zips
    python3 tools/product_check.py        # every Blender build, one at a time
    python3 tools/product_check.py --blender min

For each build: a fresh profile under tests/.work/product/<build>/ (BLENDER_USER_RESOURCES; never the
user's), `extension install-file --enable` of this platform's zip, then tests/blender/product.py in
`blender -b`: no dependency problems, the Maps listed, a Build of the Golden Maps by the driver,
UnityPy never loaded in Blender's process, and the Map Library registered in that profile. The Map
Bundles are compared with the extraction snapshot and the Map Library with the build snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build_golden  # noqa: E402
import golden  # noqa: E402
from kkbp_maps.jobs.memory import BUILD, run_watched  # noqa: E402

WORK = REPO / "tests" / ".work" / "product"   # under home: the snap can't see /tmp
PLATFORMS = {("Linux", "x86_64"): "linux-x64", ("Windows", "AMD64"): "windows-x64", ("Darwin", "arm64"): "macos-arm64"}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--blender", action="append", choices=sorted(build_golden.BUILDS))
    parser.add_argument("--game", default="KK", choices=sorted(golden.GOLDEN))
    parser.add_argument("--games-dir", default=os.environ.get("KKBP_GAMES_DIR", str(REPO.parent / "games")))
    parser.add_argument("--zip", help="the zip to check; this platform's in dist/ by default")
    args = parser.parse_args(argv)
    game_folder = Path(args.games_dir) / golden.GAME_FOLDERS[args.game]
    if not game_folder.is_dir():
        print(f"{game_folder} isn't there: nothing to build")
        return 0
    zip_path = Path(args.zip) if args.zip else this_platforms_zip()
    if zip_path is None or not zip_path.is_file():
        print("no zip for this platform in dist/: run tools/package.py first")
        return 1
    print(f"checking {zip_path.name}")
    failed = False
    for name in args.blender or list(build_golden.BUILDS):
        exe = build_golden.blender_path(name)
        if not exe.is_file():
            print(f"{name}: {exe} isn't there, skipped")
            continue
        failed |= not check(name, exe, zip_path, game_folder, args.game)
    return 1 if failed else 0


def this_platforms_zip() -> Path | None:
    manifest = tomllib.loads((REPO / "extension" / "kkbp_maps" / "blender_manifest.toml").read_text(encoding="utf-8"))
    plat = PLATFORMS.get((platform.system(), platform.machine()))
    if plat is None:
        return None
    found = sorted((REPO / "dist").glob(f"{manifest['id']}-{manifest['version']}-{plat.replace('-', '_')}.zip")) + \
        sorted((REPO / "dist").glob(f"{manifest['id']}-{manifest['version']}-{plat}.zip"))
    return found[0] if found else None


def check(name: str, exe: Path, zip_path: Path, game_folder: Path, game: str) -> bool:
    root = WORK / name
    if root.exists():
        shutil.rmtree(root)
    profile, output = root / "profile", root / "out"
    profile.mkdir(parents=True)
    log = root / "check.log"
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile))

    def blender(cmd: list[str]) -> int:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n$ {exe} {' '.join(cmd)}\n")
            f.flush()
            code, peak, reason = run_watched([str(exe), *cmd], BUILD.capped(), env=env, stdout=f, stderr=f)
        if reason:
            print(f"  {reason}")
        return code

    if blender(["--factory-startup", "--command", "extension", "install-file", "--repo", "user_default", "--enable",
                str(zip_path)]) != 0:
        print(f"{name}: installing the zip failed; see {log}")
        return False
    result_file = root / "result.json"
    blender(["-b", "--python", str(REPO / "tests" / "blender" / "product.py"), "--", "--game-folder", str(game_folder),
             "--output", str(output), "--result", str(result_file), "--maps", *build_golden.GOLDEN[game]])   # the build snapshot's order
    if not result_file.is_file():
        print(f"{name}: product.py wrote nothing; see {log}")
        return False
    r = json.loads(result_file.read_text(encoding="utf-8"))
    if r.get("error"):
        print(f"{name}: {r['error']}")
        return False
    build = r.get("build", {})
    print(f"{name}: dependencies {'ok' if not r['problems'] else r['problems']}; panel registered: "
          f"{r['registered_ui']}; {r['listed']} Maps listed; Build {build.get('status')} in {build.get('seconds')} s; "
          f"UnityPy in Blender: {r['unitypy_in_blender']}; registered: {r.get('registered')}")
    for step in build.get("steps", []):
        print(f"  {step[0]}: {step[1]} in {step[2]:.0f} s, peak {step[3]:.2f} GB{f' ({step[4]})' if step[4] else ''}")
    ok = (not r["problems"] and r["registered_ui"] and isinstance(r["listed"], int) and build.get("status") == "done"
          and not r["unitypy_in_blender"] and r.get("registered"))
    if not all(site.startswith(str(profile.resolve())) for site in r["site"]):
        print(f"  the wheels aren't all in the throwaway profile: {r['site']}")
        ok = False

    bundles = output / "Map Bundles" / game
    extracted = {key: golden.summary(bundles / Path(*key.split("/"))) for key in golden.GOLDEN[game]}
    ok &= golden.compare_snapshot(game, extracted, False, golden.GOLDEN[game]) == 0
    summary = build_golden.summarize(exe, profile, output / f"{game} Maps", root / "summaries", BUILD.capped(), log)
    ok &= summary is not None and build_golden.compare(game, {name: summary}, False) == 0
    print(f"{name}: {'passes' if ok else 'FAILS'}")
    return bool(ok)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
