"""The Extractor: reads a Game install with UnityPy and writes Map Bundles. Never imports bpy.

    from kkbp_maps.extractor import detect, list_maps, extract
    install = detect("path/to/Koikatsu")
    maps, missing = list_maps(install)
    extract(install, maps[0], "out/")

Imports only the standard library at the top; numpy, Pillow and UnityPy are loaded by the modules that
need them, so the package can be imported to show a message before its dependencies are installed.
"""

NAME = "kkbp-maps"
VERSION = "0.1.0.dev0"
