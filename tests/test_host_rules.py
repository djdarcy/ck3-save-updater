"""host_rules: where the game accepts a building in 1.21 (the hostability rule, 2026-11-17).

A synthetic game folder in 1.21's shape, carrying each lesson the real files taught: definitions in subfolders, a BOM
before the first key, hyphenated keys, a holding district naming its line as primary_building, resource and special
districts that belong to the province rather than the holding, and gated districts.
"""
import pytest

from ck3_save_migrator import host_rules as H

BOM = "﻿"


@pytest.fixture
def rules(tmp_path):
    c = tmp_path / "common"
    (c / "holdings").mkdir(parents=True)
    (c / "holdings" / "00_holdings.txt").write_text(
        BOM + "castle_holding = {\n\tprimary_district = castle_holding_district\n\tdistricts = {\n"
        "\t\tvillages_district\n\t\tborder_forts_district\n\t\t# a_comment_district\n\t}\n}\n"
        "city_holding = {\n\tprimary_district = city_holding_district\n\tdistricts = { urban_district }\n}\n",
        encoding="utf-8")
    (c / "districts" / "sub").mkdir(parents=True)                       # 1.21 keeps files in subfolders
    (c / "districts" / "sub" / "holding_districts.txt").write_text(
        BOM + "castle_holding_district = {\n\tprimary_building = castle_01\n}\n"
        "city_holding_district = {\n\tprimary_building = city_01\n}\n", encoding="utf-8")
    (c / "districts" / "sub" / "regular_districts.txt").write_text(
        BOM + "villages_district = {\n\tbuildings = { meadowlands_pastures_1 al-andalus_mill_1 }\n}\n"
        "border_forts_district = {\n\tcan_construct_potential = { always = yes }\n\tbuildings = { border_bulwarks_1 }\n}\n"
        "urban_district = {\n\tbuildings = { burgage_plots_1 }\n}\n", encoding="utf-8")
    (c / "districts" / "sub" / "resource_districts.txt").write_text(
        BOM + "wool_district = {\n\tcan_construct_potential = { always = yes }\n\tbuildings = { wool_resource_building_1 }\n}\n",
        encoding="utf-8")
    (c / "districts" / "sub" / "great_districts.txt").write_text(
        BOM + "alhambra_01_district = {\n\tbuildings = { alhambra_01 }\n}\n"
        "the_great_wall_01_district = {\n\tbuildings = { the_great_wall_01 }\n}\n", encoding="utf-8")
    (c / "buildings" / "deep").mkdir(parents=True)
    keys = ["castle_01", "city_01", "meadowlands_pastures_1", "al-andalus_mill_1", "border_bulwarks_1",
            "burgage_plots_1", "wool_resource_building_1", "alhambra_01", "the_great_wall_01", "the_great_wall_02",
            "march_01"]
    body = BOM + "castle_01 = {\n\tnext_building = castle_02\n}\ncastle_02 = {\n}\n" + \
        "".join(f"{k} = {{\n}}\n" for k in keys if k != "castle_01")
    (c / "buildings" / "deep" / "00_buildings.txt").write_text(body, encoding="utf-8")
    H.load.cache_clear()
    return H.load(str(tmp_path))


def test_a_building_a_district_of_the_holding_lists_is_accepted(rules):
    v = rules.building_on("meadowlands_pastures_1", "castle_holding")
    assert v.ok is True and "villages_district" in v.why and v.where.startswith("regular_districts.txt:")


def test_a_holding_districts_primary_building_and_its_next_tiers_are_accepted(rules):
    # castle_holding_district names castle_01 as primary_building, not in buildings = { } (the real 1.21 shape)
    assert rules.building_on("castle_01", "castle_holding").ok is True
    assert rules.building_on("castle_02", "castle_holding").ok is True          # through next_building
    assert rules.building_on("castle_01", "city_holding").ok is False           # not this holding's line


def test_hyphenated_keys_and_the_first_key_behind_the_bom_are_read(rules):
    assert rules.building_on("al-andalus_mill_1", "castle_holding").ok is True
    assert "castle_holding" in rules.holdings and "castle_holding_district" in rules.districts


def test_a_building_no_district_of_the_holding_lists_is_refused_with_the_holding_cited(rules):
    v = rules.building_on("burgage_plots_1", "castle_holding")
    assert v.ok is False and "no district of castle_holding" in v.why and v.where.startswith("00_holdings.txt:")
    assert rules.building_on("nope_1", "castle_holding").ok is False
    assert rules.building_on("castle_01", "nope_holding").ok is False


def test_a_building_only_a_gated_district_hosts_is_left_to_the_game(rules):
    v = rules.building_on("border_bulwarks_1", "castle_holding")
    assert v.ok is None and "a trigger decides" in v.why


def test_resource_and_special_districts_belong_to_the_province(rules):
    # the first real control failed on this: no holding lists a resource district
    assert rules.districts["wool_district"].kind == "resource"
    assert rules.districts["alhambra_01_district"].kind == "special"
    assert rules.districts["villages_district"].kind == "regular"
    assert rules.building_on("wool_resource_building_1", "castle_holding").ok is False
    assert rules.building_in("wool_resource_building_1", "wool_district").ok is None    # gated by the trade good
    assert rules.building_in("alhambra_01", "alhambra_01_district").ok is True
    assert rules.building_in("castle_01", "wool_district").ok is False


def test_a_wonder_finds_its_district_exactly_by_family_or_not_at_all(rules):
    assert rules.wonder_district("alhambra_01") == ("alhambra_01_district", "exact")
    assert rules.wonder_district("the_great_wall_02") == ("the_great_wall_01_district", "family")
    d, why = rules.wonder_district("march_01")
    assert d is None and "march_01_district" in why
