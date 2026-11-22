"""Game detection and the Map lists, on synthetic install folders and list records."""

import pytest

from kkbp_maps.extractor.games import KK, NotAGameFolder, UnsupportedGame, detect
from kkbp_maps.extractor.maplist import camera_profile, list_maps, map_key, thumbnail_names


def make_install(root, data_folder="Koikatu_Data", bundles=()):
    (root / data_folder).mkdir(parents=True)
    for b in bundles:
        path = root / "abdata" / b
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    (root / "abdata").mkdir(exist_ok=True)
    return root


def test_detects_kk_from_its_folder_or_its_abdata(tmp_path):
    root = make_install(tmp_path / "Koikatsu")
    assert detect(root).game is KK
    assert detect(root / "abdata").root == root


def test_later_games_are_detected_and_refused(tmp_path):
    root = make_install(tmp_path / "KKS", "KoikatsuSunshine_Data")
    with pytest.raises(UnsupportedGame, match="KKS"):
        detect(root)
    assert detect(root, require_supported=False).game.id == "KKS"


def test_a_folder_that_isnt_a_game(tmp_path):
    with pytest.raises(NotAGameFolder):
        detect(tmp_path)


def test_map_key():
    assert map_key("map/scene/1f.unity3d") == "map/scene/1f"
    assert map_key("studio/map/bushitu.unity3d") == "studio/map/bushitu"


MAPINFO = {"param": [
    {"MapName": "1F", "No": 2, "AssetBundleName": "map/scene/1f.unity3d", "AssetName": "1F", "is2D": 0,
     "isOutdoors": 1, "ThumbnailBundle": "map/thumbnail/00.unity3d", "ThumbnailAsset": "sp_map_01_00"},
    {"MapName": "公園", "No": 65, "AssetBundleName": "map/scene/park.unity3d", "AssetName": "Park", "is2D": 0,
     "isOutdoors": 1, "ThumbnailBundle": "map/thumbnail/20.unity3d", "ThumbnailAsset": "sp_map_34_02"},
    {"MapName": "どこか", "No": 99, "AssetBundleName": "map/scene/gone.unity3d", "AssetName": "Gone", "is2D": 0,
     "isOutdoors": 0, "ThumbnailBundle": "", "ThumbnailAsset": ""},
]}
STUDIO = {"list": [
    {"list": ["", "", "本体", "", "", "遮蔽", ""]},
    {"list": ["管理番号", "名称", "バンドルパス", "ファイルパス", "マニフェスト", "バンドルパス", "ファイルパス"]},
    {"list": ["1", "1F", "map/scene/1f.unity3d", "1F", "", "h/list/", "map_col_02"]},
    {"list": ["33", "空き部室", "studio/map/bushitu.unity3d", "bushitu"]},
]}


def fake_reader(path):
    if "mapinfo" in path.as_posix():
        return [("00", MAPINFO)]
    return [("Map_00", STUDIO), ("ItemList_00", {"list": [{"list": ["0", "x", "map/scene/park.unity3d"]}]})]


@pytest.fixture
def kk(tmp_path):
    return detect(make_install(tmp_path / "Koikatsu", bundles=[
        "map/scene/1f.unity3d", "map/scene/park.unity3d", "studio/map/bushitu.unity3d",
        "map/list/mapinfo/00.unity3d", "studio/info/00.unity3d"]))


def test_lists_merge_into_maps(kk):
    maps, missing = list_maps(kk, fake_reader)
    assert [m.key for m in maps] == ["map/scene/1f", "map/scene/park", "studio/map/bushitu"]
    assert missing == ["map/scene/gone"]
    one_f = maps[0]
    assert [e.record() for e in one_f.entries] == [{"list": "map", "no": 2, "name": "1F"},
                                                  {"list": "studio", "no": 1, "name": "1F"}]
    assert one_f.outdoor is True and one_f.thumbnail.asset == "sp_map_01_00"
    assert maps[2].outdoor is None and maps[2].thumbnail is None


def test_only_the_named_behaviours_of_a_studio_list_count(kk):
    maps, _ = list_maps(kk, fake_reader)
    assert [e.list for e in maps[1].entries] == ["map"]  # ItemList_00's row isn't a Map row


def test_camera_profile_follows_the_lists(kk):
    maps, _ = list_maps(kk, fake_reader)
    assert [camera_profile(kk, m) for m in maps] == ["game", "game", "studio"]


def test_thumbnail_names_per_time_of_day(kk):
    maps, _ = list_maps(kk, fake_reader)
    assert thumbnail_names(kk, maps[1].thumbnail) == {"day": "sp_map_34_00", "evening": "sp_map_34_01",
                                                      "night": "sp_map_34_02"}
