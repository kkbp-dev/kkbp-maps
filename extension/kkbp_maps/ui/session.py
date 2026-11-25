"""What the N-panel knows between redraws: the Maps listed, the Build it started or found, and a
timer that reads the driver's state file and redraws. Nothing here is saved in a .blend file."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import bpy

from .. import deps
from ..extractor.games import Install, NotAGameFolder, UnsupportedGame, detect
from ..jobs import driver

POLL_SECONDS = 0.5


class Session:
    def __init__(self):
        self.install: Install | None = None
        self.install_error = ""
        self.listing: threading.Thread | None = None
        self.listed: dict | None = None
        self.list_error = ""
        self.process: subprocess.Popen | None = None
        self.state: driver.State | None = None
        self.state_folder: Path | None = None
        self.problems = deps.problems()

    # --- the game install ------------------------------------------------------------------------

    def detect(self, folder: str) -> Install | None:
        self.install, self.install_error = None, ""
        if not folder:
            return None
        try:
            self.install = detect(bpy.path.abspath(folder))
        except (NotAGameFolder, UnsupportedGame) as e:
            self.install_error = str(e)
            if isinstance(e, UnsupportedGame):
                self.install_error += ". v0.1 builds KK only; KKS and SVS come later"
        return self.install

    def list_maps(self, work: Path):
        """Starts listing the install's Maps in a thread; the timer copies the result into the panel."""
        install = self.install
        result = work / "map-list.json"
        work.mkdir(parents=True, exist_ok=True)
        self.listed, self.list_error = None, ""

        def run():
            try:
                self.listed = driver.list_maps(sys.executable, str(install.root), deps.site_folders(), result)
            except Exception as e:   # shown in the panel, never raised into Blender
                self.listed = {"error": f"Listing the Maps failed: {e}"}

        self.listing = threading.Thread(target=run, daemon=True)
        self.listing.start()
        start_timer()

    # --- the Build -------------------------------------------------------------------------------

    def start(self, request: driver.Request):
        path = request.save()
        (request.folder / driver.CANCEL_FILE).unlink(missing_ok=True)
        self.process = subprocess.Popen([sys.executable, "-I", str(driver.JOBS / "driver.py"), "--request", str(path)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **driver._quiet())
        self.state_folder = request.folder
        self.state = None
        start_timer()

    def watch(self, folder: Path):
        """Reads the state of the Build in `folder`, if there is one, such as after Blender restarts."""
        if self.state_folder != folder:
            self.state_folder = folder
            self.state = driver.State.load(folder)
            if self.running():
                start_timer()

    def running(self) -> bool:
        if self.process is not None and self.process.poll() is None:
            return True
        return bool(self.state and self.state.status == "running" and driver.alive(self.state.pid))

    def cancel(self):
        if self.state_folder:
            driver.cancel(self.state_folder)

    def refresh(self) -> bool:
        """Reads the state file; whether anything is still going on."""
        if self.listing is not None and not self.listing.is_alive():
            self.listing = None
            fill_maps(self.listed or {"error": "Listing the Maps gave nothing"})
        if self.state_folder:
            self.state = driver.State.load(self.state_folder) or self.state
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.state = driver.State.load(self.state_folder) if self.state_folder else None
        return self.listing is not None or self.running()

    def stop(self):
        """Blender is unloading the extension: a Build it started is cancelled."""
        if self.process is not None and self.process.poll() is None:
            self.cancel()


SESSION: Session | None = None


def session() -> Session:
    global SESSION
    if SESSION is None:
        SESSION = Session()
    return SESSION


def fill_maps(listed: dict):
    from ..builder.names import NameTables

    s = session()
    wm = bpy.context.window_manager
    items = wm.kkbp_maps.maps
    items.clear()
    if "error" in listed:
        s.list_error = listed["error"]
        return
    try:
        tables = NameTables.load(listed["game"])
    except Exception:
        tables = None
    for m in listed["maps"]:
        item = items.add()
        item.key = m["key"]
        item.name = (tables.map_name(m["key"]) if tables else None) or (m["list_names"] or [m["key"]])[0]
        item.studio_only = m["lists"] == ["studio"]
        item.megabytes = m["bytes"] / 2**20
        item.selected = True
    if listed.get("missing"):
        s.list_error = f"{len(listed['missing'])} listed Maps aren't installed and are left out"


def _tick():
    s = session()
    going = s.refresh()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type in ("VIEW_3D", "PREFERENCES"):
                area.tag_redraw()
    return POLL_SECONDS if going else None


def start_timer():
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=POLL_SECONDS, persistent=True)


def request_for(install: Install, output: str, keys: list[str], camera: str | None, max_texture_size: int | None,
                previews: bool) -> driver.Request:
    return driver.Request(game=install.game.id, game_folder=str(install.root), output=output, maps=keys,
                          blender=bpy.app.binary_path, python=sys.executable, site=deps.site_folders(),
                          camera=camera, max_texture_size=max_texture_size, previews=previews,
                          parent_pid=os.getpid())


def unregister():
    global SESSION
    if SESSION is not None:
        SESSION.stop()
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    SESSION = None
