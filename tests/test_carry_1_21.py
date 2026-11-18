"""carry_1_21.carry_wonders: a 1.20 holding's built wonders written as 1.21 districts (patch day S6, decision C).

A synthetic 1.20-shaped gamestate and a synthetic 1.21 game folder. Each case is a lesson the real save taught: the
three built-wonder blocks, a bare slot that is not a wonder, a renamed building with no district, a tier the district
does not list, an already-filled slot, and the databases created when the 1.20 save has none.
"""
import re

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import host_rules as H


@pytest.fixture
def host(tmp_path):
    c = tmp_path / "common"
    for sub in ("holdings", "districts", "buildings"):
        (c / sub).mkdir(parents=True)
    (c / "holdings" / "00_holdings.txt").write_text("castle_holding = {\n\tdistricts = { }\n}\n", encoding="utf-8")
    (c / "districts" / "special_districts.txt").write_text(
        "danevirke_01_district = {\n\tbuildings = { danevirke_01 }\n}\n", encoding="utf-8")
    (c / "districts" / "great_districts.txt").write_text(
        "the_great_wall_01_district = {\n\tbuildings = { the_great_wall_01 }\n}\n", encoding="utf-8")
    (c / "districts" / "duchy_capital_districts.txt").write_text(
        "theodosian_walls_01_district = {\n\tbuildings = { theodosian_walls_01 }\n}\n", encoding="utf-8")
    (c / "buildings" / "b.txt").write_text("".join(f"{k} = {{\n}}\n" for k in (
        "danevirke_01", "the_great_wall_01", "the_great_wall_02", "theodosian_walls_01", "march_01",
        "holy_site_cathedral_01")), encoding="utf-8")
    H.load.cache_clear()
    return H.load(str(tmp_path))


def prov(pid, inner):
    return f"\t{pid}={{\n\t\tholding={{\n\t\t\ttype=\"castle_holding\"\n{inner}\t\t\tlevy=1\n\t\t}}\n\t}}\n"


SAVE = ("meta_data={ version=\"1.20.1.2\" }\nprovinces={\n"
        + prov(62, '\t\t\tspecial_building={\n\t\t\t\ttype="danevirke_01"\n\t\t\t}\n\t\t\tspecial_building_type="danevirke_01"\n')
        + prov(18, '\t\t\tspecial_building_type="holy_site_cathedral_01"\n')          # a bare slot: not built
        + prov(10061, "\t\t\tgreat_building={\n\t\t\t\ttype=the_great_wall_01\n\t\t\t}\n")
        + prov(10064, "\t\t\tgreat_building={\n\t\t\t\ttype=the_great_wall_02\n\t\t\t}\n")
        + prov(496, '\t\t\tduchy_capital_building={\n\t\t\t\ttype="theodosian_walls_01"\n\t\t\t}\n')
        + prov(482, '\t\t\tduchy_capital_building={\n\t\t\t\ttype="march_01"\n\t\t\t}\n')
        + "}\n").encode()


def holding(g, pid):
    e = next(e for e in gs.iter_entries(g, *gs.locate(g, "provinces").body) if e.key == str(pid).encode())
    return g[e.open:e.close].decode()


def test_each_built_wonder_goes_to_its_slot_with_the_games_own_lines(host):
    r = C.carry_wonders(SAVE, host)
    assert sorted((p, s) for p, _, _, s in r.carried) == [
        ("10061", "great_district"), ("496", "duchy_capital_district"), ("62", "special_district")]
    h62, h10061, h496 = holding(r.gamestate, 62), holding(r.gamestate, 10061), holding(r.gamestate, 496)
    assert re.search(r"special_district=\d+\n\t\t\tspecial_district_type=danevirke_01_district", h62)
    assert re.search(r"great_district=\d+\n\t\t\tgreat_district_type=the_great_wall_01_district", h10061)
    assert re.search(r"duchy_capital_district=\d+", h496) and "duchy_capital_district_type" not in h496


def test_the_districts_and_buildings_databases_are_created_and_point_at_each_other(host):
    g = C.carry_wonders(SAVE, host).gamestate
    dist = {e.key.decode(): g[e.open:e.close].decode() for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body)}
    blds = {e.key.decode(): g[e.open:e.close].decode() for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)}
    assert len(dist) == len(blds) == 3
    sd = re.search(r"special_district=(\d+)", holding(g, 62)).group(1)
    bid = re.search(r"buildings=\{ (\d+) \}", dist[sd]).group(1)
    assert "type=danevirke_01_district" in dist[sd] and "owner=62" in dist[sd] and "type=danevirke_01" in blds[bid]


def test_a_bare_slot_is_not_a_wonder(host):
    r = C.carry_wonders(SAVE, host)
    assert "18" not in {p for p, *_ in r.carried} and "special_district=" not in holding(r.gamestate, 18)


def test_a_wonder_with_no_district_by_name_is_reported_not_guessed(host):
    r = C.carry_wonders(SAVE, host)
    assert [(p, b) for p, b, _ in r.unmapped] == [("482", "march_01")]
    assert "duchy_capital_district=" not in holding(r.gamestate, 482)


def test_a_tier_the_district_does_not_list_is_refused_and_reported(host):
    # the great wall's tiers 2 and 3: 1.21's district lists only tier 1, and a tier-1 wall would be a guess
    r = C.carry_wonders(SAVE, host)
    assert [(p, b) for p, b, _ in r.skipped] == [("10064", "the_great_wall_02")]
    assert "great_district=" not in holding(r.gamestate, 10064)


def test_a_second_run_changes_nothing(host):
    once = C.carry_wonders(SAVE, host).gamestate
    again = C.carry_wonders(once, host)
    assert again.carried == [] and again.gamestate == once


def test_a_witness_supplies_the_wonders_for_a_save_the_game_already_converted(host):
    # phase two without phase one (the Director, 2026-11-18): the player's 1.21 re-save has lost its wonders; the
    # last 1.20 save is the witness. Measured in the game: the next re-save kept all 134 (and 4,201 roads)
    converted = re.sub(rb"\n\t\t\t(?:special_building|great_building|duchy_capital_building)=\{[^{}]*\}", b"", SAVE)
    assert C.carry_wonders(converted, host).carried == []               # nothing left in the save itself
    r = C.carry_wonders(converted, host, witness=SAVE)
    assert sorted((p, s) for p, _, _, s in r.carried) == [
        ("10061", "great_district"), ("496", "duchy_capital_district"), ("62", "special_district")]
    assert "special_district_type=danevirke_01_district" in holding(r.gamestate, 62)


def test_rows_go_after_the_existing_ones_when_the_databases_exist(host):
    pre = SAVE + b"districts={\n\tdatabase={\n\t\t7={\n\t\t\ttype=x\n\t\t}\n\t}\n}\n" \
                 b"buildings={\n\tdatabase={\n\t\t9={\n\t\t\ttype=y\n\t\t}\n\t}\n}\n"
    g = C.carry_wonders(pre, host).gamestate
    assert [e.key for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body)] == [b"7", b"8", b"9", b"10"]
    assert [e.key for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)] == [b"9", b"10", b"11", b"12"]
