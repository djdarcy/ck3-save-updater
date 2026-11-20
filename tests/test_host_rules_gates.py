"""host_rules, stage two: the gates the carry could not judge (goal 2026-11-19__22-43-27, S2).

CONSEQUENCE: 8 (data) -- before this, every duchy-capital building, every resource tier above 1 and every minor
resource building came back "not evaluated" (None), and None is never written: the stage-two carries would write
nothing. A gate evaluated wrongly writes a building the game refuses silently (it keeps illegal states), or drops one
the player built.

The concept: a gate the save can answer is answered (True or False); a gate that asks a fact the caller did not supply
stays None, so nothing is ever written blind.
"""
from pathlib import Path

import pytest

from ck3_save_migrator import host_rules as H


@pytest.fixture
def rules(tmp_path):
    c = tmp_path / "common"
    for d in ("holdings", "districts", "buildings", "scripted_triggers"):
        (c / d).mkdir(parents=True)
    (c / "scripted_triggers" / "t.txt").write_text(
        "req_level = {\n\ttrigger_if = {\n\t\tlimit = { has_holding_type = castle_holding }\n"
        "\t\thas_building_or_higher = castle_$LEVEL$\n\t}\n\ttrigger_else_if = {\n\t\tlimit = { has_holding_type = city_holding }\n"
        "\t\thas_building_or_higher = city_$LEVEL$\n\t}\n\ttrigger_else = { always = no }\n}\n"
        "is_tribal = {\n\tscope:holder ?= { government_has_flag = government_is_tribal }\n}\n", encoding="utf-8")
    (c / "buildings" / "b.txt").write_text(
        "castle_01 = { next_building = castle_02 }\ncastle_02 = { next_building = castle_03 }\ncastle_03 = { }\n"
        "city_01 = { }\n"
        "keep_01 = {\n\tcan_construct_potential = {\n\t\treq_level = { LEVEL = 02 }\n\t\tis_tribal = no\n\t}\n"
        "\tcan_construct_showing_failures_only = {\n\t\tculture = { has_innovation = innovation_burhs }\n\t}\n}\n",
        encoding="utf-8")
    (c / "districts" / "duchy_capital_districts.txt").write_text(
        "keep_district = {\n\tprimary_building = keep_01\n\tis_enabled = { can_have_duchy_capital_building_trigger = yes }\n}\n",
        encoding="utf-8")
    H.load.cache_clear()
    return H.load(str(tmp_path))


def place(**kw):
    base = dict(county_capital=True, holding="castle_holding", government_flags=frozenset({"government_is_feudal"}),
                main_building="castle_02", buildings=frozenset(), innovations=frozenset({"innovation_burhs"}),
                duchy_capital=True)
    return H.Place(**{**base, **kw})


def legal(rules, p):
    return rules.building_legal("keep_01", "keep_district", "keep_01", p).ok


def test_the_parameterised_level_chain_reads_or_higher_up_the_line_and_takes_one_branch(rules):
    assert legal(rules, place()) is True                                   # castle_02 satisfies castle_$LEVEL$ = 02
    assert legal(rules, place(main_building="castle_03")) is True          # a higher tier satisfies it too
    assert legal(rules, place(main_building="castle_01")) is False         # a lower tier does not
    assert legal(rules, place(holding="city_holding", main_building="city_01")) is False   # the city branch: city_02
    assert legal(rules, place(holding="tribal_holding")) is False          # trigger_else: always = no


def test_a_negated_scripted_trigger_a_holder_scope_and_an_innovation_are_answered(rules):
    assert legal(rules, place(government_flags=frozenset({"government_is_tribal"}))) is False   # is_tribal = no
    assert legal(rules, place(innovations=frozenset())) is False           # the failures-only block is read
    assert rules.district_enabled("keep_district", place(duchy_capital=False)).ok is False
    assert rules.districts["keep_district"].kind == "duchy_capital"


def test_a_fact_the_caller_did_not_supply_leaves_the_gate_unevaluated_never_written(rules):
    assert legal(rules, place(government_flags=None)) is None
    assert legal(rules, place(innovations=None)) is None
    assert legal(rules, place(main_building=None, buildings=None)) is None
    assert rules.district_enabled("keep_district", place(duchy_capital=None)).ok is None


GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")


@pytest.mark.skipif(not GAME.is_dir(), reason="needs the 1.21 game files")
def test_against_the_game_the_stage_two_buildings_get_a_verdict():
    H.load.cache_clear()
    r = H.load(str(GAME))
    p = place(county_goods=frozenset({"stone", "wood"}), innovations=frozenset({"innovation_burhs", "innovation_manorialism"}))
    cases = {("march_01", "military_duchy_capital_district", "military_duchy_building_01"): True,
             ("royal_forest_01", "ducal_residence_district", "ducal_residence_01"): True,
             ("stone_resource_building_2", "stone_district", "stone_resource_building_2"): True,
             ("stone_resource_building_3", "stone_district", "stone_resource_building_3"): False,   # an absent innovation
             ("stone_cutters_1", "forestry_district", "forestry_resource_building_1"): True,
             ("assay_district_01", "assay_district", "assay_district_01"): False}                 # needs prospecting
    got = {k: r.building_legal(*k, p).ok for k in cases}
    assert got == cases
    assert r.building_legal("march_01", "military_duchy_capital_district", "military_duchy_building_01",
                            place(government_flags=frozenset({"government_is_tribal"}))).ok is False
