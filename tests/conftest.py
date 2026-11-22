"""Puts the contract and the Extractor on the path."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXTENSION = REPO / "extension"
PACKAGE_PARENT = EXTENSION / "kkbp_maps"
SCHEMAS = PACKAGE_PARENT / "bundle" / "schema"

# bundle/ is imported as a top-level package, as the tools do; the Extractor as kkbp_maps.extractor,
# a namespace package until the extension gets its own __init__.py.
for folder in (PACKAGE_PARENT, EXTENSION):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
