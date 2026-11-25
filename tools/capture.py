"""Takes Reference Captures of the Golden Maps in KK's Studio with the capture plugin (ADR 0006).

Developers only, never users. Run with KKBP's dev venv (numpy, for the one axis conversion):

    ../kkbp/importer/.venv/bin/python -I tools/capture.py            # capture every Capture View
    ../kkbp/importer/.venv/bin/python -I tools/capture.py --seed     # capture Studio's own cameras and
                                                                     # keep them as the Capture Views
    ../kkbp/importer/.venv/bin/python -I tools/capture.py --lights NAME... --map map/scene/ground
                                                                     # dump the lights only, no frames

It writes the request file (BepInEx/config/kkbp-maps-capture.json), sets aside the HF Patch plugins that
change the frame (tests/look/KK.json, "set_aside"), starts CharaStudio through games/play.sh, waits for
the plugin's result and the game to quit, and puts the plugins back whatever happens. The captures go to
captures/KK/ (ignored: game content, ADR 0007), with camera-studio.json beside them.

It refuses while the game runs ("Running the games safely" in ../kkbp/CLAUDE.md) and stops the game only
by its exact process name. The plugin must be deployed first (--deploy, after the user's OK), and is
taken out again with --undeploy.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "extension"))
from kkbp_maps.extractor import space  # noqa: E402  (the one place axes are converted, ADR 0011)

GAMES = Path(os.environ.get("KKBP_GAMES_DIR", REPO.parent / "games"))
GAME_DIR = GAMES / "Koikatsu"
PROCESSES = ("CharaStudio.exe", "Koikatu.exe")   # Linux keeps 15 characters of a process name
CONFIG = GAME_DIR / "BepinEx" / "config"
PLUGINS = GAME_DIR / "BepinEx" / "plugins"
PLUGIN_DLL = "KKMaps.Capture.KK.dll"
BUILT = REPO / "tests" / ".work" / "capture" / "bin" / PLUGIN_DLL
LOOK = REPO / "tests" / "look" / "KK.json"
VIEWS = REPO / "tests" / "look" / "views" / "KK.json"
OUT = REPO / "captures" / "KK"
GOLDEN = REPO / "golden" / "KK"
OFF = ".kkbp-maps-off"
TIME_TYPE = {"day": 0, "evening": 1, "night": 2}   # SunLightInfo.Info.Type
SEED_YAWS = (0, 90, 180, 270)   # eye-level views about Studio's camera target
SEED_EYE = 1.6


def winpath(p: Path) -> str:
    """A Linux path as Wine sees it (Z: is /); a Windows path stays as it is."""
    return str(p) if os.name == "nt" else "Z:" + str(p).replace("/", "\\")


def running() -> list[str]:
    if os.name == "nt":
        return []
    return [p for p in PROCESSES if subprocess.run(["pgrep", "-x", p], capture_output=True).returncode == 0]


def to_unity(p) -> list[float]:
    return [float(x) for x in space.unity_vectors(np.array([p], dtype=float))[0]]


def to_blender(p) -> list[float]:
    return [float(x) for x in space.vector(p)]


def variants(map_key: str) -> list[dict]:
    data = json.loads((GOLDEN / map_key / "variants.json").read_text(encoding="utf-8"))
    return data["variants"]


def request(look: dict, seed: bool, only: list[str] | None = None, lights: list[str] | None = None) -> dict:
    """With `lights`, a run that only dumps each Map Variant's lights and those renderers, taking no frames."""
    views = {} if seed else json.loads(VIEWS.read_text(encoding="utf-8"))["views"]
    maps = []
    for key in look["maps"]:
        if only and key not in only:
            continue
        bundle = next(s["path"] for s in json.loads((GOLDEN / key / "manifest.json").read_text())["sources"]
                      if s["path"].startswith("abdata/map/scene/")).removeprefix("abdata/")
        vs = []
        for v in variants(key):
            if seed:
                vv = [{"name": "studio", "studio_default": 0}] + [
                    {"name": f"eye-{y}", "studio_default": y, "eye": SEED_EYE} for y in SEED_YAWS]
            else:
                vv = [{"name": w["name"], "position": to_unity(w["position"]), "target": to_unity(w["target"]),
                       "fov": w["fov"]} for w in views if w["map"] == key and w["variant"] == v["id"]]
            if vv or lights is not None:
                vs.append({"name": v["id"], "type": TIME_TYPE[v["times_of_day"][0]], "views": vv})
        maps.append({"folder": key, "bundle": bundle, "variants": vs})
    out = {"output": winpath(OUT), "width": look["width"], "height": look["height"],
           "disable": look["disable_effects"], "maps": maps}
    if lights is not None:
        out.update(frames=False, renderers=lights)
    return out


