"""Runs a Build outside Blender's process, a step at a time, each step in a process of its own under
the memory watchdog (D18):

    extract:<key>   on Blender's own Python (worker.py), into the Bundle Folder
    map:<key>       in `blender -b` (blender_worker.py), one Map file of the Map Library
    assets, finish  in `blender -b`: Props.blend and Structures.blend, then the catalogs and the Build Report

    <python> -I driver.py --request <file>

The request (Request, as JSON) says what to build; the N-panel writes it, and anyone can. The driver
writes its State next to it in the Game's Bundle Folder, `build-state.json`, after every change, and
everything the steps print to `build.log`. It stops between polls when `cancel` appears beside them,
or when the process that started it (Blender) is gone. A Map whose extraction or Map file fails is
left out, and the Build carries on; the Build Report lists it. Running the same request again
resumes: fresh Map Bundles and unchanged Map files are kept.

Imports only the standard library and the bpy-free parts of the extension.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__ in (None, ""):   # run as a script: the extension's folder is two up
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from kkbp_maps.jobs import memory
else:
    from . import memory

BUNDLE_FOLDER = "Map Bundles"
STATE_FILE, REQUEST_FILE, LOG_FILE, CANCEL_FILE = "build-state.json", "build-request.json", "build.log", "cancel"
RESULT_FILE = "step-result.json"
JOBS = Path(__file__).resolve().parent
EXTENSION = JOBS.parent.parent   # the folder holding the kkbp_maps package


@dataclass
class Request:
    game: str                      # the Game's id, as detect() found it
    game_folder: str
    output: str                    # holds "<Game> Maps" (the Map Library) and the Bundle Folder
    maps: list[str]                # Map keys, in build order
    blender: str                   # the Blender binary that runs the Builder's steps
    python: str                    # Blender's own Python, which runs the Extractor's
    site: list[str] = field(default_factory=list)   # where Blender installed the wheels
    camera: str | None = None      # one Camera Profile for every Map; each Map's own by default
    max_texture_size: int | None = None
    previews: bool = True
    parent_pid: int | None = None  # the Build stops when this process is gone

    @property
    def folder(self) -> Path:
        """The Game's Bundle Folder: its Map Bundles, and the Build's request, state and log."""
        return Path(self.output) / BUNDLE_FOLDER / self.game

    @property
    def library(self) -> Path:
        return Path(self.output) / f"{self.game} Maps"

    def bundle(self, key: str) -> Path:
        return self.folder / Path(*key.split("/"))

    def save(self) -> Path:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / REQUEST_FILE
        _write_json(path, asdict(self))
        return path

    @classmethod
    def load(cls, path) -> "Request":
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class Step:
    id: str
    status: str = "pending"        # pending, running, done, kept, failed, skipped, cancelled
    seconds: float = 0.0
    peak_gb: float = 0.0
    reason: str = ""

    @property
    def map(self) -> str | None:
        kind, _, key = self.id.partition(":")
        return key if kind in ("extract", "map") else None


@dataclass
class State:
    status: str = "running"        # running, done, failed, cancelled, stopped
    pid: int = 0
    started: float = 0.0
    finished: float = 0.0
    steps: list[Step] = field(default_factory=list)
    message: str = ""

    @classmethod
    def load(cls, folder) -> "State | None":
        try:
            data = json.loads((Path(folder) / STATE_FILE).read_text(encoding="utf-8"))
            data["steps"] = [Step(**s) for s in data["steps"]]
            return cls(**data)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def save(self, folder: Path):
        _write_json(Path(folder) / STATE_FILE, asdict(self))

    def current(self) -> Step | None:
        return next((s for s in self.steps if s.status == "running"), None)

    def not_built(self) -> dict[str, str]:
        return {s.map: s.reason or s.status for s in self.steps if s.map and s.status in ("failed", "skipped")}


def steps_of(request: Request) -> list[Step]:
    return ([Step(f"extract:{k}") for k in request.maps] + [Step(f"map:{k}") for k in request.maps]
            + [Step("assets"), Step("finish")])


def is_running(folder) -> bool:
    """Whether a Build is running for this Bundle Folder, by a driver that is still alive."""
    state = State.load(folder)
    return bool(state and state.status == "running" and alive(state.pid))


def cancel(folder):
    Path(folder, CANCEL_FILE).write_text("", encoding="utf-8")


# --- running ----------------------------------------------------------------------------------------

class Driver:
    def __init__(self, request: Request, *, run=memory.run_watched, extract_limits=None, build_limits=None):
        self.request = request
        self.folder = request.folder
        self.run = run
        self.extract_limits = extract_limits or memory.EXTRACT.capped()
        self.build_limits = build_limits or memory.BUILD.capped()
        self.state = State(pid=os.getpid(), started=time.time(), steps=steps_of(request))

    def stopping(self) -> str:
        if (self.folder / CANCEL_FILE).exists():
            return "cancelled"
        if self.request.parent_pid and not alive(self.request.parent_pid):
            return "stopped"
        return ""

    def build(self) -> State:
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / CANCEL_FILE).unlink(missing_ok=True)
        self.state.save(self.folder)
        log = open(self.folder / LOG_FILE, "a", encoding="utf-8")
        try:
            self._log = log
            self._say(f"Build of {len(self.request.maps)} {self.request.game} Maps into {self.request.library}")
            self._steps()
        finally:
            self.state.finished = time.time()
            self.state.save(self.folder)
            self._say(f"Build {self.state.status}{f': {self.state.message}' if self.state.message else ''}")
            log.close()
        return self.state

    def _steps(self):
        by_id = {s.id: s for s in self.state.steps}
        failed_extract: set[str] = set()
        for key in self.request.maps:
            step = by_id[f"extract:{key}"]
            if not self._step(step, self._extract_cmd(key), self.extract_limits, result=True):
                if self.state.status != "running":
                    return
                failed_extract.add(key)
        built = []
        for key in self.request.maps:
            step = by_id[f"map:{key}"]
            if key in failed_extract:
                step.status, step.reason = "skipped", by_id[f"extract:{key}"].reason
                continue
            if self._step(step, self._build_cmd(self._bundles(), [f"map:{key}"]), self.build_limits):
                built.append(key)
            elif self.state.status != "running":
                return
        if not built:
            self.state.status, self.state.message = "failed", "no Map was built"
            for s in (by_id["assets"], by_id["finish"]):
                s.status = "skipped"
            return
        bundles = [self.request.bundle(k) for k in built]
        not_built = [f"{k}={r}" for k, r in self.state.not_built().items()]
        for name in ("assets", "finish"):
            extra = [f"--not-built={item}" for item in not_built] if name == "finish" else []
            if not self._step(by_id[name], self._build_cmd(bundles, [name], extra), self.build_limits):
                if self.state.status == "running":
                    self.state.status, self.state.message = "failed", f"the {name} step failed"
                return
        self.state.status = "done"
        if not_built:
            self.state.message = f"{len(not_built)} of {len(self.request.maps)} Maps not built"

    def _bundles(self) -> list[Path]:
        """Every Map Bundle extracted so far, in build order: the plan sees them all."""
        by_id = {s.id: s for s in self.state.steps}
        return [self.request.bundle(k) for k in self.request.maps if by_id[f"extract:{k}"].status in ("done", "kept")]

    def _step(self, step: Step, cmd: list[str], limits: memory.Limits, *, result: bool = False) -> bool:
        why = self.stopping()
        if why:
            self.state.status = why
            return False
        step.status = "running"
        self.state.save(self.folder)
        self._say(f"{step.id}: started")
        result_file = self.folder / RESULT_FILE
        result_file.unlink(missing_ok=True)
        start = time.time()
        code, peak, reason = self.run(cmd, limits, stop=lambda: bool(self.stopping()),
                                      notice=self._say, stdout=self._log, stderr=self._log, **_quiet())
        step.seconds, step.peak_gb = round(time.time() - start, 1), round(peak / memory.GB, 2)
        outcome = {}
        if result and result_file.is_file():
            outcome = json.loads(result_file.read_text(encoding="utf-8"))
        if reason == "cancelled":
            step.status = "cancelled"
            self.state.status = self.stopping() or "cancelled"
        elif code != 0:
            step.status = "failed"
            step.reason = reason or outcome.get("error") or f"failed (exit code {code}; see {LOG_FILE})"
        else:
            step.status = "kept" if outcome.get("kept") or self._kept(step) else "done"
        self._say(f"{step.id}: {step.status}{f' ({step.reason})' if step.reason else ''} in {step.seconds:.0f} s, "
                  f"peak {step.peak_gb:.2f} GB")
        self.state.save(self.folder)
        return step.status in ("done", "kept")

    def _kept(self, step: Step) -> bool:
        if not step.id.startswith("map:"):
            return False
        try:
            library_state = json.loads((self.request.library / "build.json").read_text(encoding="utf-8"))
            return bool(library_state["maps"][step.map].get("kept"))
        except (OSError, ValueError, KeyError):
            return False

    def _extract_cmd(self, key: str) -> list[str]:
        r = self.request
        cmd = [r.python, "-I", str(JOBS / "worker.py"), "--extension", str(EXTENSION),
               "--result", str(self.folder / RESULT_FILE)]
        for s in r.site:
            cmd += ["--site", s]
        cmd += ["extract", "--game-folder", r.game_folder, "--out", str(Path(r.output) / BUNDLE_FOLDER), "--key", key]
        if r.max_texture_size:
            cmd += ["--max-texture-size", str(r.max_texture_size)]
        return cmd

    def _build_cmd(self, bundles: list[Path], steps: list[str], extra: list[str] = ()) -> list[str]:
        r = self.request
        cmd = [r.blender, "-b", "--factory-startup", "--python", str(JOBS / "blender_worker.py"), "--",
               "--extension", str(EXTENSION), "--library", str(r.library), "--bundles", *map(str, bundles)]
        for s in steps:
            cmd += ["--step", s]
        if r.camera:
            cmd += ["--camera", r.camera]
        if not r.previews:
            cmd.append("--no-previews")
        return cmd + list(extra)

    def _say(self, text: str):
        line = f"[{time.strftime('%H:%M:%S')}] {text}"
        print(line, flush=True)
        self._log.write(line + "\n")
        self._log.flush()


def list_maps(python: str, game_folder: str, site: list[str], result: Path, *, timeout: float = 600) -> dict:
    """The Maps of an install, listed by the worker on Blender's Python: {"game", "maps", "missing"} or
    {"error"}. Runs in the caller's thread; the N-panel calls it from one of its own."""
    import subprocess

    cmd = [python, "-I", str(JOBS / "worker.py"), "--extension", str(EXTENSION)]
    for s in site:
        cmd += ["--site", s]
    cmd += ["--result", str(result), "list", "--game-folder", game_folder]
    result.unlink(missing_ok=True)
    run = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **_quiet())
    if result.is_file():
        return json.loads(result.read_text(encoding="utf-8"))
    tail = (run.stderr or run.stdout).strip().splitlines()[-1:] or [f"exit code {run.returncode}"]
    return {"error": f"Listing the Maps failed: {tail[0]}"}


