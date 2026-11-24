"""Runs the Builder inside Blender with this repository's extension/ on the path, so nothing is
installed into Blender or the user's profile.

    blender -b --factory-startup --python tools/blender_build.py -- --library OUT --bundles B... [--step S]
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "extension"))

from kkbp_maps.builder.blender.build import main  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
try:
    code = main(argv)
except Exception:
    import traceback
    traceback.print_exc()
    code = 1
sys.exit(code)
