"""The Content Hashes and the float32 number rule."""

import copy

import pytest

from bundle import hashing


@pytest.mark.parametrize("text, ok", [
    ("0.895", True), ("1.0", True), ("1", True), ("1e-05", True), ("-0.0", True), ("0.70710677", True),
    ("0.89499998", False), ("0.8949999809265137", False), ("0.1", True), ("0.10000000149011612", False),
    ("3.5e38", False), ("1e-50", False),
])
def test_shortest32(text, ok):
    assert hashing.is_shortest32(text) is ok


def test_shortest32_rounds_to_float32():
    assert hashing.shortest32(0.8949999809265137) == 0.895
    assert hashing.shortest32(1 / 3) == 0.33333334


def _node(i, parent, mesh=None, translation=(0.0, 0.0, 0.0), rotation=(1.0, 0.0, 0.0, 0.0), sky=False):
    n = {"id": i, "name": f"n{i}", "parent": parent, "translation": list(translation),
         "rotation": list(rotation), "scale": [1.0, 1.0, 1.0]}
    if mesh:
        n["renderer"] = {"mesh": mesh, "draws": [{"submesh": 0, "material": "m" * 32}],
                         "shadows": "on", "receive_shadows": True}
    if sky:
        n["sky"] = True
    return n


def _desk(root_translation, child_order=(0, 1)):
    """A root group at `root_translation` with two parts, listed in `child_order`."""
    parts = [("a" * 32, (0.0, 0.0, 0.75)), ("b" * 32, (0.5, 0.0, 0.0))]
    nodes = [_node(0, None, translation=root_translation)]
    for i, k in enumerate(child_order, start=1):
        nodes.append(_node(i, 0, mesh=parts[k][0], translation=parts[k][1]))
    return nodes


def test_a_shape_ignores_where_it_stands_and_the_order_of_its_parts():
    shape_a, _ = hashing.tree_hashes(_desk((0.0, 0.0, 0.0)))
    shape_b, _ = hashing.tree_hashes(_desk((5.0, 2.0, 0.0), child_order=(1, 0)))
    assert shape_a[0] == shape_b[0]


def test_a_shape_changes_with_a_part_or_its_transform():
    base = hashing.tree_hashes(_desk((0.0, 0.0, 0.0)))[0][0]
    moved = _desk((0.0, 0.0, 0.0))
    moved[1]["translation"][2] = 0.8
    other_material = _desk((0.0, 0.0, 0.0))
    other_material[2]["renderer"]["draws"][0]["material"] = "n" * 32
    assert hashing.tree_hashes(moved)[0][0] != base
    assert hashing.tree_hashes(other_material)[0][0] != base


def test_one_and_one_point_zero_hash_the_same():
    a = _desk((0.0, 0.0, 0.0))
    b = copy.deepcopy(a)
    b[1]["translation"] = [0, 0, 0.75]
    b[1]["scale"] = [1, 1, 1]
    b[1]["rotation"][1] = -0.0
    assert hashing.tree_hashes(a)[0] == hashing.tree_hashes(b)[0]


def test_candidates_leave_out_sky_and_nested_placements():
    nodes = _desk((0.0, 0.0, 0.0)) + [_node(3, 0, mesh="c" * 32), _node(4, 0, mesh="d" * 32, sky=True)]
    assert hashing.candidate_shapes(nodes, roots={0, 3})[0] == hashing.tree_hashes(_desk((0.0, 0.0, 0.0)))[0][0]
    assert hashing.geometry_hash(nodes) != hashing.geometry_hash(_desk((0.0, 0.0, 0.0)))


def test_material_hash_leaves_out_derived_fields_and_texture_order():
    m = {"name": "a", "shader": "Standard", "keywords": [], "render_queue": 2000, "blend_mode": "opaque",
         "double_sided": False, "colors": {"_Color": [1, 1, 1, 1]}, "floats": {}, "vectors": {},
         "textures": [{"raw": "_MainTex", "texture": "t" * 32, "offset": [0, 0], "scale": [1, 1]},
                      {"raw": "_BumpMap", "role": "normal", "texture": "u" * 32, "offset": [0, 0], "scale": [1, 1]}]}
    other = copy.deepcopy(m)
    other.update(name="b", blend_mode="cutout", double_sided=True)
    other["textures"].reverse()
    del other["textures"][0]["role"]
    assert hashing.material_hash(m) == hashing.material_hash(other)
    other["floats"]["_Glossiness"] = 0.5
    assert hashing.material_hash(m) != hashing.material_hash(other)


def test_the_definitions_stay_put():
    """These values pin the hash definitions. If one changes, every Prop's identity changes: that is a
    contract change (ADR 0012), so only update them together with the Schema Version."""
    assert hashing.digest(b"") == "e3b0c44298fc1c149afbf4c8996fb924"
    assert hashing.texture_hash(1, 1, 3, bytes([1, 2, 3])) == hashing.digest(
        b"kkbp-maps texture\0" + bytes([1, 0, 0, 0, 1, 0, 0, 0, 3, 0, 0, 0, 1, 2, 3]))
    shape, placed = hashing.tree_hashes([_node(0, None, mesh="a" * 32)])
    assert shape[0] == hashing.digest(b'{"draws":[[0,"' + b"m" * 32 + b'"]],"mesh":"' + b"a" * 32 + b'","parts":[]}')
    assert placed[0] == hashing.digest(b'{"rotation":[1.0,0.0,0.0,0.0],"scale":[1.0,1.0,1.0],"shape":"'
                                       + shape[0].encode() + b'","translation":[0.0,0.0,0.0]}')
    assert hashing.geometry_hash([_node(0, None, mesh="a" * 32)]) == hashing.digest(
        b'{"roots":["' + placed[0].encode() + b'"]}')


def test_a_shadows_only_renderer_changes_the_shape():
    nodes = [_node(0, None, mesh="a" * 32)]
    shape, _ = hashing.tree_hashes(nodes, lambda n: False)
    hidden = copy.deepcopy(nodes)
    hidden[0]["renderer"]["shadows"] = "shadows_only"
    shape2, _ = hashing.tree_hashes(hidden, lambda n: False)
    assert shape != shape2
    off = copy.deepcopy(nodes)
    off[0]["renderer"]["shadows"] = "off"
    assert hashing.tree_hashes(off, lambda n: False)[0] == shape   # other modes don't touch the shape
