"""tools/package.py without downloading or zipping: what may ship, the manifest's wheels, and the
wheel it builds from a pure-Python source."""

import io
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "tools"))
import package  # noqa: E402


def test_everything_in_the_extension_may_ship():
    for path in package.SOURCE.rglob("*"):
        rel = path.relative_to(package.SOURCE)
        if path.is_file() and not set(rel.parts) & package.SKIPPED_DIRS and path.suffix != ".pyc":
            assert package.file_problem(rel, path.stat().st_size) is None, rel


@pytest.mark.parametrize("name", ["textures/a.png", "Maps/1f.blend", "x.unity3d", "a.exr", "lib.so"])
def test_game_content_and_binaries_may_not(name):
    assert package.file_problem(Path(name), 10) is not None


def test_a_big_file_may_not():
    assert "MB" in package.file_problem(Path("names/KK.toml"), 3 * 2**20)


def test_the_manifest_lists_the_wheels_before_its_first_table():
    text = (package.SOURCE / "blender_manifest.toml").read_text(encoding="utf-8")
    out = package.with_wheels(text, ["b-1-py3-none-any.whl", "a-1-cp313-cp313-win_amd64.whl"])
    import tomllib
    data = tomllib.loads(out)
    assert data["wheels"] == ["./wheels/a-1-cp313-cp313-win_amd64.whl", "./wheels/b-1-py3-none-any.whl"]
    assert data["permissions"]["files"]


def _sdist(tmp_path: Path) -> Path:
    path = tmp_path / "demo-0.1.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in {"demo-0.1/demo/__init__.py": b"X = 1\n", "demo-0.1/demo/sub.py": b"Y = 2\n",
                           "demo-0.1/PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 0.1\n",
                           "demo-0.1/LICENSE": b"MIT\n", "demo-0.1/tests/test_x.py": b""}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_a_pure_wheel_is_built_the_same_every_time(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "WHEELS", tmp_path)
    sdist = _sdist(tmp_path)
    first = package.build_pure_wheel(sdist, {"name": "demo", "version": "0.1"}).read_bytes()
    wheel = package.build_pure_wheel(sdist, {"name": "demo", "version": "0.1"})
    assert wheel.name == "demo-0.1-py3-none-any.whl" and wheel.read_bytes() == first
    with zipfile.ZipFile(wheel) as z:
        names = set(z.namelist())
        assert {"demo/__init__.py", "demo/sub.py", "demo-0.1.dist-info/METADATA", "demo-0.1.dist-info/WHEEL",
                "demo-0.1.dist-info/RECORD", "demo-0.1.dist-info/licenses/LICENSE"} <= names
        assert "tests/test_x.py" not in names
        assert b"Tag: py3-none-any" in z.read("demo-0.1.dist-info/WHEEL")


def test_a_wheel_built_that_way_imports(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "WHEELS", tmp_path)
    wheel = package.build_pure_wheel(_sdist(tmp_path), {"name": "demo", "version": "0.1"})
    import subprocess
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(wheel)!r}); "
                          "import demo.sub; print(demo.X + demo.sub.Y)"], capture_output=True, text=True)
    assert out.stdout.strip() == "3", out.stderr
