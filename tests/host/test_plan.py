"""The build plan on synthetic Map Bundles: assets once per Library, names, catalogs, tags, tiers and
the Build Report."""

import uuid

import pytest

from bundle_builder import MapBundleBuilder, edit_json, refresh_manifest
from kkbp_maps.bundle import read
from kkbp_maps.builder.catalogs import catalog_file, catalog_uuid
from kkbp_maps.builder.names import NameTables
from kkbp_maps.builder.plan import asset_nodes, passes, plan_library, safe_file_name
from kkbp_maps.builder.report import build_report, markdown

ROOT, ROOM, WALL, VASE, DESK, DESK_TOP, DESK_LEG, DESK2, DESK2_TOP, DESK2_LEG, CLOUDS, CLOUD_PLANE = range(12)

TABLES = NameTables({
    "naming": {"strip": ["^p_", "^mo_", "^o_"]},
    "words": {"desk": "Desk", "wall": "Wall", "vase": "Vase"},
    "categories": [{"category": "Furniture", "words": ["desk"]}],
    "maps": {"map/scene/a": {"name": "Room A", "area": "School"}},
})


def bundle(tmp_path, key="map/scene/a", name="a", change=None):
    b = MapBundleBuilder(key=key)
    if change:
        change(b)
    return read(b.build(tmp_path, name))


def test_one_map(tmp_path):
    p = plan_library([bundle(tmp_path)], TABLES)
    m = p.maps[0]
    assert (m.name, m.area, m.file, m.catalog) == ("Room A", "School", "Maps/Room A.blend", "Maps/School")
    assert [v.name for v in m.variants] == ["Room A, Day", "Room A, Evening, Night"]
    assert all(v.thumbnail for v in m.variants)
    assert {(a.kind, a.name, a.catalog) for a in p.assets.values()} == {
        ("structure", "Wall 00", "Structures/School"), ("prop", "Vase 00", "Props/Other"),
        ("prop", "Desk 00", "Props/Furniture")}
    desk = next(a for a in p.assets.values() if a.name == "Desk 00")
    assert desk.placements == 2 and desk.source == ("map/scene/a", DESK)
    assert p.tags(desk) == ["KK", "Room A", "Indoor", "Furniture"]
    assert p.variant_tags(m, m.variants[1]) == ["KK", "Room A", "Evening", "Night", "Indoor"]
    assert m.roots == {WALL: p.maps[0].bundle.candidates[0]["hash"], VASE: p.maps[0].bundle.candidates[1]["hash"],
                       DESK: desk.hash, DESK2: desk.hash}


def test_a_thumbnail_for_any_time_of_day_is_used(tmp_path):
    def night_only(b):
        b.map["thumbnails"][0]["times_of_day"] = ["night"]
    p = plan_library([bundle(tmp_path, change=night_only)], TABLES)
    assert [v.thumbnail is not None for v in p.maps[0].variants] == [False, True]


def test_assets_are_kept_once_across_maps_and_tagged_with_each(tmp_path):
    a = bundle(tmp_path)
    def other_room(x):   # another Map: the same Props, a room placed elsewhere
        x.map.update(outdoor=True)
        x.nodes[ROOM]["translation"] = [0.0, 0.0, 1.0]
    b = bundle(tmp_path, key="map/scene/b", name="b", change=other_room)
    p = plan_library([a, b], TABLES)
    assert len(p.assets) == 3
    desk = next(x for x in p.assets.values() if x.name == "Desk 00")
    assert desk.maps == ["map/scene/a", "map/scene/b"] and desk.placements == 4
    assert p.tags(desk) == ["KK", "Room A", "テスト教室", "Outdoor", "Indoor", "Furniture"]
    assert p.maps[1].named is False and p.maps[1].area == "Other"


def test_names_are_unique_per_kind(tmp_path):
    def other_desk(b):
        for top in (DESK_TOP, DESK2_TOP):  # another shape, the same game name
            b.nodes[top]["scale"] = [2.0, 1.0, 1.0]
    a = bundle(tmp_path)
    b = bundle(tmp_path, key="map/scene/b", name="b", change=other_desk)
    names = sorted(x.name for x in plan_library([a, b], TABLES).props())
    assert names == ["Desk 00", "Desk 00 (2)", "Vase 00"]


