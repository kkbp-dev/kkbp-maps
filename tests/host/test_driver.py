"""The Build driver, with its steps faked: what runs in what order, what is left out, cancelling."""

import json
import os
import sys
from pathlib import Path

import pytest

from conftest import REPO
from kkbp_maps.jobs import driver
from kkbp_maps.jobs.driver import Driver, Request, State
from kkbp_maps.jobs.memory import Limits

GAME = REPO.parent / "games" / "Koikatsu"


def request(tmp_path, maps=("map/scene/1f", "map/scene/park"), **kw) -> Request:
    return Request(game="KK", game_folder=str(tmp_path / "game"), output=str(tmp_path / "out"), maps=list(maps),
                   blender="blender", python="python", site=["/site"], parent_pid=os.getpid(), **kw)


class FakeRun:
    """Stands in for run_watched: records each command, and fails or cancels where told to."""

    def __init__(self, req: Request, fail=(), memory=(), kept=(), cancel_at=None):
        self.req, self.fail, self.memory, self.kept, self.cancel_at = req, set(fail), set(memory), set(kept), cancel_at
        self.steps = []

    def __call__(self, cmd, limits, *, stop, notice, **popen):
        step = self.step_of(cmd)
        self.steps.append(step)
        self.cmd = cmd
        if step == self.cancel_at:
            driver.cancel(self.req.folder)
            assert stop()
            return -9, 0, "cancelled"
        if step in self.memory:
            return -9, 4 * 2**30, f"stopped: it passed {limits.max_rss_gb} GB"
        if step in self.fail:
            return 1, 0, ""
        if step.startswith("extract:"):
            result = Path(cmd[cmd.index("--result") + 1])
            result.write_text(json.dumps({"bundle": "x", "kept": step in self.kept}))
        return 0, 2**30, ""

    @staticmethod
    def step_of(cmd):
        if "extract" in cmd:
            return "extract:" + cmd[cmd.index("--key") + 1]
        return cmd[cmd.index("--step") + 1]


def run(req, **kw):
    fake = FakeRun(req, **kw)
    state = Driver(req, run=fake, extract_limits=Limits(3.0), build_limits=Limits(8.0)).build()
    return state, fake


def test_every_map_is_extracted_then_built_then_the_assets_and_the_report(tmp_path):
    req = request(tmp_path)
    state, fake = run(req, kept=["extract:map/scene/park"])
    assert fake.steps == ["extract:map/scene/1f", "extract:map/scene/park", "map:map/scene/1f", "map:map/scene/park",
                          "assets", "finish"]
    assert state.status == "done" and state.message == ""
    assert [s.status for s in state.steps] == ["done", "kept", "done", "done", "done", "done"]
    assert State.load(req.folder).status == "done"
    log = (req.folder / driver.LOG_FILE).read_text()
    assert "extract:map/scene/1f: done" in log and "Build done" in log


def test_the_steps_run_on_blenders_python_and_in_blender(tmp_path):
    req = request(tmp_path, camera="game", max_texture_size=2048, previews=False)
    fake = FakeRun(req)
    d = Driver(req, run=fake)
    extract = d._extract_cmd("map/scene/1f")
    assert extract[:3] == ["python", "-I", str(driver.JOBS / "worker.py")]
    assert extract[extract.index("--site") + 1] == "/site" and extract[-2:] == ["--max-texture-size", "2048"]
    assert Path(extract[extract.index("--out") + 1]) == Path(req.output) / "Map Bundles"
    build = d._build_cmd([req.bundle("map/scene/1f")], ["map:map/scene/1f"])
    assert build[:3] == ["blender", "-b", "--factory-startup"]
    assert Path(build[build.index("--library") + 1]) == Path(req.output) / "KK Maps"
    assert ["--camera", "game"] == build[build.index("--camera"):build.index("--camera") + 2] and "--no-previews" in build


