"""Checks a Map Bundle against the contract: its files, its JSON Schemas and the rules in README.md."""

from __future__ import annotations

import json
from pathlib import Path

from . import hashing, rules
from .validator import Schemas

SCHEMA_VERSION = "0.2"
MAX_NUMBER_EXAMPLES = 3

_schemas: Schemas | None = None


def schemas() -> Schemas:
    global _schemas
    if _schemas is None:
        _schemas = Schemas()
    return _schemas


def closed_sets() -> dict[str, list[str]]:
    """Each closed set's values in order, by the set's file name without '.schema.json'."""
    return {url.rsplit("/", 1)[-1].removesuffix(".schema.json"): s["enum"]
            for url, s in schemas().by_id.items() if "/sets/" in url}


def check(path, *, deep: bool = False) -> list[str]:
    """Every problem in the Map Bundle at `path` (its folder or its manifest.json); [] when it is valid.

    `deep` also re-hashes every mesh file and checks its indices, which reads all of them.
    """
    root = Path(path).expanduser()
    if root.name == "manifest.json" and root.is_file():
        root = root.parent
    if not root.is_dir():
        return [f"{root} isn't a folder"]
    if not (root / "manifest.json").is_file():
        return [f"{root} has no manifest.json, so it is an unfinished Map Bundle or not one at all"]

    problems: list[str] = []
    manifest = _load(root, "manifest", problems)
    if manifest is None:
        return problems
    version = manifest.get("schema_version") if isinstance(manifest, dict) else None
    if version != SCHEMA_VERSION:
        return [f"manifest.json: the bundle is Schema Version {version}; this checker reads only "
                f"{SCHEMA_VERSION} (ADR 0014), so extract the Map again"]

    data = {"manifest": manifest}
    for name in rules.DATA_FILES[1:]:
        data[name] = _load(root, name, problems)
    for name, value in data.items():
        if value is not None:
            problems.extend(f"{name}.json: {p}" for p in schemas().problems(f"{name}.schema.json", value))
    if problems:
        return problems  # the rules need every file, with the shape its schema gives it
    return rules.check(root, data, closed_sets(), deep)


def _load(root: Path, name: str, problems: list[str]):
    """The parsed JSON of a data file, or None with its problems added."""
    file = f"{name}.json"
    path = root / file
    if not path.is_file():
        problems.append(f"{file} is missing")
        return None
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        problems.append(f"{file} starts with a byte order mark; bundle JSON is UTF-8 without one")
        return None
    bad_numbers: list[str] = []

    def number(text: str) -> float:
        if not hashing.is_shortest32(text):
            bad_numbers.append(text)
        return float(text)

    def constant(text: str):
        raise ValueError(f"{text} isn't a JSON number")

    try:
        value = json.loads(raw.decode("utf-8"), parse_float=number, parse_constant=constant)
    except UnicodeDecodeError as ex:
        problems.append(f"{file} isn't UTF-8 ({ex.reason} at byte {ex.start})")
        return None
    except ValueError as ex:
        problems.append(f"{file} isn't valid JSON ({ex})")
        return None
    if bad_numbers:
        examples = ", ".join(bad_numbers[:MAX_NUMBER_EXAMPLES])
        problems.append(f"{file}: {len(bad_numbers)} numbers aren't float32 values written shortest, such as {examples}")
    return value
