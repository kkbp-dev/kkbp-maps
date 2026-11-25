"""Runs inside a Blender with the packaged extension installed (tools/product_check.py): what the
N-panel does, without the panel. Writes what it found as JSON.

    blender -b --python tests/blender/product.py -- --game-folder G --output O --result R --maps K...
"""

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--game-folder", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--result", required=True)
parser.add_argument("--maps", nargs="+", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])

result = {}
try:
    package = "bl_ext.user_default.kkbp_maps"
    importlib.import_module(package)
    deps = importlib.import_module(f"{package}.deps")
    driver = importlib.import_module(f"{package}.jobs.driver")
    session = importlib.import_module(f"{package}.ui.session")
    library = importlib.import_module(f"{package}.ui.library")
    result["registered_ui"] = hasattr(bpy.types, "KKBPMAPS_PT_main")
    result["problems"] = deps.problems()
    result["site"] = deps.site_folders()

    s = session.session()
    s.detect(args.game_folder)
    result["game"] = s.install.game.id if s.install else s.install_error
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    listed = driver.list_maps(sys.executable, args.game_folder, deps.site_folders(), out / "map-list.json")
    result["listed"] = listed.get("error") or len(listed["maps"])

    request = session.request_for(s.install, str(out), args.maps, None, None, True)
    start = time.time()
    s.start(request)
    while s.process.poll() is None:
        time.sleep(1)
    state = driver.State.load(request.folder)
    result["build"] = {"status": state.status, "message": state.message, "seconds": round(time.time() - start),
                       "steps": [[st.id, st.status, st.seconds, st.peak_gb, st.reason] for st in state.steps]}
    result["unitypy_in_blender"] = "UnityPy" in sys.modules
    if state.status == "done":
        result["register"] = library.register_library(request.library.name, request.library)
        result["registered"] = library.registered(request.library) is not None
        bpy.ops.wm.save_userpref()   # the throwaway profile's
except Exception:
    import traceback
    result["error"] = traceback.format_exc()
Path(args.result).write_text(json.dumps(result, indent=1), encoding="utf-8")
