"""The Extractor on a synthetic KKS-like Scene Bundle (kks-spike.md): four Times of Day with the story
game's fallback, SunLightInfo's KKS settings, static batching, levels of detail, room containers under
the root, and a SkyStudio sky."""

import json
import math

import numpy as np
import pytest

from bundle import check
from fake_scene import FakeScene, ptr, solid
from kkbp_maps.extractor.extract import extract_map
from kkbp_maps.extractor.games import KKS, Install
from kkbp_maps.extractor.maplist import ListEntry, MapSource
from kkbp_maps.extractor.unity import RGB24, MeshData

C = {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}


def rgba(*v):
    return dict(zip("rgba", v))


def info(type_, shows, lut, *, blend=0, amount=0.0, sky=(0.5, 0.6, 0.7), height_fog=0, intensity=1.4):
    return {"type": type_, "backTexture": ptr(0), "visibleList": [ptr(g) for g in shows],
            "angle": {"x": 120.0, "y": -48.0, "z": 0.0}, "color": rgba(1.0, 0.98, 0.88, 1.0), "intensity": intensity,
            "ambientSkyColor": rgba(*sky, 0.0), "ambientEquatorColor": rgba(0.75, 0.78, 0.8, 0.0),
            "ambientGroundColor": rgba(0.36, 0.3, 0.05, 0.0),
            "fogUse": 1, "fogColor": rgba(0.09, 0.67, 0.9, 1.0), "fogStart": 5.0, "fogEnd": 200.0, "fogDensity": 0.02,
            "glFogDistanceFog": 0, "glFogHeightFog": height_fog, "glFogHeight": 2.0, "glFogStartDistance": 0.0,
            "sunShaftsTransform": ptr(0), "sunShaftsColor": rgba(0.6, 0.87, 1.0, 1.0), "sunThresholdColor": rgba(0, 0, 0, 0),
            "sunMaxRadius": 0.3, "sunShaftBlurRadius": 3.0, "sunRadialBlurIterations": 2, "sunShaftIntensity": 1.0,
            "aceLutTexture": ptr(lut), "aceLutBlendTexture": ptr(blend), "aceBlendAmount": amount}


def keyframes(value_key, value):
    return {"keyframes": [{"m_Id": "x", "m_Time": 0.0, "m_InterpolationCurve": 0, "m_InterpolationDirection": 0,
                           value_key: value}]}


def profile(name, material, *, upper=(0.33, 0.56, 1.0), sun=True, sun_light=(0.8, 0.5, 0.0, 1.0), sun_intensity=0.4):
    colors = {"SkyUpperColorKey": rgba(*upper, 1.0), "SkyMiddleColorKey": rgba(0.79, 0.93, 0.98, 1.0),
              "SkyLowerColorKey": C, "SunColorKey": rgba(1.0, 1.0, 0.37, 1.0), "SunLightColorKey": rgba(*sun_light)}
    numbers = {"HorizonTransitionStartKey": -0.2, "HorizonTransitionLengthKey": 1.5, "SkyMiddleColorPosition": 0.5,
               "HorizonStarScaleKey": 0.7, "SunSizeKey": 0.1, "SunEdgeFeatheringKey": 0.3, "SunColorIntensityKey": 1.0,
               "SunLightIntensityKey": sun_intensity, "StarTransitionStartKey": 0.0, "StarTransitionLengthKey": 0.5}
    keys = ["GradientSkyFeature", "SunFeature", "MoonFeature", "CloudFeature"]
    return {"m_Name": name, "m_SkyboxMaterial": ptr(material), "m_ShaderName": "Funly/Sky Studio/Skybox/3D Standard",
            "featureStatus": {"m_Keys": keys, "m_Values": [1, 1 if sun else 0, 0, 0]},
            "keyframeGroups": {
                "m_ColorGroup": {"m_Keys": list(colors), "m_Values": [keyframes("color", v) for v in colors.values()]},
                "m_NumberGroup": {"m_Keys": list(numbers), "m_Values": [keyframes("value", v) for v in numbers.values()]},
                "m_TextureGroup": {"m_Keys": [], "m_Values": []},
                "m_SpherePointGroup": {"m_Keys": ["SunPositionKey"], "m_Values": [
                    keyframes("spherePoint", {"horizontalRotation": 0.0, "verticalRotation": math.pi / 4})]},
                "m_BoolGroup": {"m_Keys": [], "m_Values": []}}}


