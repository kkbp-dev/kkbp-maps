"""The Builder's side of a Build, run by the driver in its own `blender -b --factory-startup`, so the
extension isn't enabled there and nothing is installed:

    blender -b --factory-startup --python blender_worker.py -- --extension <folder> <Builder arguments>

`--extension` is the folder holding the kkbp_maps package; the rest goes to the Builder's command
line (builder/blender/build.py).
"""

import sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if argv[:1] != ["--extension"] or len(argv) < 2:
    print("blender_worker.py needs --extension <folder> first")
    sys.exit(2)
sys.path.insert(0, argv[1])
try:
    from kkbp_maps.builder.blender.build import main

    code = main(argv[2:])
except Exception:
    import traceback

    traceback.print_exc()
    code = 1
sys.exit(code)