def test_overrides_change_the_kind(tmp_path):
    tables = NameTables({"naming": {"strip": ["^mo_"]}, "overrides": [{"match": "^mo_wall", "kind": "prop",
                                                                        "category": "Walls"}]})
    p = plan_library([bundle(tmp_path)], tables)
    wall = next(a for a in p.assets.values() if a.game_name == "mo_wall_00")
    assert (wall.kind, wall.catalog, wall.overridden) == ("prop", "Props/Walls", True)


def test_skipped_shaders(tmp_path):
    def haze(b):
        b.materials["desk"]["shader"] = "Xffect/heat_distortion"
    p = plan_library([bundle(tmp_path, change=haze)], TABLES)
    m = p.maps[0]
    assert not m.drawn(DESK_TOP) and m.drawn(WALL)
    assert [a.game_name for a in p.left_out_assets.values()] == ["p_vase_00", "p_desk_00"]
    report = build_report(p)
    tiers = report["maps"][0]["shader_tiers"]
    assert tiers == [{"shader": "Xffect/heat_distortion", "level": "skipped", "reason": "heat haze",
                      "materials": 1, "draws": 8}]
    assert "heat haze" in markdown(report)


def test_asset_nodes_leave_out_nested_placements(tmp_path):
    b = bundle(tmp_path)
    assert asset_nodes(b, WALL) == [WALL]
    assert asset_nodes(b, DESK) == [DESK, DESK_TOP, DESK_LEG]


def test_catalogs_are_seeded_by_game(tmp_path):
    p = plan_library([bundle(tmp_path)], TABLES)
    cats = p.catalogs()
    assert set(cats) == {"Maps", "Maps/School", "Props", "Props/Furniture", "Props/Other", "Structures",
                         "Structures/School"}
    assert cats["Props"] == catalog_uuid("KK", "Props") != catalog_uuid("KKS", "Props")
    uuid.UUID(cats["Props"])
    text = catalog_file(cats)
    assert "VERSION 1" in text and f"{cats['Props/Furniture']}:Props/Furniture:Props-Furniture" in text


def test_grades_are_listed_once(tmp_path):
    p = plan_library([bundle(tmp_path), bundle(tmp_path, key="map/scene/b", name="b")], TABLES)
    assert [g[1] for g in p.grades] == ["Lut_Amount", "Lut_TimeNight1"]


def test_one_game_per_library(tmp_path):
    with pytest.raises(ValueError):
        plan_library([bundle(tmp_path), read(MapBundleBuilder(game="KKS").build(tmp_path, "s"))], TABLES)


def test_safe_file_names():
    assert safe_file_name('Staff Toilet (Men)') == "Staff Toilet (Men)"
    assert safe_file_name('a/b:c?') == "a_b_c_"


def test_passes_split_a_submesh_drawn_twice():
    draws = [{"submesh": s, "material": m} for s, m in ((0, "a"), (1, "b"), (1, "c"), (1, "d"))]
    out = passes(draws, ["t"] * 4)
    assert [{k: v[0]["material"] for k, v in p.items()} for p in out] == [{0: "a", 1: "b"}, {1: "c"}, {1: "d"}]


def test_draw_notes_reach_the_report(tmp_path):
    def odd_draws(b):
        b.nodes[WALL]["renderer"]["draws"].append({"submesh": 0, "material": "desk"})  # a second pass
        b.nodes[VASE]["renderer"]["draws"].pop()                                     # submesh 1 not drawn
    m = build_report(plan_library([bundle(tmp_path, change=odd_draws)], TABLES))["maps"][0]
    assert {n["note"][:20]: n["renderers"] for n in m["renderer_notes"]} == {
        "a submesh drawn twic": 1, "submeshes the game d": 1}


def test_a_map_is_shown_through_its_own_camera_profile_unless_one_is_given(tmp_path):
    from kkbp_maps.builder.games import camera_profile

    b = bundle(tmp_path)
    p = plan_library([b], TABLES)
    m = p.maps[0]
    assert p.camera_of(m) == b.map["camera"]
    studio = plan_library([b], TABLES, camera="studio")
    assert studio.camera_of(studio.maps[0]) == "studio"
    profile = camera_profile(b.game, "studio")
    assert not profile.map_fog and not profile.map_sun_shafts and not profile.assumed


def test_studio_grades_every_time_of_day_with_its_own_lut(tmp_path):
    b = bundle(tmp_path)
    own = plan_library([b], TABLES)
    studio = plan_library([b], TABLES, camera="studio")
    m, ms = own.maps[0], studio.maps[0]
    names = [b.textures[own.grade_of(m, v)[1]["lut"]]["name"] for v in b.variants]
    assert names == ["Lut_Amount", "Lut_TimeNight1"]
    names = [b.textures[studio.grade_of(ms, v)[1]["lut"]]["name"] for v in b.variants]
    assert names == ["Lut_Amount", "Lut_Amount"]