def set_aside(names: list[str]) -> list[Path]:
    moved = []
    for name in names:
        p = PLUGINS / name
        if p.exists():
            p.rename(p.with_name(p.name + OFF))
            moved.append(p)
    return moved


def put_back(moved: list[Path]):
    for p in moved:
        off = p.with_name(p.name + OFF)
        if off.exists():
            off.rename(p)


def _state(result: Path) -> str | None:
    try:
        return json.loads(result.read_text(encoding="utf-8"))["state"]
    except (OSError, ValueError, KeyError):
        return None


def run(req: dict, look: dict, timeout: int) -> dict | None:
    result = CONFIG / "kkbp-maps-capture.result.json"
    req_path = CONFIG / "kkbp-maps-capture.json"
    result.unlink(missing_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    req_path.write_text(json.dumps(req, indent=1), encoding="utf-8")
    moved = set_aside(look["set_aside"])
    print(f"capture: set aside {len(moved)} plugins; starting CharaStudio", flush=True)
    try:
        log = open(REPO / "tests" / ".work" / "capture" / "play.log", "w")
        subprocess.Popen([str(GAMES / "play.sh"), "koikatsu", "CharaStudio.exe"], stdout=log, stderr=log)
        start = time.monotonic()
        while _state(result) in (None, "running"):
            if time.monotonic() > start + timeout:
                print(f"capture: not done after {timeout}s; stopping the game", file=sys.stderr)
                break
            if time.monotonic() > start + 120 and not running():
                print("capture: the game exited before it finished", file=sys.stderr)
                break
            time.sleep(2)
        time.sleep(3)
    finally:
        for p in PROCESSES:
            subprocess.run(["pkill", "-x", p], capture_output=True)
        for _ in range(30):
            if not running():
                break
            time.sleep(1)
        put_back(moved)
        req_path.unlink(missing_ok=True)
    return json.loads(result.read_text(encoding="utf-8")) if result.exists() else None


def keep_views(placed: list[dict]):
    """The views the plugin placed, in Blender space, as Capture Views, replacing those of the same Map
    Variants and keeping the others."""
    old = json.loads(VIEWS.read_text(encoding="utf-8"))["views"] if VIEWS.exists() else []
    new = [{"map": v["map"], "variant": v["variant"], "name": v["name"],
              "position": [round(x, 4) for x in to_blender(v["position"])],
              "target": [round(x, 4) for x in to_blender(v["target"])], "fov": round(v["fov"], 4)} for v in placed]
    redone = {(v["map"], v["variant"]) for v in new}
    views = [v for v in old if (v["map"], v["variant"]) not in redone] + new
    views.sort(key=lambda v: (v["map"], v["variant"], v["name"]))
    VIEWS.parent.mkdir(parents=True, exist_ok=True)
    VIEWS.write_text(json.dumps({"game": "KK", "space": "blender", "views": views}, indent=1) + "\n", encoding="utf-8")
    print(f"capture: kept {len(new)} new Capture Views, {len(views)} in all, in {VIEWS.relative_to(REPO)}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", action="store_true", help="capture Studio's own cameras and keep them as the Capture Views")
    ap.add_argument("--deploy", action="store_true", help="copy the built plugin into the game, then stop")
    ap.add_argument("--undeploy", action="store_true", help="take the plugin out of the game, then stop")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--map", action="append", help="only this Map, such as map/scene/park; all by default")
    ap.add_argument("--lights", nargs="*", metavar="RENDERER",
                    help="take no frames: only dump each Map Variant's lights (lights.json), and these renderers")
    args = ap.parse_args(argv)

    if running():
        print(f"capture: {', '.join(running())} is running; close it first", file=sys.stderr)
        return 2
    if args.deploy:
        shutil.copy2(BUILT, PLUGINS / PLUGIN_DLL)
        print(f"capture: deployed {PLUGINS / PLUGIN_DLL}")
        return 0
    if args.undeploy:
        (PLUGINS / PLUGIN_DLL).unlink(missing_ok=True)
        print("capture: plugin removed")
        return 0
    if not (PLUGINS / PLUGIN_DLL).exists():
        print("capture: the plugin isn't deployed (--deploy)", file=sys.stderr)
        return 2

    look = json.loads(LOOK.read_text(encoding="utf-8"))
    res = run(request(look, args.seed, args.map, args.lights), look, args.timeout)
    if res is None:
        print("capture: no result", file=sys.stderr)
        return 1
    print(json.dumps({k: v for k, v in res.items() if k not in ("views", "files")}, indent=1))
    print(f"capture: {len(res['files'])} files, state {res['state']}")
    if args.seed and res["views"]:
        keep_views(res["views"])   # also after a crash: the views captured so far
    return 0 if res["state"] == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
