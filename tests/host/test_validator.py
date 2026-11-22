"""The bundle's own schema validator (ADR 0013): it agrees with jsonschema, and the schemas use only
the keywords it knows."""

import copy
import json

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from bundle import SCHEMA_VERSION, schemas
from bundle.rules import DATA_FILES
from bundle.validator import ANNOTATIONS, KEYWORDS
from bundle_builder import MapBundleBuilder, read_json
from conftest import SCHEMAS

SCHEMA_FILES = sorted(SCHEMAS.rglob("*.schema.json"))
WRONG_VALUES = [None, True, 7, -1, 0.5, "x", [], {}]


def _jsonschema(name):
    resources = [(s["$id"], Resource.from_contents(s)) for s in (json.loads(p.read_text(encoding="utf-8"))
                                                                 for p in SCHEMA_FILES)]
    registry = Registry().with_resources(resources)
    return Draft202012Validator(dict(resources)[schemas().url(name)].contents, registry=registry)


def _walk(schema, path=""):
    yield path, schema
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key in ("properties", "$defs"):
                for name, sub in value.items():
                    yield from _walk(sub, f"{path}/{key}/{name}")
            elif key in ("items", "additionalProperties") and isinstance(value, dict):
                yield from _walk(value, f"{path}/{key}")
            elif key == "oneOf":
                for i, sub in enumerate(value):
                    yield from _walk(sub, f"{path}/oneOf/{i}")


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_schemas_use_only_known_keywords(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    for where, sub in _walk(schema):
        unknown = set(sub) - KEYWORDS - ANNOTATIONS
        assert not unknown, f"{path.name}{where} uses {unknown}, which bundle/validator.py doesn't check"


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_every_object_says_whether_it_allows_more(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    for where, sub in _walk(schema):
        if sub.get("type") == "object":
            assert "additionalProperties" in sub, f"{path.name}{where} has no additionalProperties"


@pytest.mark.parametrize("path", SCHEMA_FILES, ids=lambda p: p.name)
def test_schema_ids_carry_the_schema_version(path):
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    assert schema["$id"].startswith(f"https://schemas.kkbp-maps.invalid/{SCHEMA_VERSION}/")


def _mutants(value, path=()):
    """Copies of a JSON value, each broken in one place: every field dropped, an unknown field added,
    every value replaced by values of other types, every list emptied."""
    def at(root, p, change):
        out = copy.deepcopy(root)
        target = out
        for key in p[:-1]:
            target = target[key]
        change(target, p[-1])
        return out

    def walk(node, p):
        if p:
            for wrong in WRONG_VALUES:
                yield at(value, p, lambda t, k, w=wrong: t.__setitem__(k, copy.deepcopy(w)))
        if isinstance(node, dict):
            if p:
                yield at(value, p, lambda t, k: t[k].__setitem__("zz_unknown", 1))
            else:
                yield {**copy.deepcopy(value), "zz_unknown": 1}
            for key in node:
                if p:
                    yield at(value, p, lambda t, k, key=key: t[k].pop(key))
                else:
                    yield {k: v for k, v in copy.deepcopy(value).items() if k != key}
                yield from walk(node[key], p + (key,))
        elif isinstance(node, list):
            if p:
                yield at(value, p, lambda t, k: t.__setitem__(k, []))
            seen = set()
            for i, item in enumerate(node):  # one item of each shape: a node with a renderer, one without, ...
                shape = json.dumps(_shape(item), sort_keys=True)
                if shape not in seen:
                    seen.add(shape)
                    yield from walk(item, p + (i,))

    yield from walk(value, path)


def _shape(value):
    """A value's structure without its values: its keys, its constants that tell alternatives apart."""
    if isinstance(value, dict):
        return {k: (v if k in ("type", "kind", "mode", "source") else _shape(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


@pytest.fixture(scope="module")
def default_files(tmp_path_factory):
    root = MapBundleBuilder().build(tmp_path_factory.mktemp("bundle"))
    return {stem: read_json(root, stem) for stem in DATA_FILES}


@pytest.mark.parametrize("stem", DATA_FILES)
def test_validator_agrees_with_jsonschema(default_files, stem):
    name = f"{stem}.schema.json"
    reference = _jsonschema(name)
    valid = default_files[stem]
    assert schemas().problems(name, valid) == []
    assert reference.is_valid(valid)
    count = 0
    for mutant in _mutants(valid):
        ours = schemas().problems(name, mutant)
        theirs = list(reference.iter_errors(mutant))
        assert bool(ours) == bool(theirs), (
            f"{stem}: validator says {ours or 'valid'}, jsonschema says {[e.message for e in theirs] or 'valid'} "
            f"for {json.dumps(mutant)[:400]}")
        count += 1
    assert count > 20


def test_tagged_alternatives_report_the_matching_one():
    """A Map Variant's sky that says it is a cubemap gets the cubemap's problems, not 'matches none'."""
    variant = MapBundleBuilder().variant(["day"], sky={"kind": "cubemap", "source": "dome", "texture": "0" * 32,
                                                      "tint": [1, 1, 1, 1], "exposure": 1, "rotation": 0})
    problems = schemas().problems("variants.schema.json", {"variants": [variant]})
    assert problems == ["variants/0/sky: 'geometry' is missing"]


def test_messages_name_the_place():
    problems = schemas().problems("map.schema.json", {"key": "a b"})
    assert "key: \"a b\" doesn't match ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$" in problems
    assert "(top): 'outdoor' is missing" in problems


def test_true_is_not_one():
    assert schemas().problems("lightmaps.schema.json", {"sets": [{
        "id": "a", "mode": "non_directional", "lightmaps": [{"index": 0, "color": "0" * 32}],
        "assignments": [{"node": 0, "lightmap": 0, "scale_offset": [1, 1, 0, 0], "uv": True}]}]})
