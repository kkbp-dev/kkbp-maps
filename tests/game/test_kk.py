"""Tests on the developer's own KK install and Golden Maps (ADR 0006, 0007). They skip, with a reason,
where the install or the Golden Maps aren't there; make the Golden Maps with tools/golden.py."""

import json
import os
import sys
from pathlib import Path

import pytest

from bundle import check
from conftest import REPO

GAMES = Path(os.environ.get("KKBP_GAMES_DIR", REPO.parent / "games"))
KK_ROOT = GAMES / "Koikatsu"
GOLDEN = REPO / "golden" / "KK"
SNAPSHOT = REPO / "tests" / "snapshots" / "extract" / "KK.json"
GOLDEN_MAPS = ["map/scene/1f", "map/scene/park", "map/scene/ground"]

needs_kk = pytest.mark.skipif(not (KK_ROOT / "Koikatu_Data").is_dir(), reason=f"no KK install in {KK_ROOT}")


@needs_kk
def test_every_listed_map_is_installed():
    pytest.importorskip("UnityPy")
    from kkbp_maps.extractor.games import detect
    from kkbp_maps.extractor.maplist import camera_profile, list_maps

    install = detect(KK_ROOT)
    maps, missing = list_maps(install)
    assert missing == []
    keys = {m.key for m in maps}
    assert set(GOLDEN_MAPS) <= keys
    assert {"studio/map/bushitu", "studio/map/akikyoushitu", "map/scene/livestage_s"} <= keys
    by_key = {m.key: m for m in maps}
    assert camera_profile(install, by_key["map/scene/livestage_s"]) == "studio"
    assert [e.list for e in by_key["map/scene/1f"].entries] == ["map", "studio"]


def golden(key):
    path = GOLDEN / Path(*key.split("/"))
    if not (path / "manifest.json").is_file():
        pytest.skip(f"no Golden Map {key}: make it with tools/golden.py")
    return path


@pytest.mark.parametrize("key", GOLDEN_MAPS)
def test_golden_maps_pass_the_deep_check(key):
    assert check(golden(key), deep=True) == []


@pytest.mark.parametrize("key", GOLDEN_MAPS)
def test_golden_maps_match_the_snapshot(key):
    path = golden(key)
    if not SNAPSHOT.is_file():
        pytest.skip("no extraction snapshot recorded yet")
    sys.path.insert(0, str(REPO / "tools"))
    from golden import summary

    recorded = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert key in recorded, f"{key} isn't in the snapshot"
    assert summary(path) == recorded[key]
