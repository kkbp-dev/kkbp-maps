"""The dependency pins, their lock, and how Blender's process finds them without importing them."""

import ast
import sys
from importlib import metadata

import pytest

from conftest import PACKAGE_PARENT
from kkbp_maps import deps


def test_the_lock_holds_every_pin_and_nothing_else():
    lock = deps.lock()
    assert {(p["name"], p["version"]) for p in lock["packages"]} == set(deps.PINS.items())
    assert sorted(lock["platforms"]) == ["linux-x64", "macos-arm64", "windows-x64"]
    for p in lock["packages"]:
        kinds = set(p["files"])
        assert kinds in ({"any"}, {"source"}, set(lock["platforms"])), f"{p['name']}: {sorted(kinds)}"
        for f in p["files"].values():
            assert len(f["sha256"]) == 64 and f["url"].startswith("https://files.pythonhosted.org/")


def test_the_lock_is_for_this_python():
    """The dev venv runs the tests on the Python the zips are locked for."""
    assert deps.lock()["python"] == f"{sys.version_info.major}.{sys.version_info.minor}"


def test_the_tests_run_the_pinned_versions():
    for name, version in deps.PINS.items():
        assert metadata.version(name) == version, f"the dev venv has {name} {metadata.version(name)}, not {version}"


def test_numpy_isnt_pinned_and_fmod_is_left_out():
    names = {n.lower() for n in deps.PINS}
    assert "numpy" not in names
    assert not names & set(deps.LEFT_OUT)


def test_no_problems_where_everything_is_installed():
    assert deps.problems() == []


def test_a_missing_pin_is_named(monkeypatch):
    real = deps._version
    monkeypatch.setattr(deps, "_version", lambda n: None if n == "UnityPy" else real(n))
    (problem,) = deps.problems()
    assert "UnityPy 1.25.4" in problem and "zip made for this platform" in problem


def test_an_old_numpy_is_named(monkeypatch):
    real = deps._version
    monkeypatch.setattr(deps, "_version", lambda n: "1.26.4" if n == "numpy" else real(n))
    (problem,) = deps.problems()
    assert "1.26.4" in problem


def test_site_folders_hold_the_pins():
    folders = deps.site_folders()
    assert folders
    import UnityPy
    assert any(UnityPy.__file__.startswith(f) for f in folders)


def test_deps_imports_only_the_standard_library():
    for path in sorted((PACKAGE_PARENT / "deps").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                assert name.split(".")[0] in sys.stdlib_module_names, f"deps/{path.name} imports {name}"