def build_scene():
    s = FakeScene()
    mat = s.material("plain")
    root = s.object("Map")

    # A room container under the root, with Props inside; a renderer-less group deeper isn't one.
    room = s.object("p_ks_r01", root)
    chair_mesh = s.mesh("chair", offset=(0.0, 0.0, 0.5))
    for i in range(2):
        s.mesh_renderer(s.object(f"p_ks_r01_chair00{' (1)' if i else ''}", room, position=(float(i), 0.0, 0.0)),
                        chair_mesh, [mat])
    shelf = s.object("p_ks_r01_shelf00", room, position=(0.0, 3.0, 0.0))
    for i in range(2):
        s.mesh_renderer(s.object(f"shelf_part{i}", shelf, position=(0.0, 0.0, float(i))), s.mesh(f"shelf{i}"), [mat])

    # Static batching: an unbatched pen, and two copies drawn from a world-space Combined Mesh.
    pen = s.mesh("pen", offset=(0.0, 0.0, 0.25))
    s.mesh_renderer(s.object("p_ks_r01_pen00", room, position=(5.0, 0.0, 0.0)), pen, [mat])
    quad = s.meshes[pen]
    at = [(7.0, 0.0, 0.0), (9.0, 1.0, 0.0)]
    positions = np.concatenate([quad.positions + np.array(p, np.float32) for p in at])
    combined = s.add("Mesh", {"m_Name": "Combined Mesh (root: scene)"})
    s.meshes[combined] = MeshData("Combined Mesh (root: scene)", positions, np.concatenate([quad.normals] * 2),
                                  np.concatenate([quad.uv0] * 2), np.concatenate([quad.uv1] * 2),
                                  [quad.submeshes[0], quad.submeshes[0] + 4])
    for i, p in enumerate(at):
        go = s.object(f"p_ks_r01_pen00 ({i + 1})", room, position=p)
        r = s.mesh_renderer(go, combined, [mat])
        s.objects[r][1]["m_StaticBatchInfo"] = {"firstSubMesh": i, "subMeshCount": 1}

    # A SpeedTree-like tree: LOD0 kept, LOD1 and the billboard left out.
    tree = s.object("toon_tree00_00", root, position=(0.0, 10.0, 0.0))
    lod0 = s.mesh_renderer(s.object("toon_tree00_00_LOD0", tree), s.mesh("tree_lod0"), [mat])
    lod1 = s.mesh_renderer(s.object("toon_tree00_00_LOD1", tree), s.mesh("tree_lod1"), [mat])
    board = s.component(s.object("toon_tree00_00_Billboard", tree), "BillboardRenderer", {"m_Enabled": 1})
    s.component(tree, "LODGroup", {"m_Enabled": 1, "m_LODs": [
        {"screenRelativeHeight": 0.25, "renderers": [{"renderer": ptr(lod0)}]},
        {"screenRelativeHeight": 0.1, "renderers": [{"renderer": ptr(lod1)}]},
        {"screenRelativeHeight": 0.01, "renderers": [{"renderer": ptr(board)}]}]})

    # Per-Time-of-Day objects: one listed by two infos, one VisibleChange would hide at load in KK.
    morning = s.object("morning", root)
    s.mesh_renderer(morning, s.mesh("sea_morning"), [mat])
    night = s.object("night_light", root)
    s.mesh_renderer(night, s.mesh("sea_night"), [mat])
    both = s.object("dentyu_OFF", root)
    s.mesh_renderer(both, s.mesh("dentyu"), [mat])
    point = s.object("h_point", root)
    s.mesh_renderer(point, s.mesh("bed"), [mat])
    s.behaviour(root, "VisibleChange", {"_visibleList": [], "_unVisibleList": ["h_point"]})

    # Lights: the sun, a water-only light, and SkyStudio's sun under its orbit.
    def light(go, kind, mask, *, enabled=1, mode=4, render=0, intensity=1.0):
        return s.component(go, "Light", {
            "m_Enabled": enabled, "m_Type": kind, "m_Color": C, "m_Intensity": intensity, "m_Range": 10.0,
            "m_SpotAngle": 30.0, "m_Shadows": {"m_Type": 2}, "m_Lightmapping": mode, "m_RenderMode": render,
            "m_CullingMask": {"m_Bits": mask}, "m_AreaSize": {"x": 1.0, "y": 1.0}})
    sun_light = light(s.object("Directional Light_sun", root), 1, 2048)
    light(s.object("Point Light", root, position=(1.0, 2.0, 3.0)), 2, 2048, mode=1, render=2)
    controller_go = s.object("SkySystemController", root)
    orbit_go = s.object("Sun", controller_go)
    sky_light = light(s.object("Light", orbit_go), 1, 16, enabled=0)
    orbit = s.behaviour(orbit_go, "OrbitingBody", {})

    # The Grade, two LUTs blended at night; the SkyStudio profiles and skybox.
    luts = [s.texture(n, solid(32, 1024, [g, g, g]), fmt=RGB24, color_space=0) for n, g in (("Lut_Amount", 128), ("Lut_TimeNight1", 60))]
    sky_shader_props = [("_GradientSkyUpperColor", 0), ("_GradientSkyMiddleColor", 0), ("_GradientSkyLowerColor", 0),
                        ("_SunColor", 0), ("_GradientFadeBegin", 3), ("_GradientFadeEnd", 3), ("_GradientFadeMiddlePosition", 3),
                        ("_HorizonScaleFactor", 3), ("_SunRadius", 3), ("_SunEdgeFade", 3), ("_SunHDRBoost", 3),
                        ("_StarFadeBegin", 3), ("_StarFadeEnd", 3), ("_SunPosition", 1)]
    sky_mat = s.material("SkyboxMaterial_morning", shader="Funly/Sky Studio/Skybox/3D Standard", props=sky_shader_props,
                         colors={"_GradientSkyUpperColor": (0.0, 0.34, 1.0, 1.0)}, keywords="GRADIENT_BACKGROUND MOON")
    profiles = [s.add("MonoBehaviour", {"m_Script": ptr(s.add("MonoScript", {"m_ClassName": "SkyProfile"})),
                                        **profile(name, sky_mat, upper=upper, sun=sun)})
                for name, upper, sun in (("SkyProfile_morning", (0.33, 0.56, 1.0), True), ("SkyProfile_night", (0.13, 0.15, 0.28), False))]
    s.behaviour(controller_go, "TimeOfDayController", {"m_SkyProfile": ptr(profiles[0]), "m_SkyTime": 0.22,
                                                       "automaticTimeIncrement": 0, "sunOrbit": ptr(orbit), "moonOrbit": ptr(0)})
    s.behaviour(root, "MapSkyInfo", {"_controller": ptr(0), "_infos": [
        {"_profile": ptr(profiles[0]), "_actives": [], "_inactives": []},
        {"_profile": ptr(profiles[0]), "_actives": [], "_inactives": []},
        {"_profile": ptr(profiles[0]), "_actives": [], "_inactives": []},
        {"_profile": ptr(profiles[1]), "_actives": [], "_inactives": []}]})
    # Only Morning and Night: Day and Evening fall back to Morning (ADR 0032).
    infos = [info(0, [morning, both], luts[0], sky=(0.54, 0.64, 0.75)),
             info(3, [night, both], luts[1], blend=luts[0], amount=0.5, sky=(0.18, 0.4, 0.9), height_fog=1, intensity=1.2)]
    s.behaviour(root, "SunLightInfo", {"_targetLight": ptr(sun_light), "_bgParam": ptr(0), "_infos": infos})
    s.add("RenderSettings", {
        "m_Fog": True, "m_FogColor": C, "m_FogMode": 1, "m_FogDensity": 0.0, "m_LinearFogStart": 5.0,
        "m_LinearFogEnd": 200.0, "m_AmbientMode": 1, "m_AmbientIntensity": 1.0, "m_AmbientSkyColor": C,
        "m_AmbientEquatorColor": C, "m_AmbientGroundColor": C,
        "m_AmbientProbe": {f"sh[{i:2d}]": 0.0 for i in range(27)}, "m_SkyboxMaterial": ptr(sky_mat),
        "m_DefaultReflectionMode": 0, "m_ReflectionIntensity": 1.0, "m_CustomReflection": ptr(0),
        "m_GeneratedSkyboxReflection": ptr(0)})
    return s, {"sky_light": sky_light}


