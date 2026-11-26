"""Takes Reference Captures of a Game's Golden Maps with the capture plugin (ADR 0006): KK's in Studio or
its story game, KKS's in its story game (--game KKS; KKS's Studio loads its own builds of the Maps).

Developers only, never users. Run with KKBP's dev venv (numpy, for the one axis conversion):

    ../kkbp/importer/.venv/bin/python -I tools/capture.py            # capture every Capture View
    ../kkbp/importer/.venv/bin/python -I tools/capture.py --seed     # capture Studio's own cameras and
                                                                     # keep them as the Capture Views
    ../kkbp/importer/.venv/bin/python -I tools/capture.py --lights NAME... --map map/scene/ground
                                                                     # dump the lights only, no frames
    ../kkbp/importer/.venv/bin/python -I tools/capture.py --camera game
                                                                     # the same views in the story game

It writes the request file (BepInEx/config/kkbp-maps-capture.json), sets aside the HF Patch plugins that
change the frame (tests/look/KK.json, "set_aside"), starts the game of the Camera Profile through
games/play.sh (CharaStudio for "studio", the story game from its title screen for "game"), waits for the
plugin's result and the game to quit, and puts the plugins back whatever happens. Studio's captures go to
captures/KK/ (ignored: game content, ADR 0007), the story game's to captures/KK/game/, each with
camera-<profile>.json beside them.

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

from kkbp_maps.jobs import memory  # noqa: E402  (the game's own memory, watched while it runs)

GAMES = Path(os.environ.get("KKBP_GAMES_DIR", REPO.parent / "games"))
OFF = ".kkbp-maps-off"
SEED_YAWS = (0, 90, 180, 270)   # eye-level views about the seed's anchor
SEED_EYE = 1.6
# Stop the game before it takes the desktop down (the user's rule): its own memory, or the machine's.
GAME_MAX_GB, MIN_AVAILABLE_GB, MIN_SWAP_FREE_GB = 10.0, 1.2, 6.0

# Per Game: its folder, play.sh's name for it, the program each Camera Profile runs in, the processes to
# watch and stop (Linux keeps 15 characters of a process name), SunLightInfo.Info.Type by Time of Day,
# and the seed's overview view name (Studio's camera in KK, the free-H point's overview in KKS).
GAME_DATA = {
    "KK": {"dir": "Koikatsu", "play": "koikatsu", "exes": {"studio": "CharaStudio.exe", "game": "Koikatu.exe"},
           "processes": ("CharaStudio.exe", "Koikatu.exe"), "times": {"day": 0, "evening": 1, "night": 2},
           "overview": "studio"},
    "KKS": {"dir": "Koikatsu Sunshine", "play": "kks", "exes": {"game": "KoikatsuSunshine.exe"},
            "processes": ("KoikatsuSunshin",), "times": {"morning": 0, "day": 1, "evening": 2, "night": 3},
            "overview": "overview"},
}


def use_game(game: str):
    """Points the module's paths at one Game."""
    global GAME, GAME_DIR, PROCESSES, CONFIG, PLUGINS, PLUGIN_DLL, BUILT, LOOK, VIEWS, OUT, GOLDEN, EXES, TIME_TYPE
    GAME = game
    d = GAME_DATA[game]
    GAME_DIR = GAMES / d["dir"]
    PROCESSES = d["processes"]
    CONFIG = GAME_DIR / "BepinEx" / "config"
    PLUGINS = GAME_DIR / "BepinEx" / "plugins"
    PLUGIN_DLL = f"KKMaps.Capture.{game}.dll"
    BUILT = REPO / "tests" / ".work" / "capture" / ("bin" if game == "KK" else f"bin-{game.lower()}") / PLUGIN_DLL
    LOOK = REPO / "tests" / "look" / f"{game}.json"
    VIEWS = REPO / "tests" / "look" / "views" / f"{game}.json"
    OUT = REPO / "captures" / game
    GOLDEN = REPO / "golden" / game
    EXES = d["exes"]
    TIME_TYPE = d["times"]


use_game("KK")


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