def test_a_map_whose_extraction_fails_is_left_out_and_reported(tmp_path):
    req = request(tmp_path)
    state, fake = run(req, memory=["extract:map/scene/1f"])
    assert "map:map/scene/1f" not in fake.steps
    assert state.status == "done" and state.message == "1 of 2 Maps not built"
    assert state.not_built() == {"map/scene/1f": "stopped: it passed 3.0 GB"}
    finish = fake.cmd
    assert "--not-built=map/scene/1f=stopped: it passed 3.0 GB" in finish
    bundles = finish[finish.index("--bundles") + 1:finish.index("--step")]
    assert bundles == [str(req.bundle("map/scene/park"))]


def test_a_map_file_that_fails_is_left_out_of_the_assets(tmp_path):
    req = request(tmp_path)
    state, fake = run(req, fail=["map:map/scene/park"])
    assert state.status == "done"
    assert state.not_built()["map/scene/park"] == "exit code 1; see build.log"


def test_nothing_built_fails_the_build(tmp_path):
    state, fake = run(request(tmp_path), fail=["extract:map/scene/1f", "extract:map/scene/park"])
    assert state.status == "failed" and "assets" not in fake.steps


def test_a_failed_asset_step_fails_the_build(tmp_path):
    state, fake = run(request(tmp_path), fail=["assets"])
    assert state.status == "failed" and "finish" not in fake.steps


def test_cancelling_stops_the_current_step_and_the_build(tmp_path):
    req = request(tmp_path)
    state, fake = run(req, cancel_at="map:map/scene/1f")
    assert state.status == "cancelled" and fake.steps[-1] == "map:map/scene/1f"
    assert {s.id: s.status for s in state.steps}["map:map/scene/1f"] == "cancelled"
    second, fake = run(req)   # running it again resumes, and clears the cancel
    assert second.status == "done"


def test_the_build_stops_when_blender_is_gone(tmp_path, monkeypatch):
    req = request(tmp_path)
    monkeypatch.setattr(driver, "alive", lambda pid: False)
    state, fake = run(req)
    assert state.status == "stopped" and fake.steps == []


def test_the_request_round_trips(tmp_path):
    req = request(tmp_path, camera="studio")
    assert Request.load(req.save()) == req
    assert req.save() == req.folder / driver.REQUEST_FILE


def test_this_process_is_alive_and_a_finished_one_isnt():
    import subprocess
    assert driver.alive(os.getpid())
    proc = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    proc.wait()
    assert not driver.alive(proc.pid)


def test_the_estimate_grows_with_the_maps():
    disk, seconds = driver.estimate([72 * 2**20, 31 * 2**20])
    assert disk == int(103 * 2**20 * driver.DISK_PER_BYTE)
    assert 90 < seconds < 120
    assert driver.estimate([]) == (0, 0.0)


@pytest.mark.skipif(not GAME.is_dir(), reason="no KK install")
def test_the_worker_lists_the_maps_on_this_python(tmp_path):
    listed = driver.list_maps(sys.executable, str(GAME), [], tmp_path / "list.json")
    assert listed["game"] == "KK" and len(listed["maps"]) > 3
    one = next(m for m in listed["maps"] if m["key"] == "map/scene/park")
    assert one["camera"] in ("game", "studio") and one["bytes"] > 0


def test_the_worker_names_a_folder_that_isnt_a_game(tmp_path):
    listed = driver.list_maps(sys.executable, str(tmp_path), [], tmp_path / "list.json")
    assert "isn't the folder of a KK, KKS or SVS install" in listed["error"]


def test_an_extraction_error_reaches_the_report_in_words(tmp_path, monkeypatch):
    from kkbp_maps.jobs import worker
    from kkbp_maps.extractor import games

    monkeypatch.setattr(games, "detect", lambda folder: object())
    monkeypatch.setattr(worker, "extract_result", lambda install, args: (_ for _ in ()).throw(
        RuntimeError("material Default-Diffuse's shader isn't in the bundle")))
    result = tmp_path / "r.json"
    code = worker.main(["--extension", str(tmp_path), "--result", str(result), "extract", "--game-folder", "g",
                        "--out", "o", "--key", "k"])
    assert code == 1
    assert json.loads(result.read_text())["error"] == "RuntimeError: material Default-Diffuse's shader isn't in the bundle"
