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