@pytest.fixture
def bundle(tmp_path):
    root = tmp_path / "Koikatsu Sunshine"
    (root / "KoikatsuSunshine_Data").mkdir(parents=True)
    (root / "abdata" / "map" / "scene").mkdir(parents=True)
    scene_file = root / "abdata" / "map" / "scene" / "test.unity3d"
    scene_file.write_bytes(b"scene bundle")
    install = Install(KKS, root)
    m = MapSource(key="map/scene/test", bundle=scene_file, entries=[ListEntry("map", 4, "浜辺")], outdoor=True)
    scene, _ = build_scene()
    return extract_map(install, m, tmp_path / "out", store_factory=lambda path: scene.store(), log=lambda *_: None)


def load(path, stem):
    return json.loads((path / f"{stem}.json").read_text(encoding="utf-8"))


def names(bundle):
    return [n["name"] for n in load(bundle, "scene")["nodes"]]


def variant(bundle, tod):
    return next(v for v in load(bundle, "variants")["variants"] if tod in v["times_of_day"])


def test_the_bundle_passes_the_deep_check(bundle):
    assert check(bundle, deep=True) == []


def test_missing_times_of_day_show_the_first_info(bundle):
    assert load(bundle, "map")["times_of_day"] == ["morning", "day", "evening", "night"]
    assert [v["times_of_day"] for v in load(bundle, "variants")["variants"]] == [["morning", "day", "evening"], ["night"]]


def test_set_hides_every_list_then_shows_the_chosen(bundle):
    n = names(bundle)
    for tod in ("morning", "night"):
        assert n.index("dentyu_OFF") not in variant(bundle, tod)["hidden"]   # in both lists: shown at both
    assert n.index("night_light") in variant(bundle, "morning")["hidden"]
    assert n.index("morning") in variant(bundle, "night")["hidden"]


def test_visible_change_isnt_replayed_at_load(bundle):
    n = names(bundle)
    assert all(n.index("h_point") not in v["hidden"] for v in load(bundle, "variants")["variants"])


def test_ambient_fog_shafts_and_grade_follow_each_info(bundle):
    morning, night = variant(bundle, "morning"), variant(bundle, "night")
    assert morning["ambient"]["mode"] == "trilight" and morning["ambient"]["sky_color"][:3] == [0.54, 0.64, 0.75]
    assert night["ambient"]["sky_color"][:3] == [0.18, 0.4, 0.9]
    assert morning["fog"]["density"] == 0.02 and morning["fog"]["camera"]["height"] is False
    assert night["fog"]["camera"] == {"distance": False, "height": True, "top": 2.0, "start_distance": 0.0}
    assert "blend" not in morning["grade"]
    assert night["grade"]["blend"]["amount"] == 0.5


def test_lights_keep_their_masks_and_render_modes(bundle):
    lights = variant(bundle, "morning")["lights"]
    assert sorted((l["type"], l["culling_mask"], l["render_mode"], l["mode"]) for l in lights) == [
        ("directional", 16, "auto", "realtime"), ("directional", 2048, "auto", "realtime"),
        ("point", 2048, "not_important", "mixed")]


def test_skystudio_drives_the_sky_and_its_sun(bundle):
    morning, night = variant(bundle, "morning"), variant(bundle, "night")
    sky = morning["sky"]
    assert (sky["kind"], sky["source"], sky["shader"]) == ("material", "skystudio", "Funly/Sky Studio/Skybox/3D Standard")
    assert sky["colors"]["_GradientSkyUpperColor"] == [0.33, 0.56, 1.0, 1.0]          # the profile's, not the material's
    assert sky["floats"]["_GradientFadeBegin"] == -0.2 and sky["floats"]["_GradientFadeEnd"] == 1.0   # clamped
    assert sky["keywords"] == ["GRADIENT_BACKGROUND", "SUN"]                         # MOON switched off by the profile
    assert night["sky"]["colors"]["_GradientSkyUpperColor"] == [0.13, 0.15, 0.28, 1.0]
    # The profile's sun at 45° above the horizon along Unity's +X: its light shines down and back.
    sun = next(l for l in morning["lights"] if l["culling_mask"] == 16)
    assert sun["intensity"] == 0.4 and sun["color"] == [0.8, 0.5, 0.0, 1.0]
    assert not any(l["culling_mask"] == 16 for l in night["lights"])   # no SunFeature at night: off


def test_batched_copies_take_the_unbatched_mesh(bundle):
    nodes = load(bundle, "scene")["nodes"]
    pens = [n for n in nodes if n["name"].startswith("p_ks_r01_pen00")]
    assert len(pens) == 3 and len({n["renderer"]["mesh"] for n in pens}) == 1
    meshes = {m["id"]: m for m in load(bundle, "meshes")["meshes"]}
    assert not meshes[pens[0]["renderer"]["mesh"]].get("batched")
    cands = [c for c in load(bundle, "assets")["candidates"] if nodes[c["placements"][0]]["name"].startswith("p_ks_r01_pen00")]
    assert len(cands) == 1 and len(cands[0]["placements"]) == 3


def test_only_lod0_is_kept(bundle):
    n = names(bundle)
    assert "toon_tree00_00_LOD0" in n and "toon_tree00_00_LOD1" not in n and "toon_tree00_00_Billboard" not in n
    skipped = {s["reason"]: s["count"] for s in load(bundle, "map")["skipped"]}
    assert skipped == {"lod": 1, "billboard": 1}


def test_a_container_is_walked_into_only_under_the_root(bundle):
    nodes = load(bundle, "scene")["nodes"]
    placed = {nodes[p]["name"]: c for c in load(bundle, "assets")["candidates"] for p in c["placements"]}
    assert "p_ks_r01" not in placed
    assert len(placed["p_ks_r01_chair00"]["placements"]) == 2
    assert "p_ks_r01_shelf00" in placed and "shelf_part0" not in placed   # a Prop of two parts
