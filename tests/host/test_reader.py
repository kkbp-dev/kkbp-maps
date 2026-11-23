"""The reader on synthetic Map Bundles: it checks first, indexes the sections and reads mesh files."""

import pytest

from bundle import BundleRejected, read
from bundle_builder import MapBundleBuilder, edit_json, read_json

ROOT, ROOM, WALL, VASE, DESK, DESK_TOP, DESK_LEG, DESK2, DESK2_TOP, DESK2_LEG, CLOUDS, CLOUD_PLANE = range(12)


@pytest.fixture
def path(tmp_path):
    return MapBundleBuilder().build(tmp_path)


def test_sections_are_indexed(path):
    b = read(path)
    assert b.game == "KK" and b.key == "map/scene/test"
    assert len(b.nodes) == 12
    assert set(b.meshes) == {m["id"] for m in read_json(path, "meshes")["meshes"]}
    assert all(b.texture_path(t).is_file() for t in b.textures)
    assert b.children[ROOT] == [ROOM, CLOUDS]
    assert b.subtree(DESK) == [DESK, DESK_TOP, DESK_LEG]


def test_reading_the_manifest_path_is_the_same(path):
    assert read(path / "manifest.json").root == path


def test_mesh_buffers_match_the_record(path):
    b = read(path)
    for mid, m in b.meshes.items():
        buffers = b.mesh_buffers(mid)
        assert list(buffers.attributes) == m["attributes"]
        assert len(buffers.attributes["position"]) == 3 * m["vertices"]
        assert [len(s) for s in buffers.submeshes] == m["index_counts"]
        assert max(max(s) for s in buffers.submeshes) < m["vertices"]
    quad = next(mid for mid, m in b.meshes.items() if m["name"] == "quad")
    assert list(b.mesh_buffers(quad).attributes["position"][3:6]) == [1.0, 0.0, 0.0]


def test_hidden_covers_the_subtree(path):
    b = read(path)
    edit_json(path, "variants", lambda d: d["variants"][-1].update(hidden=[DESK]))
    night = read(path).variants[-1]
    assert b.subtree(DESK) == sorted(read(path).hidden_in(night))


def test_a_broken_bundle_is_rejected(path):
    edit_json(path, "scene", lambda d: d["nodes"][WALL].update(name=7))
    with pytest.raises(BundleRejected) as e:
        read(path)
    assert e.value.problems