def test_the_story_camera_adds_its_height_fog_where_the_maps_fog_is_drawn(tmp_path):
    b = bundle(tmp_path, change=lambda b: b.variants[1]["fog"].update(enabled=False))
    game = plan_library([b], TABLES, camera="game")
    studio = plan_library([b], TABLES, camera="studio")
    fogged, clear = (game.as_shown(game.maps[0], v) for v in b.variants)
    assert fogged["fog"] == b.variants[0]["fog"] and fogged["height_fog"] == {"top": 1.0, "density": 2.0}
    assert clear["height_fog"] is None
    in_studio = studio.as_shown(studio.maps[0], b.variants[0])
    assert not in_studio["fog"]["enabled"] and in_studio["height_fog"] is None
    assert b.variants[0]["fog"]["enabled"]   # the bundle's own record is left alone


def test_the_report_lists_the_maps_a_build_left_out(tmp_path):
    p = plan_library([bundle(tmp_path)], TABLES)
    report = build_report(p, not_built={"map/scene/2f": "stopped: it passed 3.0 GB"})
    assert report["not_built"] == [{"key": "map/scene/2f", "reason": "stopped: it passed 3.0 GB"}]
    text = markdown(report)
    assert "and 1 Maps not built" in text and "## Not built" in text and "it passed 3.0 GB" in text
    assert build_report(p)["not_built"] == [] and "Not built" not in markdown(build_report(p))


# --- KKS: trilight ambient and the Map's own camera fog ----------------------------------------------

def test_a_uniform_trilight_is_its_colour_everywhere():
    from kkbp_maps.builder.plan import trilight_sh
    grey = [0.5, 0.5, 0.5, 1.0]
    sh = trilight_sh({"mode": "trilight", "intensity": 1.0, "sky_color": grey, "equator_color": grey, "ground_color": grey})
    lin = ((0.5 + 0.055) / 1.055) ** 2.4
    for c in range(3):
        k = sh[9 * c:9 * c + 9]
        assert abs(k[0] - lin) < 1e-3 and abs(k[2]) < 1e-4 and abs(k[6]) < 1e-4


def test_a_trilight_is_brighter_facing_its_sky():
    from kkbp_maps.builder.plan import trilight_sh
    sh = trilight_sh({"mode": "trilight", "intensity": 1.0, "sky_color": [1.0, 1.0, 1.0, 1.0],
                      "equator_color": [0.5, 0.5, 0.5, 1.0], "ground_color": [0.0, 0.0, 0.0, 1.0]})
    up = sh[0] + sh[2] + 2 * sh[6]
    down = sh[0] - sh[2] + 2 * sh[6]
    assert up > sh[0] > down > 0


def test_a_map_with_another_maps_geometry_is_that_map(tmp_path):
    """D22: a Studio Map whose geometry hash is its story Map's is one Map."""
    a = bundle(tmp_path)
    b = bundle(tmp_path, key="studio/map/a_studio", name="s", change=lambda x: x.map.update(outdoor=True))
    p = plan_library([a, b], TABLES)
    assert [m.key for m in p.maps] == ["map/scene/a"] and p.maps[0].twins == ["studio/map/a_studio"]


def test_batched_copies_in_another_map_are_the_same_prop(tmp_path):
    """ADR 0034: a Map's batched vase matches another Map's unbatched one within the tolerance."""
    def nudged(x):
        x.nodes[ROOM]["translation"] = [0.0, 0.0, 1.0]
        q = x.meshes["slab"]["attributes"]
        x.meshes["slab"]["attributes"] = dict(q, position=[[px + 3e-6, py, pz] for px, py, pz in q["position"]])
    a = bundle(tmp_path)
    b = bundle(tmp_path, key="map/scene/b", name="b", change=nudged)
    edit_json(b.root, "meshes", lambda d: next(m for m in d["meshes"] if m["name"] == "desk_top").update(batched=True))
    refresh_manifest(b.root)
    b = read(b.root)
    p = plan_library([a, b], TABLES)
    vase = next(x for x in p.assets.values() if x.name == "Vase 00")
    assert vase.maps == ["map/scene/a", "map/scene/b"] and vase.source[0] == "map/scene/a"
