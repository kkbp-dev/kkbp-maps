"""bundle/ loads without bpy and with nothing outside the standard library."""

import ast
import subprocess
import sys

from conftest import PACKAGE_PARENT

PACKAGE = PACKAGE_PARENT / "bundle"


def test_bundle_imports_only_the_standard_library():
    probe = (
        "import sys; before = set(sys.modules); import bundle; "
        "new = {m.split('.')[0] for m in set(sys.modules) - before}; "
        "foreign = sorted(m for m in new if m != 'bundle' and m not in sys.stdlib_module_names and not m.startswith('_')); "
        "print(','.join(foreign))"
    )
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(PACKAGE_PARENT)!r}); {probe}"],
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "", f"bundle/ loads {out.stdout.strip()}"


def test_bundle_imports_itself_only_relatively():
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module.split(".")[0] in sys.stdlib_module_names, f"{path.name} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in sys.stdlib_module_names, f"{path.name} imports {alias.name}"


# --- the Extractor --------------------------------------------------------------------------------

EXTRACTOR = PACKAGE_PARENT / "extractor"
EXTRACTOR_THIRD_PARTY = {"numpy", "PIL", "UnityPy", "lz4"}   # lz4: a pinned UnityPy dependency, read by bundles.py


def test_the_extractor_never_imports_bpy_and_only_its_dependencies():
    for path in sorted(EXTRACTOR.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                assert top != "bpy", f"{path.name} imports bpy"
                assert top in sys.stdlib_module_names or top in EXTRACTOR_THIRD_PARTY, f"{path.name} imports {name}"


def test_only_unity_py_imports_unitypy():
    for path in sorted(EXTRACTOR.glob("*.py")):
        if path.name == "unity.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(n.startswith("UnityPy") for n in names), f"{path.name} imports UnityPy"


def test_only_space_py_holds_the_axis_matrix():
    """ADR 0011: nothing else converts axes. The tell-tale is building (-x, -z, y) by hand."""
    for path in sorted(EXTRACTOR.glob("*.py")):
        if path.name != "space.py":
            text = path.read_text(encoding="utf-8")
            assert "[-x, -z, y]" not in text and "np.diag([-1" not in text, f"{path.name} converts axes"


# --- the Builder ----------------------------------------------------------------------------------

BUILDER = PACKAGE_PARENT / "builder"


def test_the_builders_plan_imports_only_the_standard_library():
    """Everything in builder/ outside builder/blender/ is decided without Blender, so it is host-tested."""
    for path in sorted(BUILDER.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
            for name in names:
                assert name.split(".")[0] in sys.stdlib_module_names, f"builder/{path.name} imports {name}"


def test_only_compat_checks_blenders_version():
    for path in sorted(PACKAGE_PARENT.rglob("*.py")):
        if "compat" in path.relative_to(PACKAGE_PARENT).parts:
            continue
        assert "app.version" not in path.read_text(encoding="utf-8"), f"{path} checks Blender's version"


def test_unitypy_imports_without_the_fmod_packages():
    """ADR 0029: the zips leave out fmod_toolkit and pyfmodex; unity.unitypy() stands in for them."""
    pytest = __import__("pytest")
    pytest.importorskip("UnityPy")
    probe = (
        "import sys, importlib.abc\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name.split('.')[0] in ('fmod_toolkit', 'pyfmodex'): raise ImportError(name)\n"
        "sys.meta_path.insert(0, Block())\n"
        f"sys.path.insert(0, {str(PACKAGE_PARENT.parent)!r})\n"
        "from kkbp_maps.extractor.unity import unitypy\n"
        "UnityPy = unitypy(); import UnityPy.export.Texture2DConverter\n"
        "print('ok')\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True)
    assert out.stdout.strip() == "ok", out.stderr


# --- the Build driver and the dependency pins -----------------------------------------------------

def test_jobs_and_deps_import_only_the_standard_library():
    """The driver runs on Blender's Python outside Blender; the N-panel imports deps in Blender."""
    for folder in ("jobs", "deps"):
        for path in sorted((PACKAGE_PARENT / folder).glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                    [node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 else []
                for name in names:
                    top = name.split(".")[0]
                    assert top in sys.stdlib_module_names or top == "kkbp_maps", f"{folder}/{path.name} imports {name}"
