"""Writes extension/kkbp_maps/deps/lock.json from the pins in deps/__init__.py, reading PyPI's JSON API.

Usage (any Python 3.11 or later; reads PyPI, downloads no package):

    python3 tools/lock_deps.py                 # for the Python of the `min` Blender build
    python3 tools/lock_deps.py --python 3.13   # for another

For every pin the lock holds one file per platform the extension supports: the wheel that platform's
Blender can install (the lowest macOS or glibc version a wheel needs, so the widest reach), or one
pure-Python wheel for all, or, for a project with no wheel, its source, which tools/package.py builds.
Review the diff before committing.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "extension"))
from kkbp_maps import deps  # noqa: E402

MIN_BLENDER = Path("~/.local/opt/blender-5.2.2/blender").expanduser()
# Blender's platform names and the wheel platform tags its builds can load, with the highest glibc or
# macOS version a wheel may need: no higher than what Blender 5.2 itself needs.
PLATFORMS = {
    "linux-x64": (re.compile(r"^(?:manylinux_(\d+)_(\d+)|manylinux(1|2010|2014))_x86_64$"), (2, 28)),
    "windows-x64": (re.compile(r"^win_amd64$"), None),
    "macos-arm64": (re.compile(r"^macosx_(\d+)_(\d+)_(?:arm64|universal2)$"), (11, 2)),
}
LEGACY_MANYLINUX = {"1": (2, 5), "2010": (2, 12), "2014": (2, 17)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--python", help="major.minor; the min Blender build's by default")
    args = parser.parse_args(argv)
    python = args.python or blender_python()
    packages = []
    for name, version in deps.PINS.items():
        release = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60))
        files = pick(release["urls"], python)
        if not files:
            print(f"{name} {version}: no file for Python {python}")
            return 1
        packages.append({"name": name, "version": version, "files": files})
        print(f"{name} {version}: {', '.join(f'{k} {v['filename']}' for k, v in files.items())}")
    out = {"python": python, "platforms": sorted(PLATFORMS), "packages": packages}
    deps.LOCK.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {deps.LOCK.relative_to(REPO)}; review the diff before committing")
    return 0


def blender_python() -> str:
    out = subprocess.run([str(MIN_BLENDER), "-b", "--factory-startup", "--python-expr",
                          "import sys; print('PYTHON', *sys.version_info[:2])"], capture_output=True, text=True)
    major, minor = next(l.split()[1:3] for l in out.stdout.splitlines() if l.startswith("PYTHON "))
    return f"{major}.{minor}"


def pick(urls: list[dict], python: str) -> dict:
    """{platform or "any" or "source": file} for one release."""
    def record(u):
        return {"filename": u["filename"], "url": u["url"], "size": u["size"], "sha256": u["digests"]["sha256"]}

    wheels = [(u, wheel_tags(u["filename"])) for u in urls if u["filename"].endswith(".whl")]
    wheels = [(u, t) for u, t in wheels if t and fits_python(t, python)]
    pure = [u for u, (_, _, plats) in wheels if plats == {"any"}]
    if pure:
        return {"any": record(pure[0])}
    out = {}
    for platform, (pattern, ceiling) in PLATFORMS.items():
        best = None
        for u, (_, _, plats) in wheels:
            for tag in plats:
                m = pattern.match(tag)
                if not m:
                    continue
                needs = needed_version(m)
                if ceiling and needs and needs > ceiling:
                    continue
                if best is None or (needs or (0, 0)) < best[0]:
                    best = (needs or (0, 0), u)
        if best:
            out[platform] = record(best[1])
    if len(out) == len(PLATFORMS):
        return out
    source = [u for u in urls if u["filename"].endswith(".tar.gz")]
    return {"source": record(source[0])} if source and not wheels else {}


def wheel_tags(filename: str):
    parts = filename[:-4].split("-")
    if len(parts) < 5:
        return None
    pythons, abis, plats = parts[-3:]
    return set(pythons.split(".")), set(abis.split(".")), set(plats.split("."))


def fits_python(tags, python: str) -> bool:
    pythons, abis, _ = tags
    major, minor = (int(p) for p in python.split("."))
    cp = f"cp{major}{minor}"
    if cp in pythons and cp in abis:
        return True
    if "abi3" in abis:
        return any(p.startswith("cp3") and int(p[3:]) <= minor for p in pythons if p[3:].isdigit())
    return "none" in abis and any(p in ("py3", f"py{major}{minor}") for p in pythons)


def needed_version(m: re.Match):
    groups = [g for g in m.groups() if g is not None]
    if not groups:
        return None
    if len(groups) == 1:
        return LEGACY_MANYLINUX[groups[0]]
    return int(groups[0]), int(groups[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
