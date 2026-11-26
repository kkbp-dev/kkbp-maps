"""The checker on synthetic Map Bundles: the default one passes, and each rule catches its break."""

import json

import pytest

from bundle import check
from bundle_builder import MapBundleBuilder, edit_json, read_json, refresh_manifest, write_json

# Node ids of the default Map (bundle_builder._default_map).
ROOT, ROOM, WALL, VASE, DESK, DESK_TOP, DESK_LEG, DESK2, DESK2_TOP, DESK2_LEG, CLOUDS, CLOUD_PLANE = range(12)


@pytest.fixture
def bundle(tmp_path):
    return MapBundleBuilder().build(tmp_path)


def built(tmp_path, change):
    b = MapBundleBuilder()
    change(b)
    return b.build(tmp_path)


def problems_of(path, deep=False):
    return check(path, deep=deep)


def assert_problem(path, text, deep=False):
    found = problems_of(path, deep)
    assert any(text in p for p in found), f"expected a problem with {text!r}, got {found}"


def texture_id(path, name):
    return next(t["id"] for t in read_json(path, "textures")["textures"] if t["name"] == name)


def mesh_id(path, name):
    return next(m["id"] for m in read_json(path, "meshes")["meshes"] if m["name"] == name)


# --- the valid bundle ------------------------------------------------------------------------

def test_the_default_bundle_is_valid(bundle):
    assert problems_of(bundle, deep=True) == []


def test_the_manifest_file_itself_can_be_given(bundle):
    assert problems_of(bundle / "manifest.json") == []


def test_variants_merge_and_the_merged_one_covers_both(bundle):
    variants = read_json(bundle, "variants")["variants"]
    assert [v["times_of_day"] for v in variants] == [["day"], ["evening", "night"]]


def test_the_desk_is_one_candidate_placed_twice(bundle):
    candidates = read_json(bundle, "assets")["candidates"]
    assert [c["placements"] for c in candidates] == [[WALL], [VASE], [DESK, DESK2]]


# --- files and the Manifest -------------------------------------------------------------------

def test_without_manifest_it_is_unfinished(bundle):
    (bundle / "manifest.json").unlink()
    assert_problem(bundle, "unfinished")


def test_another_schema_version_is_refused(bundle):
    edit_json(bundle, "manifest", lambda m: m.update(schema_version="0.1"))
    assert problems_of(bundle) == ["manifest.json: the bundle is Schema Version 0.1; this checker reads only 0.12 "
                                   "(ADR 0014), so extract the Map again"]


def test_a_missing_data_file(bundle):
    (bundle / "scene.json").unlink()
    assert_problem(bundle, "scene.json is missing")


def test_byte_order_mark(bundle):
    path = bundle / "map.json"
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert_problem(bundle, "map.json starts with a byte order mark")


def test_numbers_must_be_float32_shortest(bundle):
    path = bundle / "scene.json"
    path.write_text(path.read_text(encoding="utf-8").replace("0.75", "0.75000001", 1), encoding="utf-8")
    assert_problem(bundle, "scene.json: 1 numbers aren't float32 values written shortest, such as 0.75000001")


def test_nan_is_not_json(bundle):
    path = bundle / "variants.json"
    path.write_text(path.read_text(encoding="utf-8").replace("1.45", "NaN", 1), encoding="utf-8")
    assert_problem(bundle, "variants.json isn't valid JSON")


def test_schema_problems_are_reported_with_their_file(bundle):
    edit_json(bundle, "materials", lambda d: d["materials"][0].update(shininess=1.0))
    assert_problem(bundle, "materials.json: materials/0: 'shininess' isn't allowed here")


def test_manifest_map_is_the_key(bundle):
    edit_json(bundle, "manifest", lambda m: m.update(map="map/scene/other"))
    assert_problem(bundle, "map map/scene/other isn't map.json's key")


def test_contents_counts(bundle):
    edit_json(bundle, "manifest", lambda m: m["contents"].update(nodes=99))
    assert_problem(bundle, "contents.nodes is 99; the bundle has 12")


def test_contents_bytes(bundle):
    edit_json(bundle, "manifest", lambda m: m["contents"].update(bytes=1))
    assert_problem(bundle, "contents.bytes is 1")


def test_nothing_else_in_the_folder(bundle):
    (bundle / "notes.txt").write_text("hi")
    refresh_manifest(bundle)
    assert problems_of(bundle) == ["manifest.json: notes.txt doesn't belong in the bundle"]


def test_sources_once(bundle):
    edit_json(bundle, "manifest", lambda m: m["sources"].append(dict(m["sources"][0])))
    assert_problem(bundle, "source abdata/map/scene/test.unity3d appears 2 times")


@pytest.mark.parametrize("path", ["/abs/x.unity3d", "../x.unity3d", "a/../x", "C:/x", "a\\b"])
def test_source_paths_are_relative_and_inside(bundle, path):
    edit_json(bundle, "manifest", lambda m: m["sources"][0].update(path=path))
    assert_problem(bundle, "manifest.json: sources/0/path:")


# --- the Map ------------------------------------------------------------------------------------

def test_times_of_day_keep_their_order(bundle):
    edit_json(bundle, "map", lambda m: m.update(times_of_day=["night", "day", "evening"]))
    assert_problem(bundle, "times_of_day ['night', 'day', 'evening'] should name each value once")


def test_four_times_of_day_start_with_morning(tmp_path):
    def four(b):
        b.map["times_of_day"] = ["morning", "day", "evening", "night"]
        b.map["thumbnails"][0]["times_of_day"] = ["morning", "day", "evening", "night"]
        b.variants[0].update(id="morning", times_of_day=["morning", "day"])
    assert problems_of(built(tmp_path, four)) == []


def test_morning_comes_before_day(bundle):
    edit_json(bundle, "map", lambda m: m.update(times_of_day=["day", "morning", "evening", "night"]))
    assert_problem(bundle, "times_of_day ['day', 'morning', 'evening', 'night'] should name each value once")


def test_a_time_of_day_has_one_thumbnail(bundle):
    edit_json(bundle, "map", lambda m: m["thumbnails"].append(dict(m["thumbnails"][0], times_of_day=["day"])))
    assert_problem(bundle, "2 thumbnails are for day")


def test_thumbnails_are_pngs(bundle):
    sky = texture_id(bundle, "mt_koi_sky_hiru00")
    edit_json(bundle, "map", lambda m: m["thumbnails"][0].update(texture=sky))
    assert_problem(bundle, "a exr; it should be a png")


def test_list_entries_once(bundle):
    edit_json(bundle, "map", lambda m: m["list_entries"].append(dict(m["list_entries"][0])))
    assert_problem(bundle, "list entry map 3 appears 2 times")


def test_geometry_hash(bundle):
    edit_json(bundle, "map", lambda m: m.update(geometry_hash="0" * 32))
    assert_problem(bundle, "geometry_hash should be")


def test_geometry_hash_follows_any_transform(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][ROOM].update(translation=[0.0, 0.0, 1.0]))
    assert problems_of(bundle)[0].startswith("map.json: geometry_hash should be")


# --- nodes ------------------------------------------------------------------------------------

def test_node_ids_are_positions(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][3].update(id=7))
    assert_problem(bundle, "node 3 has id 7")


def test_parents_come_first(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][ROOM].update(parent=5))
    assert_problem(bundle, "node 1 has parent 5, which doesn't come before it")


def test_unit_quaternions(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][ROOM].update(rotation=[1.0, 1.0, 0.0, 0.0]))
    assert_problem(bundle, "node 1: rotation [1.0, 1.0, 0.0, 0.0] isn't a unit quaternion")


def test_no_zero_scale(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][ROOM].update(scale=[1.0, 0.0, 1.0]))
    assert_problem(bundle, "node 1: scale [1.0, 0.0, 1.0] has a 0")


def test_renderer_mesh_exists(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][WALL]["renderer"].update(mesh="0" * 32))
    assert_problem(bundle, f"node {WALL}: mesh {'0' * 32} doesn't exist")


def test_draws_name_a_submesh_the_mesh_has(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][WALL]["renderer"]["draws"][0].update(submesh=1))
    assert_problem(bundle, f"node {WALL}: draws submesh 1, but its mesh has 1")


def test_children_of_sky_nodes_are_sky_nodes(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][CLOUD_PLANE].pop("sky"))
    assert_problem(bundle, f"node {CLOUD_PLANE} is a child of sky node {CLOUDS} but not a sky node")


# --- meshes -----------------------------------------------------------------------------------

def test_attributes_start_with_position_and_normal(bundle):
    edit_json(bundle, "meshes", lambda d: d["meshes"][0].update(attributes=["position", "uv0", "normal", "uv1"]))
    assert_problem(bundle, "its attributes should start with position and normal")


def test_mesh_file_size(bundle):
    edit_json(bundle, "meshes", lambda d: d["meshes"][0].update(vertices=5))
    assert_problem(bundle, "is 184 bytes; its record says 224")


def test_index_counts_are_triangles(bundle):
    edit_json(bundle, "meshes", lambda d: d["meshes"][0].update(index_counts=[4]))
    assert_problem(bundle, "submesh 0 has 4 indices, not a multiple of 3")


def test_deep_check_rehashes_meshes(bundle):
    quad = mesh_id(bundle, "quad")
    path = bundle / "meshes" / f"{quad}.bin"
    data = bytearray(path.read_bytes())
    data[0] ^= 1
    path.write_bytes(bytes(data))
    assert problems_of(bundle) == []
    assert_problem(bundle, f"mesh {quad}: its file's hash is", deep=True)


def test_deep_check_reads_indices(bundle):
    quad = mesh_id(bundle, "quad")
    path = bundle / "meshes" / f"{quad}.bin"
    data = bytearray(path.read_bytes())
    data[-4:] = (9).to_bytes(4, "little")
    path.write_bytes(bytes(data))
    assert_problem(bundle, f"mesh {quad}: index 9 is beyond its 4 vertices", deep=True)


# --- textures and materials ------------------------------------------------------------------

def test_texture_file_exists(bundle):
    lut = texture_id(bundle, "Lut_Amount")
    (bundle / "textures" / f"{lut}.png").unlink()
    refresh_manifest(bundle)
    assert_problem(bundle, f"texture {lut}: textures/{lut}.png is missing")


def test_texture_size_matches_its_file(bundle):
    edit_json(bundle, "textures", lambda d: d["textures"][0].update(width=8))
    assert_problem(bundle, "is 4 × 4; its record says 8 × 4")


def test_exr_is_linear(bundle):
    sky = texture_id(bundle, "mt_koi_sky_hiru00")
    edit_json(bundle, "textures", lambda d: next(t for t in d["textures"] if t["id"] == sky).update(color_space="srgb"))
    assert_problem(bundle, f"texture {sky}: an EXR is linear, not srgb")


def test_exr_is_half_float(bundle):
    sky = texture_id(bundle, "mt_koi_sky_hiru00")
    path = bundle / "textures" / f"{sky}.exr"
    path.write_bytes(path.read_bytes().replace(b"R\0\x01\0\0\0", b"R\0\x02\0\0\0", 1))
    assert_problem(bundle, "has channel R of pixel type 2, not half float")


def test_png_header_is_checked(bundle):
    lut = texture_id(bundle, "Lut_Amount")
    path = bundle / "textures" / f"{lut}.png"
    path.write_bytes(b"not a png at all, padded to be long enough")
    refresh_manifest(bundle)
    assert_problem(bundle, f"textures/{lut}.png isn't a PNG file")


def test_material_id_is_its_content_hash(bundle):
    edit_json(bundle, "materials", lambda d: d["materials"][0]["floats"].update(_Glossiness=0.25))
    assert_problem(bundle, "its Content Hash is")


def test_keywords_sorted(tmp_path):
    path = built(tmp_path, lambda b: b.materials["wall"].update(keywords=["_NORMALMAP", "_EMISSION"]))
    assert_problem(path, "keywords should be sorted, each once")


def test_raw_property_once(tmp_path):
    def change(b):
        b.materials["desk"]["textures"].append(dict(b.materials["desk"]["textures"][0]))
    assert_problem(built(tmp_path, change), "Raw Property _MainTex appears 2 times")


def test_texture_role_once(tmp_path):
    def change(b):
        b.materials["desk"]["textures"].append(dict(b.materials["desk"]["textures"][0], raw="_BaseMap"))
    assert_problem(built(tmp_path, change), "Texture Role main appears 2 times")


def test_material_textures_exist(tmp_path):
    def change(b):
        b.materials["desk"]["textures"][0]["texture"] = "0" * 32
    assert_problem(built(tmp_path, change), f"_MainTex names texture {'0' * 32}, which doesn't exist")


# --- use -------------------------------------------------------------------------------------

def test_every_texture_is_used(tmp_path):
    path = built(tmp_path, lambda b: b.add_texture("spare", 2, 2, 3))
    assert_problem(path, "isn't used by anything")


def test_every_mesh_and_material_is_used(tmp_path):
    def change(b):
        b.add_mesh("spare", b.meshes["quad"]["attributes"] | {"uv1": [[0.5, 0.5]] * 4}, [[0, 1, 2]])
        b.add_material("spare", {"_MainTex": ("desk_main", "main")}, keywords=["_SPARE"])
    found = problems_of(built(tmp_path, change))
    assert any("isn't used by any renderer" in p and p.startswith("meshes.json") for p in found)
    assert any("isn't used by any renderer" in p and p.startswith("materials.json") for p in found)


def test_every_lightmap_set_is_used(bundle):
    edit_json(bundle, "variants", lambda d: [v.update(lightmap_set=None) for v in d["variants"]])
    assert_problem(bundle, "Lightmap Set scene isn't used by any Map Variant")


# --- Lightmap Sets ----------------------------------------------------------------------------

def test_lightmap_color_is_exr(bundle):
    direction = texture_id(bundle, "Lightmap-0_comp_dir")
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["lightmaps"][0].update(color=direction))
    assert_problem(bundle, "lightmap 0: color names texture")


def test_lightmap_direction_matches_its_colour(tmp_path):
    path = built(tmp_path, lambda b: b.textures["lightmap_0_dir"].update(width=8))
    assert_problem(path, "of 8 × 4; it should be 4 × 4")


def test_directional_sets_have_direction_maps(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["lightmaps"][0].pop("direction"))
    assert_problem(bundle, "lightmaps.json: sets/0/lightmaps/0: 'direction' is missing")


def test_assignment_needs_a_renderer(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["assignments"][0].update(node=ROOM))
    assert_problem(bundle, f"Lightmap Set scene: node {ROOM} has no renderer or is a sky node")


def test_assignment_once_per_set(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["assignments"].append(d["sets"][0]["assignments"][0]))
    assert_problem(bundle, f"assignment for node {WALL} appears 2 times")


def test_assignment_lightmap_exists(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["assignments"][0].update(lightmap=3))
    assert_problem(bundle, "uses lightmap 3, which the set doesn't have")


def test_assignment_uv_set_exists(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["assignments"][1].update(uv=1))
    assert_problem(bundle, f"node {DESK_TOP} uses uv1, which its mesh doesn't have")


def test_assignment_node_exists(bundle):
    edit_json(bundle, "lightmaps", lambda d: d["sets"][0]["assignments"][0].update(node=40))
    assert_problem(bundle, "names node 40, which doesn't exist")


# --- Map Variants -----------------------------------------------------------------------------

def test_each_time_of_day_in_one_variant(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(times_of_day=["evening"]))
    assert_problem(bundle, "night is covered by 0 Map Variants")


def test_no_time_of_day_twice(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(times_of_day=["day", "evening", "night"], id="day"))
    assert_problem(bundle, "day is covered by 2 Map Variants")


def test_a_grade_can_blend_a_second_lut(bundle):
    lut_day = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][1]["grade"].update(blend={"lut": lut_day, "amount": 0.5}))
    assert problems_of(bundle) == []


def test_a_grade_blend_lut_is_a_lut(bundle):
    sky = texture_id(bundle, "mt_koi_sky_hiru00")
    edit_json(bundle, "variants", lambda d: d["variants"][1]["grade"].update(blend={"lut": sky, "amount": 0.5}))
    assert_problem(bundle, "Grade blend LUT names texture")


def test_a_grade_blend_of_nothing_is_left_out(bundle):
    lut_day = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][1]["grade"].update(blend={"lut": lut_day, "amount": 0.0}))
    assert_problem(bundle, "a Grade blend of amount 0 should be left out")


def test_variant_id_is_its_first_time_of_day(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(id="night"))
    assert_problem(bundle, "its id should be its first Time of Day, evening")


def test_equal_variants_must_be_merged(bundle):
    def split(d):
        evening = d["variants"][1]
        d["variants"][1:] = [dict(evening, id="evening", times_of_day=["evening"]),
                             dict(evening, id="night", times_of_day=["night"])]
    edit_json(bundle, "variants", split)
    assert_problem(bundle, "Map Variant evening lights the Map the same as another; they should be one")


def test_variants_equal_in_any_number_spelling_are_equal(bundle):
    def split(d):
        evening = d["variants"][1]
        night = json.loads(json.dumps(evening))
        night.update(id="night", times_of_day=["night"])
        night["ambient"]["intensity"] = 1  # 1, not 1.0
        d["variants"][1:] = [dict(evening, id="evening", times_of_day=["evening"]), night]
    edit_json(bundle, "variants", split)
    assert_problem(bundle, "Map Variant night lights the Map the same as another")


def test_hidden_sorted(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(hidden=[CLOUDS, ROOM]))
    assert_problem(bundle, "hidden should be sorted, each node once")


def test_variant_lightmap_set_exists(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(lightmap_set="other"))
    assert_problem(bundle, "Lightmap Set other doesn't exist")


def test_sky_geometry_is_sky(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["sky"].update(geometry=[CLOUDS, ROOM]))
    assert_problem(bundle, f"sky geometry node {ROOM} isn't a sky node")


def test_a_variant_shows_its_sky_geometry(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0].update(hidden=[CLOUDS]))
    assert_problem(bundle, f"Map Variant day: hides its own sky geometry node {CLOUDS}")


def test_every_sky_node_belongs_to_a_sky(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["sky"].update(geometry=[]))
    assert_problem(bundle, f"sky node {CLOUD_PLANE} isn't in any Map Variant's sky geometry")


def test_sky_cubemap_is_exr(bundle):
    lut = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][0]["sky"].update(texture=lut))
    assert_problem(bundle, "Map Variant day: sky names texture")


def test_grade_lut_size(bundle):
    thumb = texture_id(bundle, "thumbnail")
    edit_json(bundle, "variants", lambda d: d["variants"][0]["grade"].update(lut=thumb))
    assert_problem(bundle, "of 8 × 4; it should be 1024 × 32")


def test_reflection_needs_its_texture_field(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["reflection"].pop("texture"))
    assert_problem(bundle, "variants/0/reflection: 'texture' is missing")


def test_a_custom_reflection_may_have_an_empty_slot(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["reflection"].update(source="custom"))
    assert problems_of(bundle) == []


def test_a_reflection_texture_is_an_exr(bundle):
    lut = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][0]["reflection"].update(texture=lut))
    assert_problem(bundle, "Map Variant day: reflection names texture")


def test_a_baked_skybox_reflection_is_carried(tmp_path):
    def change(b):
        b.add_texture("skybox_reflection", 8, 4, 3, fmt="exr", color_space="linear")
        b.variants[1]["reflection"]["texture"] = "skybox_reflection"
    assert problems_of(built(tmp_path, change), deep=True) == []


def test_lights_by_type(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["lights"][0].update(type="spot"))
    assert_problem(bundle, "variants/0/lights/0: 'position' is missing")


def test_variants_may_have_realtime_lights_probes_and_a_procedural_sky(tmp_path):
    def change(b):
        b.add_texture("probe", 8, 4, 3, fmt="exr", color_space="linear")
        v = b.variants[1]
        v["lights"].append({"type": "point", "position": [1.0, 2.0, 3.0], "color": [1.0, 0.8, 0.5, 1.0],
                            "intensity": 2.0, "range": 10.0, "shadows": "none", "mode": "mixed",
                            "culling_mask": 2048, "render_mode": "not_important"})
        v["reflection"]["probes"].append({"texture": "probe", "position": [0.0, 0.0, 1.0],
                                          "box_size": [10.0, 20.0, 5.0], "box_projection": True, "intensity": 1.0})
        v["sky"] = {"kind": "procedural", "source": "skybox", "colors": {"_SkyTint": [0.5, 0.5, 0.5, 1.0]},
                    "floats": {"_SunSize": 0.04, "_Exposure": 1.3}, "geometry": []}
        v["ambient"] = {"mode": "skybox_sh", "intensity": 1.0, "sh": [0.1] * 27}
    assert problems_of(built(tmp_path, change), deep=True) == []


def test_a_variant_may_set_the_camera_fog_and_sun_shafts(bundle):
    def change(d):
        d["variants"][0]["fog"]["camera"] = {"distance": False, "height": True, "top": 2.0, "start_distance": 0.0}
        d["variants"][0]["sun_shafts"].update(threshold=[0.0, 0.0, 0.0, 0.0], max_radius=0.3, blur_radius=3.0,
                                              blur_iterations=2, intensity=1.0)
    edit_json(bundle, "variants", change)
    assert problems_of(bundle) == []


def test_camera_fog_names_all_its_switches(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["fog"].update(camera={"height": True, "top": 2.0}))
    assert_problem(bundle, "fog/camera")


def test_a_light_mask_covers_unity_layers_only(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][0]["lights"][0].update(culling_mask=2 ** 32))
    assert_problem(bundle, "culling_mask")


def test_a_renderer_layer_is_a_unity_layer(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][WALL]["renderer"].update(layer=32))
    assert_problem(bundle, "layer")


TREE_WIND = {"kind": "speedtree", "floats": {"m_fStrengthResponse": 10.0, "Oscillation0_1": 0.174},
             "flags": ["BRANCH_DIRECTIONAL_FROND_1", "GLOBAL_WIND"]}


def tree(b):
    """A SpeedTree-like mesh with every attribute, on a node with a wind and a wind zone."""
    quad = b.meshes["quad"]["attributes"]
    n = len(quad["position"])
    b.add_mesh("tree", {"position": quad["position"], "normal": quad["normal"], "color0": [[1.0, 1.0, 1.0, 0.5]] * n,
                        "uv0": quad["uv0"], "uv0_zw": [[0.1, 0.2]] * n, "uv1": [[0.5, 0.5]] * n,
                        "uv1_zw": [[0.0, 1.0]] * n, "uv2": [[0.0, 0.1, 0.2, 0.3]] * n, "uv3": [[1.0, 0.0, 0.0, 0.0]] * n},
               [[0, 1, 2]])
    node = b.add_node("toon_tree00_00_LOD0", b.nodes[ROOM]["id"], mesh="tree", draws=[(0, "desk")])
    b.nodes[node]["renderer"]["wind"] = 0
    b.nodes[ROOM]["wind_zone"] = {"mode": "directional", "radius": 20.0, "main": 1.0, "turbulence": 1.0,
                                  "pulse_magnitude": 0.5, "pulse_frequency": 0.01}
    b.winds.append(dict(TREE_WIND))
    b.candidates.append({"kind": "structure", "rule": "unprefixed", "placements": [node]})


def test_speedtree_attributes_wind_and_wind_zones(tmp_path):
    assert problems_of(built(tmp_path, tree), deep=True) == []


def test_a_zw_half_needs_its_uv_set(tmp_path):
    path = built(tmp_path, tree)
    def drop_uv1(d):
        m = next(m for m in d["meshes"] if "uv1_zw" in m["attributes"])
        m["attributes"].remove("uv1")
    edit_json(path, "meshes", drop_uv1)
    assert_problem(path, "has uv1_zw but not uv1")


def test_a_renderer_names_a_wind_that_exists(tmp_path):
    path = built(tmp_path, tree)
    edit_json(path, "scene", lambda d: next(n for n in d["nodes"] if n["name"] == "toon_tree00_00_LOD0")["renderer"].update(wind=3))
    assert_problem(path, "wind 3 doesn't exist")


def test_every_wind_is_used(tmp_path):
    path = built(tmp_path, tree)
    edit_json(path, "scene", lambda d: d["winds"].append(dict(TREE_WIND, flags=[])))
    assert_problem(path, "wind 1 isn't used by any renderer")


def skystudio(texture):
    return {"kind": "material", "source": "skystudio", "shader": "Funly/Sky Studio/Skybox/3D Standard",
            "keywords": ["GRADIENT_BACKGROUND", "NOISE_CLOUDS"],
            "colors": {"_GradientSkyUpperColor": [0.33, 0.557, 1.0, 1.0]}, "floats": {"_CloudDensity": 0.25},
            "vectors": {}, "textures": [{"raw": "_CloudNoiseTexture", "texture": texture, "offset": [0.0, 0.0],
                                         "scale": [1.0, 1.0]}], "geometry": []}


def test_a_sky_may_be_a_skybox_material(bundle):
    noise = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(sky=skystudio(noise)))
    assert problems_of(bundle) == []


def test_a_material_sky_names_textures_that_exist(bundle):
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(sky=skystudio("0" * 32)))
    assert_problem(bundle, "sky _CloudNoiseTexture names texture")


def test_a_material_sky_keywords_are_sorted(bundle):
    noise = texture_id(bundle, "Lut_Amount")
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(sky=dict(skystudio(noise), keywords=["Z", "A"])))
    assert_problem(bundle, "sky keywords should be sorted")


def test_a_mesh_may_be_marked_batched(bundle):
    edit_json(bundle, "meshes", lambda d: d["meshes"][0].update(batched=True))
    assert problems_of(bundle) == []


def test_a_batched_mesh_matching_another_is_a_problem(tmp_path):
    def copy_quad(b):
        q = b.meshes["quad"]["attributes"]
        nudged = [[x + 5e-6, y, z] for x, y, z in q["position"]]
        b.add_mesh("quad_batched", dict(q, position=nudged), b.meshes["quad"]["submeshes"])
        b.add_node("mo_wall_01", b.nodes[ROOM]["id"], mesh="quad_batched", draws=[(0, "wall")])
        b.candidates.append({"kind": "structure", "rule": "mo_prefix", "placements": [len(b.nodes) - 1]})
    path = built(tmp_path, copy_quad)
    assert problems_of(path, deep=True) == []          # nothing is batched yet: exact identity only
    edit_json(path, "meshes", lambda d: next(m for m in d["meshes"] if m["name"] == "quad_batched").update(batched=True))
    assert_problem(path, "match (ADR 0034)", deep=True)


def test_batched_is_only_ever_true(bundle):
    edit_json(bundle, "meshes", lambda d: d["meshes"][0].update(batched=False))
    assert_problem(bundle, "batched")


# --- Candidates and Placements ----------------------------------------------------------------

def test_candidate_hash_is_its_shape(bundle):
    edit_json(bundle, "assets", lambda d: d["candidates"][2].update(hash="0" * 32))
    assert_problem(bundle, f"the Placement at node {DESK} has shape")


def test_a_moved_part_breaks_the_shared_shape(bundle):
    edit_json(bundle, "scene", lambda d: d["nodes"][DESK2_LEG].update(translation=[0.0, 0.0, 0.1]))
    assert_problem(bundle, f"the Placement at node {DESK2} has shape")


def test_moving_a_placement_keeps_its_shape(bundle):
    def move(d):
        d["nodes"][DESK2]["translation"] = [7.0, 7.0, 0.0]
    edit_json(bundle, "scene", move)
    found = problems_of(bundle)
    assert len(found) == 1 and found[0].startswith("map.json: geometry_hash should be")


def test_kind_follows_rule(bundle):
    edit_json(bundle, "assets", lambda d: d["candidates"][0].update(kind="prop"))
    assert_problem(bundle, "rule mo_prefix makes a structure, not a prop")


def test_a_node_roots_one_placement(bundle):
    edit_json(bundle, "assets", lambda d: d["candidates"][1]["placements"].append(DESK))
    assert_problem(bundle, f"node {DESK} roots more than one Placement")


def test_nothing_nests_inside_a_prop(bundle):
    def nest(d):
        d["candidates"].append({"hash": "0" * 32, "kind": "prop", "rule": "p_prefix", "placements": [DESK_TOP]})
    edit_json(bundle, "assets", nest)
    assert_problem(bundle, f"the prop Placement at node {DESK_TOP} lies inside the prop Placement at node {DESK}")


def test_structures_dont_nest(bundle):
    def nest(d):
        d["candidates"].append({"hash": "0" * 32, "kind": "structure", "rule": "mo_prefix", "placements": [ROOM]})
    edit_json(bundle, "assets", nest)
    assert_problem(bundle, f"the structure Placement at node {WALL} lies inside the structure Placement at node {ROOM}")


def test_every_renderer_belongs_to_a_placement(bundle):
    edit_json(bundle, "assets", lambda d: d["candidates"].pop(2))
    assert_problem(bundle, f"node {DESK_TOP} has a renderer but belongs to no Placement")


def test_a_prop_without_its_placement_becomes_part_of_its_structure(bundle):
    """Without the vase's Placement, the vase is a part of the wall, so the wall's shape changes."""
    edit_json(bundle, "assets", lambda d: d["candidates"].pop(1))
    assert problems_of(bundle) == [p for p in problems_of(bundle) if f"the Placement at node {WALL} has shape" in p]
    assert problems_of(bundle)


def test_sky_nodes_are_not_placements(bundle):
    def add(d):
        d["candidates"].append({"hash": "0" * 32, "kind": "structure", "rule": "mo_prefix", "placements": [CLOUDS]})
    edit_json(bundle, "assets", add)
    assert_problem(bundle, f"Placement root {CLOUDS} is a sky node")


def test_a_problem_report_is_complete(bundle):
    """Several problems in several files are all reported at once."""
    edit_json(bundle, "map", lambda m: m.update(geometry_hash="0" * 32))
    edit_json(bundle, "assets", lambda d: d["candidates"][2].update(kind="structure"))
    edit_json(bundle, "variants", lambda d: d["variants"][1].update(hidden=[CLOUDS, ROOM]))
    assert len(problems_of(bundle)) == 3


def test_check_bundle_tool(bundle, capsys):
    import importlib.util
    from conftest import REPO
    spec = importlib.util.spec_from_file_location("check_bundle", REPO / "tools" / "check_bundle.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.main([str(bundle)]) == 0
    edit_json(bundle, "map", lambda m: m.update(geometry_hash="0" * 32))
    assert tool.main([str(bundle)]) == 1
    assert "geometry_hash should be" in capsys.readouterr().out


def test_a_shadows_only_renderer_may_belong_to_no_placement(bundle):
    def hide(d):
        for n in d["nodes"]:
            if n["id"] in (DESK_TOP, DESK_LEG, DESK2_TOP, DESK2_LEG):
                n["renderer"]["shadows"] = "shadows_only"
    edit_json(bundle, "scene", hide)
    edit_json(bundle, "assets", lambda d: d["candidates"].pop(2))
    assert not [p for p in problems_of(bundle) if "belongs to no Placement" in p]


def test_shadow_modes_are_a_closed_set(bundle):
    def odd(d):
        next(n for n in d["nodes"] if "renderer" in n)["renderer"]["shadows"] = "sometimes"
    edit_json(bundle, "scene", odd)
    assert any("sometimes" in p for p in problems_of(bundle))


def test_a_renderer_says_whether_it_takes_real_time_gi(bundle):
    def drop(d):
        del next(n for n in d["nodes"] if "renderer" in n)["renderer"]["realtime_gi"]
    edit_json(bundle, "scene", drop)
    assert any("realtime_gi" in p for p in problems_of(bundle))


def test_a_renderer_says_how_it_takes_reflection_probes(bundle):
    def drop(d):
        del next(n for n in d["nodes"] if "renderer" in n)["renderer"]["reflection_probes"]
    edit_json(bundle, "scene", drop)
    assert any("reflection_probes" in p for p in problems_of(bundle))


def test_reflection_probe_modes_are_a_closed_set(bundle):
    def odd(d):
        next(n for n in d["nodes"] if "renderer" in n)["renderer"]["reflection_probes"] = "sometimes"
    edit_json(bundle, "scene", odd)
    assert any("reflection_probes" in p for p in problems_of(bundle))
