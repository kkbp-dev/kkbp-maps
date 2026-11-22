"""Puts the bundle package on the path as a top-level package, as the tests and tools import it."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACKAGE_PARENT = REPO / "extension" / "kkbp_maps"
SCHEMAS = PACKAGE_PARENT / "bundle" / "schema"

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))