def request(look: dict, seed: bool, only: list[str] | None = None, lights: list[str] | None = None,
            views_only: list[str] | None = None, sun_off: bool = False, sun_no_shadows: bool = False,
            camera: str = "studio", also_disable: list[str] | None = None) -> dict:
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
                vv = [{"name": GAME_DATA[GAME]["overview"], "studio_default": 0}] + [
                    {"name": f"eye-{y}", "studio_default": y, "eye": SEED_EYE} for y in SEED_YAWS]
            else:
                vv = [{"name": w["name"], "position": to_unity(w["position"]), "target": to_unity(w["target"]),
                       "fov": w["fov"]} for w in views if w["map"] == key and w["variant"] == v["id"]
                      and (not views_only or f"{key}/{v['id']}/{w['name']}" in views_only)]
            if vv or lights is not None:
                vs.append({"name": v["id"], "type": TIME_TYPE[v["times_of_day"][0]], "views": vv})
        maps.append({"folder": key, "bundle": bundle, "variants": vs})
    out_dir = OUT if camera == "studio" else OUT / camera   # as tools/look.py's captures_of
    out = {"camera": camera, "output": winpath(out_dir), "width": look["width"], "height": look["height"],
           "disable": look["disable_effects"], "maps": maps}
    if lights is not None:
        out.update(frames=False, renderers=lights)
    if sun_off:
        out.update(sun_off=True, output=winpath(out_dir / "sun-off"))
    elif sun_no_shadows:
        out.update(sun_shadows_off=True, output=winpath(out_dir / "sun-no-shadows"))
    elif also_disable:
        out.update(disable=look["disable_effects"] + also_disable,
                   output=winpath(out_dir / ("no-" + "-".join(also_disable))))
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
    exe = EXES[req["camera"]]
    print(f"capture: set aside {len(moved)} plugins; starting {exe}", flush=True)
    try:
        log = open(REPO / "tests" / ".work" / "capture" / "play.log", "w")
        subprocess.Popen([str(GAMES / "play.sh"), GAME_DATA[GAME]["play"], exe], stdout=log, stderr=log)
        start = time.monotonic()
        peak = 0
        while _state(result) in (None, "running"):
            if time.monotonic() > start + timeout:
                print(f"capture: not done after {timeout}s; stopping the game", file=sys.stderr)
                break
            if time.monotonic() > start + 120 and not running():
                print("capture: the game exited before it finished", file=sys.stderr)
                break
            why = memory_breach()
            if why:
                print(f"capture: stopping the game: {why}", file=sys.stderr)
                break
            used = game_memory()
            peak = max(peak, used or 0)
            time.sleep(0.5)
        print(f"capture: the game's peak memory {peak / 2**30:.1f} GB", flush=True)
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


def game_memory() -> int | None:
    """The game's own memory (resident and swapped) in bytes, by its exact process name."""
    if os.name == "nt":
        return None
    total = None
    for name in PROCESSES:
        r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
        for pid in r.stdout.split():
            used = memory.process_memory(int(pid))
            if used is not None:
                total = (total or 0) + used
    return total


def memory_breach() -> str:
    """Why the game must stop now, or "": past GAME_MAX_GB, or the machine short of memory or swap."""
    gb = 2 ** 30
    used = game_memory()
    if used is not None and used > GAME_MAX_GB * gb:
        return f"the game uses {used / gb:.1f} GB"
    available = memory.available_memory()
    if available is not None and available < MIN_AVAILABLE_GB * gb:
        return f"only {available / gb:.1f} GB of memory left"
    swap = memory.swap_free()
    if swap is not None and swap < MIN_SWAP_FREE_GB * gb:
        return f"only {swap / gb:.1f} GB of swap left"
    return ""


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
    VIEWS.write_text(json.dumps({"game": GAME, "space": "blender", "views": views}, indent=1) + "\n", encoding="utf-8")
    print(f"capture: kept {len(new)} new Capture Views, {len(views)} in all, in {VIEWS.relative_to(REPO)}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", choices=sorted(GAME_DATA), default="KK")
    ap.add_argument("--camera", choices=["studio", "game"], default=None,
                    help="the Camera Profile, and so the game: CharaStudio (studio) or the story game (game); "
                         "the look file's by default")
    ap.add_argument("--seed", action="store_true", help="capture Studio's own cameras and keep them as the Capture Views")
    ap.add_argument("--deploy", action="store_true", help="copy the built plugin into the game, then stop")
    ap.add_argument("--undeploy", action="store_true", help="take the plugin out of the game, then stop")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.add_argument("--map", action="append", help="only this Map, such as map/scene/park; all by default")
    ap.add_argument("--lights", nargs="*", metavar="RENDERER",
                    help="take no frames: only dump each Map Variant's lights (lights.json), and these renderers")
    ap.add_argument("--view", action="append", help="only this Capture View, such as map/scene/ground/day/studio")
    ap.add_argument("--sun-off", action="store_true",
                    help="switch the Map's sun off; the frames go to captures/<Game>/sun-off/ (a measurement)")
    ap.add_argument("--also-disable", action="append", metavar="EFFECT",
                    help="also switch off this camera effect, such as SunShafts; frames go to "
                         "captures/<Game>/[<profile>/]no-<EFFECT>/ (a measurement)")
    ap.add_argument("--globals", nargs="+", metavar="NAME",
                    help="take no frames: dump these shader globals per Map Variant (globals.json)")
    ap.add_argument("--sun-no-shadows", action="store_true",
                    help="the Map's sun casts no shadows; frames go to captures/<Game>/sun-no-shadows/ (a measurement)")
    args = ap.parse_args(argv)
    use_game(args.game)
    look_camera = json.loads(LOOK.read_text(encoding="utf-8")).get("camera", "studio") if LOOK.exists() else "studio"
    args.camera = args.camera or look_camera
    if args.camera not in EXES:
        print(f"capture: {args.game} has no {args.camera} camera to capture with", file=sys.stderr)
        return 2

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

    if args.seed and args.game == "KK" and args.camera != "studio":
        print("capture: KK's --seed takes Studio's own cameras; it needs --camera studio", file=sys.stderr)
        return 2
    look = json.loads(LOOK.read_text(encoding="utf-8"))
    req = request(look, args.seed, args.map, args.lights if args.lights is not None else ([] if args.globals else None),
                  args.view, args.sun_off, args.sun_no_shadows, args.camera, args.also_disable)
    if args.globals:
        req["globals"] = args.globals
    res = run(req, look, args.timeout)
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
