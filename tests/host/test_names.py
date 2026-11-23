"""The Name Tables: English names word by word, categories, overrides, and KK's tables themselves."""

from kkbp_maps.builder.names import NameTables

TABLES = NameTables({
    "naming": {"strip": ["^p_", "^mo_", "^o_", "^koi_", r"^map\d+_"], "default_category": "Other"},
    "words": {"wall": "Wall", "kaidan": "Stairs", "desk": "Desk", "isu": "Chair"},
    "categories": [{"category": "Furniture", "words": ["desk", "isu"]}],
    "overrides": [{"match": "^o_kouen_isu_", "kind": "prop"}, {"hash": "ab" * 16, "name": "Odd One"}],
    "times_of_day": {"day": "Day"},
    "maps": {"map/scene/1f": {"name": "School 1F", "area": "School"}},
})


def test_words_are_translated_and_numbers_kept():
    n = TABLES.name("mo_koi_map02_wall06_kaidan03")
    assert n.english == "Wall 06 Stairs 03"
    assert n.words == ("wall", "kaidan") and n.unknown == ()


def test_copy_suffixes_and_nested_prefixes_are_cut():
    assert TABLES.name("p_o_koi_desk01 (1)").english == "Desk 01"
    assert TABLES.name("mo_koi_map34_gura00_ami00 1").words == ("gura", "ami")


def test_unknown_words_keep_their_romaji():
    n = TABLES.name("p_o_koi_nisu00")
    assert n.english == "Nisu 00" and n.unknown == ("nisu",)


def test_the_last_word_is_never_stripped():
    assert TABLES.name("p_").english == "P"
    assert TABLES.name("mo_koi").english == "Koi"


def test_categories_and_overrides():
    assert TABLES.category(TABLES.name("p_o_koi_desk05")) == "Furniture"
    assert TABLES.category(TABLES.name("p_o_koi_vase")) == "Other"
    assert TABLES.override("o_kouen_isu_00", "00" * 16).kind == "prop"
    assert TABLES.override("o_road_00", "ab" * 16).name == "Odd One"
    assert TABLES.override("o_road_00", "00" * 16) is None


def test_maps_and_times_of_day():
    assert TABLES.map_name("map/scene/1f") == "School 1F" and TABLES.map_area("map/scene/1f") == "School"
    assert TABLES.map_name("map/scene/none") is None
    assert TABLES.time_of_day("day") == "Day" and TABLES.time_of_day("night") == "Night"


def test_kk_tables_load_and_name_every_map_with_an_area():
    kk = NameTables.load("KK")
    assert len(kk.maps) == 43
    assert all(m.get("name") and m.get("area") for m in kk.maps.values())
    assert kk.override("o_kouen_gaitou_01", "00" * 16).kind == "prop"
    assert kk.override("o_kouen_kakiwari_ki_00", "00" * 16) is None