# --- estimates --------------------------------------------------------------------------------------

# Measured on the KK Golden Maps (1f, park, ground; 157 MB of Scene Bundles): extraction takes about
# 0.5 s per MB of Scene Bundle, a Map file about 0.2 s per MB plus Blender's start, and the Map Bundle
# and the Map Library each take about as much disk as the Scene Bundle.
EXTRACT_S_PER_MB, BUILD_S_PER_MB, BLENDER_START_S, DISK_PER_BYTE = 0.5, 0.2, 5.0, 2.1


def estimate(sizes: list[int]) -> tuple[int, float]:
    """(bytes of disk, seconds) a Build of Maps with these Scene Bundle sizes takes, roughly."""
    mb = sum(sizes) / 2**20
    seconds = mb * (EXTRACT_S_PER_MB + BUILD_S_PER_MB) + BLENDER_START_S * (len(sizes) + 2) if sizes else 0.0
    return int(sum(sizes) * DISK_PER_BYTE), seconds


# --- the platform ---------------------------------------------------------------------------------

def alive(pid: int) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if not handle:
            return False
        try:
            kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            return kernel32.WaitForSingleObject(ctypes.c_void_p(handle), 0) == 0x102   # WAIT_TIMEOUT
        finally:
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _quiet() -> dict:
    """On Windows, a step's process opens no console window."""
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}   # CREATE_NO_WINDOW


def _write_json(path: Path, data):
    tmp = path.with_name(path.name + ".partial")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="kkbp-maps build", description="Runs a Build from a request file.")
    parser.add_argument("--request", required=True, help="a build-request.json (Request)")
    args = parser.parse_args(argv)
    request = Request.load(args.request)
    if is_running(request.folder) and State.load(request.folder).pid != os.getpid():
        print(f"A Build is already running for {request.folder}")
        return 2
    state = Driver(request).build()
    return 0 if state.status == "done" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
