"""Builds the extension's zips, one per platform, with its wheels inside (ADR 0029).

Usage (any Python 3.11 or later; Blender does the zipping):

    python3 tools/package.py                  # dist/kkbp_maps-<version>-<platform>.zip for every platform
    python3 tools/package.py --offline        # only from wheels already downloaded into dist/wheels/

1. Every file in extension/kkbp_maps/deps/lock.json is downloaded once into dist/wheels/ and checked
   against its size and SHA-256; a file that doesn't match is deleted and the run stops.
2. A project with only its source on PyPI (tpk_ar) gets a pure-Python wheel built from that source,
   the same bytes every time.
3. extension/kkbp_maps is copied into dist/stage/ without caches, with LICENSE, NOTICE and the wheels;
   the copy's manifest lists them. Only code, data and documents may be in it (ADR 0007): anything
   else stops the run.
4. `blender --command extension build --split-platforms` makes the zips, which are then validated
   and checked to hold every pinned package's wheel and nothing they shouldn't.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "extension" / "kkbp_maps"
sys.path.insert(0, str(REPO / "extension"))
from kkbp_maps import deps  # noqa: E402

DIST = REPO / "dist"
WHEELS = DIST / "wheels"
STAGE = DIST / "stage"
BLENDER = Path("~/.local/opt/blender-5.2.2/blender").expanduser()   # the min build, as the harness
# What may ship besides the wheels: code, data and documents, none of it from a game (ADR 0007).
ALLOWED_SUFFIXES = {".py", ".toml", ".json", ".md", ".txt"}
ALLOWED_NAMES = {"LICENSE", "NOTICE"}
MAX_FILE_BYTES = 2 * 2**20
SKIPPED_DIRS = {"__pycache__", "wheels"}
ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="don't download; use dist/wheels/ only")
    parser.add_argument("--blender", default=str(BLENDER))
    args = parser.parse_args(argv)
    lock = deps.lock()
    wheels = fetch(lock, offline=args.offline)
    if wheels is None:
        return 1
    stage(wheels)
    manifest = tomllib.loads((SOURCE / "blender_manifest.toml").read_text(encoding="utf-8"))
    for old in DIST.glob(f"{manifest['id']}-{manifest['version']}-*.zip"):
        old.unlink()
    blender = [args.blender, "--factory-startup", "--command", "extension"]
    run = subprocess.run(blender + ["build", "--source-dir", str(STAGE / SOURCE.name), "--output-dir", str(DIST),
                                    "--split-platforms"], capture_output=True, text=True)
    print(run.stdout.strip())
    if run.returncode != 0:
        print(run.stderr.strip())
        return 1
    zips = sorted(DIST.glob(f"{manifest['id']}-{manifest['version']}-*.zip"))
    failed = False
    for z in zips:
        check = subprocess.run(blender + ["validate", str(z)], capture_output=True, text=True)
        problems = ([] if check.returncode == 0 else [(check.stdout + check.stderr).strip()]) + zip_problems(z, lock)
        print(f"{z.name}: {z.stat().st_size / 2**20:.1f} MB, {'ok' if not problems else 'PROBLEMS'}")
        for p in problems:
            print(f"  {p}")
        failed |= bool(problems)
    if len(zips) != len(lock["platforms"]):
        print(f"expected {len(lock['platforms'])} zips, made {len(zips)}")
        failed = True
    return 1 if failed else 0


# --- the wheels ---------------------------------------------------------------------------------------

def fetch(lock: dict, *, offline: bool) -> list[Path] | None:
    """Every wheel the zips need, downloaded and checked, with tpk_ar's built; None if one can't be had."""
    WHEELS.mkdir(parents=True, exist_ok=True)
    out = []
    for package in lock["packages"]:
        for kind, f in package["files"].items():
            path = WHEELS / f["filename"]
            if not _matches(path, f):
                if offline:
                    print(f"{f['filename']} isn't in {WHEELS} (run without --offline to download it)")
                    return None
                print(f"downloading {f['filename']} ({f['size'] / 2**20:.1f} MB)")
                tmp = path.with_name(path.name + ".partial")
                with urllib.request.urlopen(f["url"], timeout=120) as response, open(tmp, "wb") as dst:
                    shutil.copyfileobj(response, dst)
                if not _matches(tmp, f):
                    tmp.unlink()
                    print(f"{f['filename']}: its size or SHA-256 isn't the lock's; deleted. Stopping.")
                    return None
                tmp.replace(path)
            out.append(build_pure_wheel(path, package) if kind == "source" else path)
    return out


def _matches(path: Path, f: dict) -> bool:
    return path.is_file() and path.stat().st_size == f["size"] and _sha256(path.read_bytes()) == f["sha256"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_pure_wheel(sdist: Path, package: dict) -> Path:
    """A py3-none-any wheel of a pure-Python project's source: its top-level package, its PKG-INFO as
    METADATA and its licence. The same bytes every time."""
    name, version = package["name"], package["version"]
    files: dict[str, bytes] = {}
    with tarfile.open(sdist) as tar:
        root = f"{name}-{version}/"
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith(root):
                continue
            rel = member.name[len(root):]
            data = tar.extractfile(member).read()
            if rel.startswith(f"{name}/") and rel.endswith(".py"):
                files[rel] = data
            elif rel == "PKG-INFO":
                files["METADATA"] = data
            elif rel in ("LICENSE", "LICENSE.txt", "LICENSE.md"):
                files["LICENSE"] = data
    if not any(k.startswith(f"{name}/") for k in files) or "METADATA" not in files:
        raise RuntimeError(f"{sdist.name} isn't laid out as a pure-Python project named {name}")
    if any(k.endswith((".so", ".pyd", ".c")) for k in files):
        raise RuntimeError(f"{sdist.name} isn't pure Python")
    info = f"{name}-{version}.dist-info"
    entries = {k: v for k, v in files.items() if k.startswith(f"{name}/")}
    entries[f"{info}/METADATA"] = files["METADATA"]
    if "LICENSE" in files:
        entries[f"{info}/licenses/LICENSE"] = files["LICENSE"]
    entries[f"{info}/WHEEL"] = b"Wheel-Version: 1.0\nGenerator: kkbp-maps tools/package.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    entries[f"{info}/top_level.txt"] = f"{name}\n".encode()
    record = "".join(f"{k},sha256={base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b'=').decode()},{len(v)}\n"
                     for k, v in sorted(entries.items()))
    entries[f"{info}/RECORD"] = (record + f"{info}/RECORD,,\n").encode()
    out = WHEELS / f"{name}-{version}-py3-none-any.whl"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for k in sorted(entries):
            item = zipfile.ZipInfo(k, ZIP_TIME)
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            z.writestr(item, entries[k])
    out.write_bytes(buffer.getvalue())
    return out


# --- the stage --------------------------------------------------------------------------------------

def stage(wheels: list[Path]):
    target = STAGE / SOURCE.name
    if STAGE.exists():
        shutil.rmtree(STAGE)
    for path in sorted(SOURCE.rglob("*")):
        rel = path.relative_to(SOURCE)
        if path.is_dir() or set(rel.parts) & SKIPPED_DIRS or path.suffix == ".pyc":
            continue
        problem = file_problem(rel, path.stat().st_size)
        if problem:
            raise SystemExit(f"{rel.as_posix()}: {problem}; it can't ship (ADR 0007)")
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target / rel)
    for name in ALLOWED_NAMES:
        shutil.copy2(REPO / name, target / name)
    (target / "wheels").mkdir()
    for w in wheels:
        shutil.copy2(w, target / "wheels" / w.name)
    manifest = target / "blender_manifest.toml"
    manifest.write_text(with_wheels(manifest.read_text(encoding="utf-8"), [w.name for w in wheels]),
                        encoding="utf-8", newline="\n")


def file_problem(rel: Path, size: int) -> str | None:
    if rel.suffix not in ALLOWED_SUFFIXES and rel.name not in ALLOWED_NAMES:
        return f"a {rel.suffix or 'suffix-less'} file"
    if size > MAX_FILE_BYTES:
        return f"{size / 2**20:.1f} MB, more than code or tables take"
    return None


def with_wheels(manifest: str, names: list[str]) -> str:
    """The manifest with a `wheels` list naming wheels/<name> for each, before its first table."""
    line = "wheels = [\n" + "".join(f'  "./wheels/{n}",\n' for n in sorted(names)) + "]\n\n"
    at = manifest.index("\n[")
    return manifest[:at + 1] + line + manifest[at + 1:]


def zip_problems(path: Path, lock: dict) -> list[str]:
    """What a built zip holds that it shouldn't, or lacks."""
    platform = next((p for p in lock["platforms"] if path.stem.endswith(p.replace("-", "_")) or path.stem.endswith(p)),
                    None)
    if platform is None:
        return [f"no platform in its name ({', '.join(lock['platforms'])})"]
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        manifest = tomllib.loads(z.read("blender_manifest.toml").decode("utf-8"))
    problems = []
    for n in names:
        rel = Path(n)
        if rel.parts[0] == "wheels":
            continue
        if file_problem(rel, 0):
            problems.append(f"{n}: {file_problem(rel, 0)}")
    shipped = {Path(n).name for n in names if n.startswith("wheels/")}
    for package in lock["packages"]:
        files = package["files"]
        expected = (files.get(platform) or files.get("any") or {}).get("filename") or \
            f"{package['name']}-{package['version']}-py3-none-any.whl"
        if expected not in shipped:
            problems.append(f"no wheel of {package['name']} {package['version']} ({expected})")
    # Blender's --split-platforms keeps the manifest and records the zip's own platform beneath it.
    generated = manifest.get("build", {}).get("generated", {})
    if generated.get("platforms") != [platform]:
        problems.append(f"its manifest's build.generated platforms are {generated.get('platforms')}, not [{platform!r}]")
    listed = {Path(w).name for w in generated.get("wheels", [])}
    if listed != shipped:
        problems.append(f"its manifest lists other wheels than it holds: {sorted(listed ^ shipped)}")
    if any(left in n.lower() for n in shipped for left in deps.LEFT_OUT):
        problems.append("it holds an FMOD wheel (ADR 0029)")
    return problems


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
