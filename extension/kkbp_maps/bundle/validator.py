"""A JSON Schema (draft 2020-12) validator for only the keywords the contract's schemas use (ADR 0013).

Standard library only. A test checks that it agrees with `jsonschema` on whether a file is valid, and
another that the schemas use no keyword outside KEYWORDS and ANNOTATIONS.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urldefrag, urljoin

SCHEMA_DIR = Path(__file__).parent / "schema"

# The keywords this validator checks, and those it reads past.
KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "enum", "const", "pattern",
    "items", "minItems", "maxItems", "minimum", "maximum", "minLength", "$ref", "oneOf",
})
ANNOTATIONS = frozenset({"$schema", "$id", "$defs", "title", "description", "x-unique"})


class Schemas:
    """The contract's schemas, loaded once, by `$id`."""

    def __init__(self, folder: Path = SCHEMA_DIR):
        self.by_id: dict[str, dict] = {}
        for path in sorted(folder.rglob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            self.by_id[schema["$id"]] = schema
        self._patterns: dict[str, re.Pattern] = {}

    def url(self, name: str) -> str:
        """The `$id` of a schema by file name, such as 'scene.schema.json'."""
        for url in self.by_id:
            if url.rsplit("/", 1)[-1] == name and "/sets/" not in url:
                return url
        raise KeyError(name)

    def problems(self, name: str, value) -> list[str]:
        """Every way `value` breaks the schema called `name`, as 'path: message' strings."""
        url = self.url(name)
        out: list[str] = []
        self._check(self.by_id[url], url, value, "", out)
        return out

    # --- the keywords -----------------------------------------------------------------

    def _check(self, schema: dict, base: str, value, path: str, out: list[str]):
        if "$ref" in schema:
            target, target_base = self._resolve(schema["$ref"], base)
            self._check(target, target_base, value, path, out)
        if "type" in schema:
            types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_is_type(value, t) for t in types):
                out.append(f"{_where(path)}: {_show(value)} isn't of type {' or '.join(types)}")
                return
        if "const" in schema and not _equal(value, schema["const"]):
            out.append(f"{_where(path)}: {_show(value)} should be {_show(schema['const'])}")
        if "enum" in schema and not any(_equal(value, e) for e in schema["enum"]):
            out.append(f"{_where(path)}: {_show(value)} isn't one of {', '.join(_show(e) for e in schema['enum'])}")
        if "oneOf" in schema:
            self._one_of(schema["oneOf"], base, value, path, out)
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append(f"{_where(path)}: {_show(value)} is shorter than {schema['minLength']}")
            if "pattern" in schema and not self._pattern(schema["pattern"]).search(value):
                out.append(f"{_where(path)}: {_show(value)} doesn't match {schema['pattern']}")
        if _is_type(value, "number"):
            if "minimum" in schema and value < schema["minimum"]:
                out.append(f"{_where(path)}: {_show(value)} is below the minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                out.append(f"{_where(path)}: {_show(value)} is above the maximum {schema['maximum']}")
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                out.append(f"{_where(path)}: has {len(value)} items, fewer than {schema['minItems']}")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                out.append(f"{_where(path)}: has {len(value)} items, more than {schema['maxItems']}")
            if "items" in schema:
                for i, item in enumerate(value):
                    self._check(schema["items"], base, item, f"{path}/{i}", out)
        if isinstance(value, dict):
            properties = schema.get("properties", {})
            for key in schema.get("required", ()):
                if key not in value:
                    out.append(f"{_where(path)}: '{key}' is missing")
            for key, item in value.items():
                if key in properties:
                    self._check(properties[key], base, item, f"{path}/{key}", out)
                elif schema.get("additionalProperties") is False:
                    out.append(f"{_where(path)}: '{key}' isn't allowed here")
                elif isinstance(schema.get("additionalProperties"), dict):
                    self._check(schema["additionalProperties"], base, item, f"{path}/{key}", out)

    def _one_of(self, branches, base, value, path, out):
        results = []
        for branch in branches:
            found: list[str] = []
            self._check(branch, base, value, path, found)
            results.append(found)
        matches = sum(1 for r in results if not r)
        if matches == 1:
            return
        if matches > 1:
            out.append(f"{_where(path)}: matches {matches} of the alternatives, not exactly one")
            return
        # None matches. Where the alternatives are told apart by a constant (a 'kind', 'mode' or 'type'),
        # report the problems of the one whose constant the value has.
        tagged = [r for b, r in zip(branches, results) if self._tag_matches(b, base, value)]
        if len(tagged) == 1:
            out.extend(tagged[0])
        else:
            out.append(f"{_where(path)}: {_show(value)} matches none of the alternatives")

    def _tag_matches(self, branch, base, value) -> bool:
        while "$ref" in branch:
            branch, base = self._resolve(branch["$ref"], base)
        consts = {k: p["const"] for k, p in branch.get("properties", {}).items() if "const" in p}
        return bool(consts) and isinstance(value, dict) and all(
            k in value and _equal(value[k], c) for k, c in consts.items())

    def _resolve(self, ref: str, base: str):
        url, fragment = urldefrag(urljoin(base, ref))
        target = self.by_id[url]
        for part in filter(None, fragment.split("/")):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return target, url

    def _pattern(self, pattern: str) -> re.Pattern:
        if pattern not in self._patterns:
            self._patterns[pattern] = re.compile(pattern)
        return self._patterns[pattern]


def _is_type(value, name: str) -> bool:
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    if isinstance(value, bool):
        return False
    if name == "number":
        return isinstance(value, (int, float))
    if name == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    raise ValueError(f"unknown JSON type {name}")


def _equal(a, b) -> bool:
    """JSON equality: true isn't 1, and 1 is 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    return a == b


def _where(path: str) -> str:
    return path[1:] if path else "(top)"


def _show(value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."
