"""The Extractor's dependencies, which ship as wheels inside each platform's zip (ADR 0029).

PINS is what the extension is tested with. tools/lock_deps.py writes lock.json from it: for every
pin, the one file of that version each platform gets, with its URL, size and SHA-256, so packaging
downloads exactly those files and nothing else. numpy and attrs are Blender's own and aren't pinned
(FROM_BLENDER); the FMOD packages UnityPy declares are left out (extractor/unity.py stands in for them).

Imports only the standard library, and never imports a dependency: Blender's process finds where
they are installed from their metadata alone, and only the Extractor's subprocess loads them.
"""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path

PINS = {  # distribution name -> version; raised only on purpose
    "UnityPy": "1.25.4",
    "Pillow": "12.3.0",
    "lz4": "4.4.5",
    "Brotli": "1.2.1",
    "texture2ddecoder": "1.0.6",
    "etcpak": "0.9.15",
    "astc-encoder-py": "0.1.12",
    "archspec": "0.2.7",
    "fsspec": "2026.9.0",
    "tpk_ar": "0.2.4",   # source only on PyPI: packaging builds its wheel (pure Python)
}
LEFT_OUT = ("fmod_toolkit", "pyfmodex")   # FMOD's licence doesn't let us pass it on (ADR 0029)
# Packages Blender ships in its own Python, which a wheel of ours would replace for Blender and every
# other extension: they are used as Blender has them, at least at these versions (Blender 5.2's).
FROM_BLENDER = {"numpy": (2, 3), "attrs": (25, 3)}
LOCK = Path(__file__).with_name("lock.json")


def lock() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))


def _version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def problems() -> list[str]:
    """What stops the Extractor from running on this Python, in words for the user; empty if nothing."""
    out = []
    wrong = []
    for name, version in PINS.items():
        found = _version(name)
        if found != version:
            wrong.append(f"{name} {version}" + (f" (found {found})" if found else ""))
    if wrong:
        out.append(f"Missing dependencies: {', '.join(wrong)}. Install the kkbp-maps zip made for this "
                   f"platform again; Blender installs its wheels with it.")
    for name, minimum in FROM_BLENDER.items():
        found = _version(name)
        if found is None:
            out.append(f"This Blender has no {name}; kkbp-maps uses the one Blender 5.2 and later ship.")
        elif tuple(int(p) for p in found.split(".")[:2] if p.isdigit()) < minimum:
            out.append(f"This Blender's {name} is {found}; kkbp-maps needs {'.'.join(map(str, minimum))} or "
                       f"later, as Blender 5.2 ships.")
    return out


def site_folders() -> list[str]:
    """The folders the pinned dependencies are installed in, for the Extractor's subprocess's path."""
    out: list[str] = []
    for name in PINS:
        try:
            folder = str(Path(metadata.distribution(name).locate_file("")).resolve())
        except metadata.PackageNotFoundError:
            continue
        if folder not in out:
            out.append(folder)
    return out
