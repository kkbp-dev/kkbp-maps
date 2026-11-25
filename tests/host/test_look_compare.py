"""The look check's image measure, on synthetic images."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import look_compare as lc  # noqa: E402


def test_identical_images_pass_with_zero():
    img = np.random.default_rng(1).integers(0, 256, (64, 96, 3), dtype=np.uint8)
    r = lc.compare(img, img)
    assert r.mean_de == 0 and r.p95_de == 0 and r.worst_tile == 0 and r.passed


def test_delta_e2000_matches_sharma_reference_pairs():
    # Pairs 1, 7 and 17 from Sharma, Wu and Dalal's test data.
    a = np.array([[50.0, 2.6772, -79.7751], [50.0, 0.0, 0.0], [50.0, 2.5, 0.0]])
    b = np.array([[50.0, 0.0, -82.7485], [50.0, -1.0, 2.0], [73.0, 25.0, -18.0]])
    np.testing.assert_allclose(lc.delta_e2000(a, b), [2.0425, 2.3669, 27.1492], atol=1e-4)


def test_white_lab_is_100_0_0():
    np.testing.assert_allclose(lc.lab(np.full((1, 1, 3), 255, np.uint8))[0, 0], [100, 0, 0], atol=1e-3)


def test_a_too_bright_region_fails_the_tile_check():
    cap = np.full((80, 80, 3), 120, np.uint8)
    ren = cap.copy()
    ren[:10, :10] = 200   # one tile of the 8 × 8 grid
    r = lc.compare(ren, cap)
    assert r.worst_tile > 1.0 and not r.passed
    assert r.tiles[0, 0] > 0 and np.count_nonzero(r.tiles) == 1


def test_small_noise_passes():
    rng = np.random.default_rng(2)
    cap = rng.integers(40, 216, (80, 80, 3)).astype(np.int16)
    ren = np.clip(cap + rng.integers(-1, 2, cap.shape), 0, 255).astype(np.uint8)
    assert lc.compare(ren, cap.astype(np.uint8)).passed


def test_sizes_must_match():
    with pytest.raises(ValueError):
        lc.compare(np.zeros((4, 4, 3)), np.zeros((4, 5, 3)))


def test_each_pass_has_its_own_tolerance():
    look = {"tolerance": {"pregrade": {"mean_de": 3.0, "tile": 0.25}, "graded": {"mean_de": 5.0, "floor": 0.05}}}
    t = lc.tolerances(look)
    assert t["pregrade"].mean_de == 3.0 and t["pregrade"].tile == 0.25
    assert t["graded"].mean_de == 5.0 and t["graded"].floor == 0.05


def test_a_look_file_without_both_passes_is_refused():
    with pytest.raises(ValueError, match="graded"):
        lc.tolerances({"tolerance": {"pregrade": {}}})


def test_a_view_worse_than_the_snapshot_by_more_than_the_margin_regresses():
    before = {"a": {"mean_de": 2.0, "p95_de": 6.0, "worst_tile": 0.10},
              "b": {"mean_de": 2.0, "p95_de": 6.0, "worst_tile": 0.10},
              "gone": {"mean_de": 1.0, "p95_de": 2.0, "worst_tile": 0.0}}
    now = {"a": {"mean_de": 2.05, "p95_de": 5.0, "worst_tile": 0.11},   # within the margins, or better
           "b": {"mean_de": 2.3, "p95_de": 6.0, "worst_tile": 0.10},
           "new": {"mean_de": 9.0, "p95_de": 20.0, "worst_tile": 1.0}}
    margin = {"mean_de": 0.1, "p95_de": 0.3, "worst_tile": 0.02}
    assert lc.regressions(before, now, margin) == ["b: mean_de 2.0 → 2.3", "gone: not measured"]
