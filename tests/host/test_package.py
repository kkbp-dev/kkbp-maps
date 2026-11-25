"""The extension's package: its manifest, its version, and an __init__.py that loads without bpy."""

import subprocess
import sys
import tomllib

from conftest import EXTENSION, PACKAGE_PARENT


def manifest() -> dict:
    return tomllib.loads((PACKAGE_PARENT / "blender_manifest.toml").read_text(encoding="utf-8"))


def test_one_version_for_the_manifest_the_extractor_and_the_builder():
    import kkbp_maps
    from kkbp_maps import builder, extractor

    assert manifest()["version"] == kkbp_maps.VERSION == extractor.VERSION == builder.VERSION


def test_the_manifest_names_the_three_platforms_and_blender_5_2():
    m = manifest()
    assert m["id"] == PACKAGE_PARENT.name
    assert sorted(m["platforms"]) == ["linux-x64", "macos-arm64", "windows-x64"]
    assert m["blender_version_min"] == "5.2.0"
    assert "wheels" not in m, "tools/package.py writes the wheels into the copy it packages (ADR 0029)"
    assert "network" not in m.get("permissions", {})


def test_the_package_imports_without_bpy():
    probe = (f"import sys; sys.path.insert(0, {str(EXTENSION)!r}); import kkbp_maps, kkbp_maps.extractor.extract, "
             "kkbp_maps.builder.plan; print('bpy' in sys.modules)")
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr
