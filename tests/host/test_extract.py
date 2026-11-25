"""The Extractor end to end on a synthetic Scene Bundle: the bundle passes the deep check, and each
thing the game resolves at run time comes out as the game shows it."""

import json

import numpy as np
import pytest

from bundle import check
from fake_scene import FakeScene, builtin, ptr, solid
from kkbp_maps.extractor.extract import Options, extract_map, is_fresh, source_files
from kkbp_maps.extractor.games import Install, KK
from kkbp_maps.extractor.maplist import ListEntry, MapSource
from kkbp_maps.extractor.scene import Unsupported
from kkbp_maps.extractor.unity import DXT5, RGB24

SPHERE = 10207  # Unity's built-in Sphere


def lut(grey):
    return solid(32, 1024, [grey, grey, grey])


def sun_info(type_, shows, *, color=(1.0, 0.9, 0.8, 1.0), angle=(30.0, 40.0, 0.0), lut_ref, shafts):
    return {"type": type_, "backTexture": ptr(0), "visibleList": [ptr(g) for g in shows],
            "angle": dict(zip("xyz", angle)), "color": dict(zip("rgba", color)), "intensity": 1.2,
            "fogUse": 1, "fogColor": {"r": 0.3, "g": 0.4, "b": 0.5, "a": 1.0}, "fogStart": 0.0, "fogEnd": 500.0,
            "sunShaftsColor": {"r": 1.0, "g": 0.5, "b": 0.0, "a": 1.0}, "sunShaftsTransform": ptr(shafts),
            "aceLutTexture": ptr(lut_ref), "aceLutBlendTexture": ptr(0), "aceBlendAmount": 0.0}


def build_scene(*, same_light=False):
    """A small KK-like Map: props, a lightmapped wall, Helpers of every kind, a Sky Dome with clouds per
    Time of Day and a sun. With `same_light`, as in park, the three Times of Day are the same and show
    one dome that no info toggles."""
    s = FakeScene()
    wood = s.texture("wood", solid(4, 4, [200, 150, 100, 255]))
    bump = s.texture("bump_n", solid(4, 4, [128, 128, 128, 128]), fmt=DXT5, color_space=0)
    mat_wood = s.material("wood", textures={"_MainTex": wood, "_BumpMap": bump})
    mat_glass = s.material("glass", floats={"_Mode": 3.0, "_SrcBlend": 1.0, "_DstBlend": 10.0}, queue=3000)
    mat_plain = s.material("plain")

    root = s.object("Map")
    room = s.object("n_room", root)
    desk_mesh = s.mesh("desk")
    desks = [s.object(f"p_desk00{' (1)' if i else ''}", room, position=(2.0 * i, 0.0, 0.0)) for i in range(2)]
    for d in desks:
        s.mesh_renderer(d, desk_mesh, [mat_wood, mat_glass])  # two slots on one submesh: a second pass
    wall = s.object("mo_wall00", room, position=(0.0, 0.0, 5.0))
    wall_r = s.mesh_renderer(wall, s.mesh("wall", submeshes=2), [mat_plain], lightmap=0, scale_offset=(0.5, 0.5, 0.0, 0.0))
    floor = s.object("o_floor00", room)
    floor_r = s.mesh_renderer(floor, s.mesh("floor", uv1=False), [mat_plain], lightmap=65535, dynamic=0)
    vase = s.object("p_vase00", wall, position=(0.5, 1.0, 0.0))
    s.mesh_renderer(vase, s.mesh("vase", offset=(0.0, 1.0, 0.0)), [mat_wood])
    loose = s.object("hana_01", room)
    s.mesh_renderer(loose, s.mesh("hana"), [mat_plain])

    # Helpers
    s.mesh_renderer(s.object("o_kage00", room), s.mesh("kage"), [mat_plain], cast=3)
    s.mesh_renderer(s.object("o_off00", room), s.mesh("off"), [mat_plain], enabled=False)
    s.mesh_renderer(s.object("Cube (1)", room), builtin(10202), [mat_plain])
    gone = s.object("o_gone00", room, active=False)
    s.mesh_renderer(gone, s.mesh("gone"), [mat_plain])
    s.component(s.object("Icon", room), "SpriteRenderer", {"m_Enabled": True})
    s.component(s.object("smoke", room), "ParticleSystemRenderer", {"m_Enabled": True})
    s.object("n_empty", room)
    s.mesh_renderer(s.object("nav_map00", room), s.mesh("nav"), [0])  # a renderer with an empty slot only

    # Sky Domes
    cube = s.texture("mt_sky", [solid(4, 4, [10 * f, 100, 200, 255]) for f in range(6)], cube=True)
    sky = s.material("mt_sky", shader="Skybox/Cubemap", props=[("_Tint", 0), ("_Exposure", 3), ("_Rotation", 3), ("_Tex", 4)],
                     textures={"_Tex": cube}, colors={"_Tint": (0.5, 0.5, 0.5, 1.0)}, floats={"_Exposure": 1.0, "_Rotation": 90.0})
    cloud_mat = s.material("cloud", textures={"_MainTex": wood}, queue=3000)
    domes = []
    dome_names = (("mo_koi_sky_hiru00", True),) if same_light else \
        (("mo_koi_sky_hiru00", True), ("mo_koi_sky_yu00", False), ("mo_koi_sky_yo00", True))
    for name, active in dome_names:
        d = s.object(name, root, scale=(500.0, 500.0, 500.0), active=active)
        s.mesh_renderer(d, builtin(SPHERE), [sky], cast=0)
        cloud = s.object("mo_koi_sky_kumo00", d, position=(0.0, 0.0001, 0.0))
        s.mesh_renderer(cloud, s.mesh("cloud" + name), [cloud_mat])
        domes.append(d)

    # Light, lightmaps, settings
    sun = s.object("Directional Light", root)
    sun_light = s.component(sun, "Light", {
        "m_Enabled": 1, "m_Type": 1, "m_Color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}, "m_Intensity": 1.0,
        "m_Range": 10.0, "m_SpotAngle": 30.0, "m_Shadows": {"m_Type": 2}, "m_Lightmapping": 4,
        "m_AreaSize": {"x": 1.0, "y": 1.0}})
    shafts = s.object("sun", sun)
    luts = [s.texture(n, lut(g), fmt=RGB24, color_space=0) for n, g in (("Lut_Amount", 128), ("Lut_TimeNight1", 60))]
    if same_light:
        infos = [sun_info(t, [], lut_ref=luts[1], shafts=0, color=(0.4, 0.5, 0.7, 1.0)) for t in range(3)]
    else:
        infos = [sun_info(0, [domes[0]], lut_ref=luts[0], shafts=s.transform(shafts)),
                 sun_info(1, [domes[1]], lut_ref=luts[0], shafts=s.transform(shafts), color=(1.0, 0.5, 0.2, 1.0)),
                 sun_info(2, [domes[2]], lut_ref=luts[1], shafts=0, color=(0.4, 0.5, 0.7, 1.0), angle=(60.0, 0.0, 0.0))]
    s.behaviour(root, "SunLightInfo", {"_targetLight": ptr(sun_light), "_bgParam": ptr(0), "_infos": infos})
    s.behaviour(root, "LightmapPrefab", {"lightmapParameters": [
        {"lightmapIndex": 0, "scaleOffset": {"x": 0.25, "y": 0.25, "z": 0.5, "w": 0.5}, "renderer": ptr(floor_r)}]})
    lm = s.texture("Lightmap-0_comp_light", solid(4, 4, [255, 128, 64, 51]), lightmap_format=2)
    lm_dir = s.texture("Lightmap-0_comp_dir", solid(4, 4, [128, 255, 128, 200]), color_space=0)
    s.add("LightmapSettings", {"m_Lightmaps": [{"m_Lightmap": ptr(lm), "m_DirLightmap": ptr(lm_dir), "m_ShadowMask": ptr(0)}],
                               "m_LightmapsMode": 1})
    probe = {f"sh[{i:2d}]": 0.01 * i for i in range(27)}
    s.add("RenderSettings", {
        "m_Fog": True, "m_FogColor": {"r": 0.5, "g": 0.5, "b": 0.5, "a": 1.0}, "m_FogMode": 1, "m_FogDensity": 0.01,
        "m_LinearFogStart": 0.0, "m_LinearFogEnd": 300.0, "m_AmbientMode": 3, "m_AmbientIntensity": 1.0,
        "m_AmbientSkyColor": {"r": 0.2, "g": 0.2, "b": 0.25, "a": 1.0}, "m_AmbientProbe": probe,
        "m_SkyboxMaterial": ptr(0), "m_DefaultReflectionMode": 1, "m_ReflectionIntensity": 0.7,
        "m_CustomReflection": ptr(0), "m_GeneratedSkyboxReflection": ptr(0)})
    return s, {"desks": desks, "wall": wall, "floor": floor, "vase": vase, "loose": loose, "domes": domes}


@pytest.fixture
def install(tmp_path):
    root = tmp_path / "Koikatsu"
    (root / "Koikatu_Data").mkdir(parents=True)
    (root / "abdata" / "map" / "scene").mkdir(parents=True)
    (root / "abdata" / "map" / "scene" / "test.unity3d").write_bytes(b"scene bundle")
    return Install(KK, root)


def map_source(install):
    return MapSource(key="map/scene/test", bundle=install.assets / "map" / "scene" / "test.unity3d",
                     entries=[ListEntry("map", 3, "テスト")], outdoor=True)


def extract(install, tmp_path, scene, **kw):
    m = map_source(install)
    return extract_map(install, m, tmp_path / "out", store_factory=lambda path: scene.store(), log=lambda *_: None, **kw)


def load(path, stem):
    return json.loads((path / f"{stem}.json").read_text(encoding="utf-8"))


@pytest.fixture
def bundle(install, tmp_path):
    scene, _ = build_scene()
    return extract(install, tmp_path, scene)


def names(bundle):
    return [n["name"] for n in load(bundle, "scene")["nodes"]]


def node_id(bundle, name):
    return names(bundle).index(name)


def test_the_bundle_passes_the_deep_check(bundle):
    assert check(bundle, deep=True) == []
    assert bundle.name == "test" and bundle.parent.name == "scene"
    assert not (bundle.parent / "test.partial").exists()


def test_helpers_are_left_out(bundle):
    n = names(bundle)
    for helper in ("o_off00", "Cube (1)", "o_gone00", "Icon", "smoke", "n_empty", "nav_map00"):
        assert helper not in n
    assert {"p_desk00", "p_desk00 (1)", "mo_wall00", "o_floor00", "p_vase00", "hana_01"} <= set(n)


def test_a_shadows_only_caster_is_the_map_variants_own(bundle):
    """o_kage00 only casts shadows: it is carried, but no Candidate's Placement holds it (ADR 0024)."""
    nodes = load(bundle, "scene")["nodes"]
    kage = node_id(bundle, "o_kage00")
    assert nodes[kage]["renderer"]["shadows"] == "shadows_only"
    roots = {r for c in load(bundle, "assets")["candidates"] for r in c["placements"]}
    assert kage not in roots


def test_a_renderer_with_real_time_gi_is_marked(bundle):
    rgi = [n["name"] for n in load(bundle, "scene")["nodes"] if n.get("renderer", {}).get("realtime_gi")]
    assert len(rgi) == 1


def test_what_isnt_carried_is_counted(bundle):
    assert load(bundle, "map")["skipped"] == [{"reason": "realtime_gi", "count": 1}, {"reason": "particles", "count": 1}]


def test_sky_domes_are_renderer_less_sky_nodes(bundle):
    nodes = load(bundle, "scene")["nodes"]
    domes = [n for n in nodes if n["name"].startswith("mo_koi_sky_") and "kumo" not in n["name"]]
    assert len(domes) == 3 and all(n.get("sky") and "renderer" not in n for n in domes)
    clouds = [n for n in nodes if "kumo" in n["name"]]
    assert all(n.get("sky") and "renderer" in n for n in clouds)


def test_each_time_of_day_shows_its_own_dome(bundle):
    vs = load(bundle, "variants")["variants"]
    assert [v["times_of_day"] for v in vs] == [["day"], ["evening"], ["night"]]
    day, evening, night = vs
    hiru, yu, yo = (node_id(bundle, n) for n in ("mo_koi_sky_hiru00", "mo_koi_sky_yu00", "mo_koi_sky_yo00"))
    assert day["hidden"] == [yu, yo] and evening["hidden"] == [hiru, yo] and night["hidden"] == [hiru, yu]
    assert [v["sky"]["geometry"] for v in vs] == [[hiru], [yu], [yo]]
    assert day["sun_shafts"] == {"color": [1.0, 0.5, 0.0, 1.0]} and night["sun_shafts"] is None
    assert day["grade"]["lut"] != night["grade"]["lut"]


def test_times_of_day_that_light_the_same_merge(install, tmp_path):
    scene, _ = build_scene(same_light=True)
    out = extract(install, tmp_path, scene)
    vs = load(out, "variants")["variants"]
    assert [(v["id"], v["times_of_day"]) for v in vs] == [("day", ["day", "evening", "night"])]
    assert check(out, deep=True) == []


def test_the_sun_takes_sunlightinfo_s_rotation_and_colour(bundle):
    from kkbp_maps.extractor import space
    night = load(bundle, "variants")["variants"][2]
    sun = night["lights"][0]
    assert sun["color"] == [0.4, 0.5, 0.7, 1.0] and sun["intensity"] == 1.2
    assert np.allclose(sun["rotation"], space.light_rotation(space.euler_quaternion((60.0, 0.0, 0.0))), atol=1e-6)


def test_the_sky_rotation_and_tint(bundle):
    sky = load(bundle, "variants")["variants"][0]["sky"]
    assert sky["kind"] == "cubemap" and sky["source"] == "dome"
    assert sky["rotation"] == -90.0 and sky["tint"] == [0.5, 0.5, 0.5, 1.0]


def test_an_empty_custom_reflection_is_carried_as_null(bundle):
    assert load(bundle, "variants")["variants"][0]["reflection"] == {"source": "custom", "intensity": 0.7,
                                                                     "texture": None, "probes": []}


def test_lightmap_assignment_follows_the_prefab_over_the_renderer(bundle):
    s = load(bundle, "lightmaps")["sets"][0]
    by_node = {a["node"]: a for a in s["assignments"]}
    wall, floor = node_id(bundle, "mo_wall00"), node_id(bundle, "o_floor00")
    assert by_node[wall] == {"node": wall, "lightmap": 0, "scale_offset": [0.5, 0.5, 0.0, 0.0], "uv": 1}
    assert by_node[floor] == {"node": floor, "lightmap": 0, "scale_offset": [0.25, 0.25, 0.5, 0.5], "uv": 0}
    assert set(by_node) == {wall, floor}
    assert s["mode"] == "directional"


def test_the_lightmap_is_decoded_from_rgbm(bundle):
    from kkbp_maps.extractor import images
    s = load(bundle, "lightmaps")["sets"][0]
    textures = {t["id"]: t for t in load(bundle, "textures")["textures"]}
    color = textures[s["lightmaps"][0]["color"]]
    assert color["format"] == "exr" and color["color_space"] == "linear"
    direction = textures[s["lightmaps"][0]["direction"]]
    assert direction["format"] == "png" and direction["color_space"] == "linear"
    expected = images.rgbm_decode(solid(1, 1, [255, 128, 64, 51]), 34.493242, 2.2)
    assert expected[0, 0, 0] == pytest.approx(34.493242 * 0.2 ** 2.2, rel=1e-3)


def test_two_material_slots_on_one_submesh_draw_it_twice(bundle):
    nodes = load(bundle, "scene")["nodes"]
    desk = nodes[node_id(bundle, "p_desk00")]
    assert [d["submesh"] for d in desk["renderer"]["draws"]] == [0, 0]
    wall = nodes[node_id(bundle, "mo_wall00")]
    assert [d["submesh"] for d in wall["renderer"]["draws"]] == [0]  # submesh 1 has no slot


def test_materials_keep_only_their_shaders_properties(bundle):
    mats = {m["name"]: m for m in load(bundle, "materials")["materials"]}
    wood = mats["wood"]
    assert "_Stale" not in wood["colors"] and "_OldShaderValue" not in wood["floats"]
    assert {t["raw"]: t.get("role") for t in wood["textures"]} == {"_MainTex": "main", "_BumpMap": "normal"}
    assert mats["glass"]["blend_mode"] == "alpha" and mats["plain"]["blend_mode"] == "opaque"
    assert mats["cloud"]["blend_mode"] == "alpha" and mats["plain"]["render_queue"] == 2000


def test_normal_maps_are_unpacked(bundle):
    from PIL import Image
    mats = {m["name"]: m for m in load(bundle, "materials")["materials"]}
    bump = next(t["texture"] for t in mats["wood"]["textures"] if t["raw"] == "_BumpMap")
    px = np.asarray(Image.open(bundle / "textures" / f"{bump}.png"))
    assert px.shape[2] == 3 and list(px[0, 0]) == [128, 128, 255]


def test_props_structures_and_loose_renderers(bundle):
    cands = load(bundle, "assets")["candidates"]
    by_rule = {}
    for c in cands:
        by_rule.setdefault(c["rule"], []).append(sorted(names(bundle)[p] for p in c["placements"]))
    assert sorted(by_rule["p_prefix"]) == [["p_desk00", "p_desk00 (1)"], ["p_vase00"]]
    assert by_rule["mo_prefix"] == [["mo_wall00"]] and by_rule["o_prefix"] == [["o_floor00"]]
    assert by_rule["unprefixed"] == [["hana_01"]]


def test_a_bundle_is_fresh_until_a_source_changes(install, tmp_path, bundle):
    m = map_source(install)
    assert is_fresh(bundle, install, source_files(install, m), Options())
    assert not is_fresh(bundle, install, source_files(install, m), Options(max_texture_size=2))
    m.bundle.write_bytes(b"another scene bundle")
    assert not is_fresh(bundle, install, source_files(install, m), Options())


def test_a_fresh_bundle_isnt_extracted_again(install, tmp_path, bundle):
    scene, _ = build_scene()
    before = (bundle / "manifest.json").read_bytes()
    calls = []
    extract_map(install, map_source(install), tmp_path / "out", store_factory=lambda p: calls.append(p) or scene.store(),
                log=lambda *_: None)
    assert calls == [] and (bundle / "manifest.json").read_bytes() == before


def test_the_size_limit_scales_material_textures_only(install, tmp_path):
    scene, _ = build_scene()
    big = scene.texture("big", solid(64, 64, [1, 2, 3, 255]))
    mat = scene.material("big", textures={"_MainTex": big})
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    scene.mesh_renderer(scene.object("p_big00", root), scene.mesh("big"), [mat])
    out = extract(install, tmp_path, scene, options=Options(max_texture_size=16))
    textures = {t["name"]: t for t in load(out, "textures")["textures"]}
    assert textures["big"]["width"] == 16
    assert textures["Lut_Amount"]["width"] == 1024
    assert check(out, deep=True) == []


def test_an_unknown_renderer_stops_the_extraction(install, tmp_path):
    scene, _ = build_scene()
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    scene.component(scene.object("line", root), "LineRenderer", {"m_Enabled": True})
    with pytest.raises(Unsupported, match="LineRenderer"):
        extract(install, tmp_path, scene)
    assert not (tmp_path / "out" / "KK" / "map" / "scene" / "test").exists()


def test_light_probes_stop_the_extraction(install, tmp_path):
    scene, _ = build_scene()
    scene.add("LightProbes", {"m_Data": {"m_Positions": [{"x": 0.0, "y": 1.0, "z": 0.0}]}})
    with pytest.raises(Unsupported, match="light probes"):
        extract(install, tmp_path, scene)


def test_room_containers_are_walked_into(install, tmp_path):
    """ADR 0019: park's whole Map sits under p_koi_map71_park; its pieces are Candidates of their own."""
    scene, _ = build_scene()
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    mat = scene.material("bench")
    room = scene.object("p_koi_map71_park", root)
    shell = scene.object("o_koi_map02_00", room)
    for i in range(2):
        scene.mesh_renderer(scene.object(f"o_kouen_isu_0{i}", shell, position=(float(i), 0.0, 0.0)),
                            scene.mesh("isu", offset=(0.0, 0.0, 1.5)), [mat])
    lamp = scene.object("p_koi_map37_water00", room)  # a container name with a renderer is a Prop
    scene.mesh_renderer(lamp, scene.mesh("water", offset=(0.0, 0.0, 3.0)), [mat])
    out = extract(install, tmp_path, scene)
    n = names(out)
    placed = {n[p]: c["rule"] for c in load(out, "assets")["candidates"] for p in c["placements"]}
    assert placed["o_kouen_isu_00"] == placed["o_kouen_isu_01"] == "o_prefix"
    assert placed["p_koi_map37_water00"] == "p_prefix"
    assert "p_koi_map71_park" not in placed and "o_koi_map02_00" not in placed
    benches = [c for c in load(out, "assets")["candidates"] if n[c["placements"][0]] == "o_kouen_isu_00"]
    assert len(benches[0]["placements"]) == 2
    assert check(out, deep=True) == []


def test_unprefixed_copies_of_a_prop_are_its_placements(install, tmp_path):
    """ADR 0023: KK places plain copies of a p_ Prop (2f's isu00) without the prefix."""
    scene, _ = build_scene()
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    group = scene.object("MapObjectGroup", root)
    mat = scene.material("chair")
    chair = scene.mesh("isu", offset=(0.0, 0.0, 2.5))
    scene.mesh_renderer(scene.object("isu00", group, position=(4.0, 0.0, 0.0)), chair, [mat])
    scene.mesh_renderer(scene.object("p_o_koi_isu00", group, position=(5.0, 0.0, 0.0)), chair, [mat])
    out = extract(install, tmp_path, scene)
    n = names(out)
    chairs = [c for c in load(out, "assets")["candidates"] if "p_o_koi_isu00" in [n[p] for p in c["placements"]]]
    assert len(chairs) == 1
    assert sorted(n[p] for p in chairs[0]["placements"]) == ["isu00", "p_o_koi_isu00"]
    assert (chairs[0]["kind"], chairs[0]["rule"]) == ("prop", "p_prefix")
    assert check(out, deep=True) == []


def test_a_structure_with_a_props_shape_still_stops(install, tmp_path):
    scene, _ = build_scene()
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    mat = scene.material("chair")
    chair = scene.mesh("isu", offset=(0.0, 0.0, 2.5))
    scene.mesh_renderer(scene.object("o_isu00", root, position=(4.0, 0.0, 0.0)), chair, [mat])
    scene.mesh_renderer(scene.object("p_isu00", root, position=(5.0, 0.0, 0.0)), chair, [mat])
    with pytest.raises(ValueError, match="shape of a"):
        extract(install, tmp_path, scene)


def _probe(scene, mode, baked):
    root = next(pid for pid, (t, tr) in scene.objects.items() if t == "GameObject" and tr["m_Name"] == "Map")
    scene.component(scene.object("Reflection Probe", root), "ReflectionProbe", {
        "m_Enabled": 1, "m_Mode": mode, "m_BakedTexture": ptr(baked), "m_CustomBakedTexture": ptr(0),
        "m_BoxOffset": {"x": 0.0, "y": 0.0, "z": 0.0}, "m_BoxSize": {"x": 10.0, "y": 10.0, "z": 10.0},
        "m_BoxProjection": 0, "m_IntensityMultiplier": 1.0})


def test_a_probe_that_was_never_baked_is_left_out(install, tmp_path):
    """ADR 0023: akikyoushitu's Reflection Probe2-99 is baked-mode with no bake."""
    scene, _ = build_scene()
    _probe(scene, 0, 0)
    out = extract(install, tmp_path, scene)
    assert all(v["reflection"]["probes"] == [] for v in load(out, "variants")["variants"])


def test_a_realtime_probe_still_stops(install, tmp_path):
    scene, _ = build_scene()
    _probe(scene, 1, 0)
    with pytest.raises(Unsupported, match="no baked cubemap"):
        extract(install, tmp_path, scene)
