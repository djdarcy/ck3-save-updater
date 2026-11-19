"""The built-state carry, phase two: a holding's 1.20 regular buildings written into the districts 1.21's conversion
left empty, legal by the game's own gates (design of record: the collabN-local 1 final assessment, 2026-11-19 13:49).

CONSEQUENCE: 9 (data) -- the game keeps illegal district states silently, so every gate the carry skips writes a
broken realm nobody sees; and every building not written must be named, not lost.

One synthetic game and save pair, one province per lesson:
  1 a capital castle, size 3 (2 slots): pastures_02 + cereal_fields_03 -> one villages district, primary raised to 3
  2 a barony castle: ramparts_01 -> walls is enabled only in a county capital, so refused
  3 a capital castle whose county has no grain potential: cereal_fields_02 -> the good gate refuses it
  4 a capital castle with an open family (guild_halls) -> named, not written
  5 a capital castle with outposts_01 only -> manor houses need villages, so dropped
  6 a capital castle that already has a district -> never touched
"""
import re

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import host_rules as H
from ck3_save_migrator.district_lint import Facts

E = "4294967295"


@pytest.fixture
def host(tmp_path):
    c = tmp_path / "common"
    for d in ("holdings", "districts", "buildings"):
        (c / d).mkdir(parents=True)
    (c / "holdings" / "h.txt").write_text(
        "castle_holding = {\n\tprimary_district = castle_holding_district\n"
        "\tdistricts = { villages_district walls_district manor_houses_district }\n}\n", encoding="utf-8")
    (c / "districts" / "holding_districts.txt").write_text(
        "castle_holding_district = {\n\tprimary_building = castle_01\n}\n", encoding="utf-8")
    (c / "districts" / "regular_districts.txt").write_text(
        "villages_district = {\n\tprimary_building = pb_villages_01\n"
        "\tbuildings = { farming_fields_1 meadowlands_pastures_1 }\n}\n"
        "walls_district = {\n\tprimary_building = pb_walls_01\n\tis_enabled = {\n\t\tis_county_capital = yes\n\t}\n"
        "\tbuildings = { ramparts_1 }\n}\n"
        "manor_houses_district = {\n\tprimary_building = pb_manor_houses_01\n\tunlocked_by = villages_district\n"
        "\tbuildings = { manor_tower_1 }\n}\n", encoding="utf-8")
    pot = lambda goods: ("\tcan_construct_potential = {\n\t\tOR = {\n" + "".join(          # noqa: E731
        f"\t\t\tcounty = {{ has_potential_for_trade_good = trade_good_type:trade_good_{x} }}\n" for x in goods)
        + "\t\t}\n\t}\n")
    chain = lambda fam, n, extra="", slots=None: "".join(                                   # noqa: E731
        f"{fam}_{'%02d' % i if fam.startswith('pb_') else i} = {{\n"
        + (f"\tnext_building = {fam}_{'%02d' % (i + 1) if fam.startswith('pb_') else i + 1}\n" if i < n else "")
        + (f"\tdistrict_level_requirement = {i}\n" if i > 1 and not fam.startswith("pb_") else "")
        + (f"\tbuilding_slots_for_host_district = {slots + i - 1}\n" if slots else "") + extra + "}\n"
        for i in range(1, n + 1))
    (c / "buildings" / "b.txt").write_text(
        "castle_01 = {\n}\n" + chain("pb_villages", 4, slots=2) + chain("pb_walls", 2, slots=1)
        + chain("pb_manor_houses", 2, slots=1) + chain("farming_fields", 5, pot(["grain"]))
        + chain("meadowlands_pastures", 5, pot(["wool"])) + chain("ramparts", 3) + chain("manor_tower", 2),
        encoding="utf-8")
    H.load.cache_clear()
    return H.load(str(tmp_path))


TABLE = {f: {"successors": [{"building": b, "district": d, "source": "test"}]} for f, b, d in (
    ("pastures", "meadowlands_pastures", "villages_district"), ("cereal_fields", "farming_fields", "villages_district"),
    ("ramparts", "ramparts", "walls_district"), ("outposts", "manor_tower", "manor_houses_district"))}
TABLE["guild_halls"] = {"successors": [], "open": "open: djdarcy's answer pending"}


def p121(pid, districts=f"{E} {E}"):
    return (f"\t{pid}={{\n\t\tholding={{\n\t\t\ttype=castle_holding\n\t\t\tdistricts={{ {districts} }}\n\t\t}}\n\t}}\n")


def p120(pid, keys):
    bl = " ".join(f'{{\n\t\t\t\t\ttype="{k}"\n\t\t\t\t}}\n' for k in keys)
    return f'\t{pid}={{\n\t\tholding={{\n\t\t\ttype="castle_holding"\n\t\t\tbuildings={{ {bl} }}\n\t\t}}\n\t}}\n'


SAVE = ("meta_data={ version=\"1.21.0\" }\nprovinces={\n" + "".join(p121(i) for i in range(1, 6)) + p121(6, f"77 {E}")
        + "}\nbuildings={\n\tdatabase={\n\t\t300={\n\t\t\ttype=pb_villages_01\n\t\t}\n\t}\n}\n"
        "districts={\n\tdatabase={\n\t\t77={\n\t\t\tbuildings={ 300 }\n\t\t\ttype=villages_district\n\t\t\towner=6\n"
        "\t\t}\n\t}\n}\n").encode()
WITNESS = ("meta_data={ version=\"1.20.1.2\" }\nprovinces={\n"
           + p120(1, ["castle_01", "pastures_02", "cereal_fields_03"]) + p120(2, ["castle_01", "ramparts_01"])
           + p120(3, ["castle_01", "cereal_fields_02"]) + p120(4, ["castle_01", "guild_halls_02"])
           + p120(5, ["castle_01", "outposts_01"]) + p120(6, ["castle_01", "pastures_01"]) + "}\n").encode()
GOODS = frozenset({"grain", "wool"})
FACTS = {"1": Facts(H.Place(True, "castle_holding", GOODS), 3), "2": Facts(H.Place(False, "castle_holding", GOODS), 3),
         "3": Facts(H.Place(True, "castle_holding", frozenset({"wool"})), 3),
         "4": Facts(H.Place(True, "castle_holding", GOODS), 3), "5": Facts(H.Place(True, "castle_holding", GOODS), 3),
         "6": Facts(H.Place(True, "castle_holding", GOODS), 3)}


def by_province(rows):
    out = {}
    for r in rows:
        out.setdefault(r[0], []).append(r)
    return out


def test_buildings_keep_their_tiers_in_a_district_raised_to_hold_them(host):
    r = C.carry_districts(SAVE, host, WITNESS, FACTS, TABLE)
    assert by_province(r.written)["1"] == [("1", "villages_district", ["farming_fields_3", "meadowlands_pastures_2"],
                                            "pb_villages_03")]
    g = r.gamestate
    prov = next(e for e in gs.iter_entries(g, *gs.locate(g, "provinces").body) if e.key == b"1")
    did = re.search(rb"districts=\{ (\d+) " + E.encode() + rb" \}", g[prov.open:prov.close]).group(1)
    d = next(e for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if e.key == did)
    assert b"type=villages_district" in g[d.open:d.close] and b"owner=1" in g[d.open:d.close]


def test_cap_keeps_primaries_at_tier_one_and_the_buildings_with_them(host):
    r = C.carry_districts(SAVE, host, WITNESS, FACTS, TABLE, tier_policy="cap")
    assert by_province(r.written)["1"][0][2:] == (["farming_fields_1", "meadowlands_pastures_1"], "pb_villages_01")


def test_a_district_disabled_here_or_a_county_without_the_good_writes_nothing(host):
    r = C.carry_districts(SAVE, host, WITNESS, FACTS, TABLE)
    refused = by_province(r.refused)
    assert "2" not in by_province(r.written) and "enabled" in refused["2"][0][2]       # walls: capital only
    assert "3" not in by_province(r.written) and "potential" in refused["3"][0][2]     # no grain in this county


def test_what_is_not_carried_is_named_with_its_reason(host):
    r = C.carry_districts(SAVE, host, WITNESS, FACTS, TABLE)
    assert by_province(r.open)["4"] == [("4", "guild_halls_02", "open: djdarcy's answer pending")]
    assert by_province(r.dropped)["5"] == [("5", "outposts_01", "manor_houses_district needs villages_district")]


def test_a_dependent_district_goes_when_its_prerequisite_loses_every_building(host):
    # the case the lint caught on v18 (14:3x): villages passes the first check, then its pastures are refused (no wool
    # in this county), so the manor district would stand without villages
    save = SAVE.replace(b"provinces={\n", b"provinces={\n" + p121(7).encode())
    witness = WITNESS.replace(b"provinces={\n", b"provinces={\n" + p120(7, ["castle_01", "pastures_01",
                                                                           "outposts_01"]).encode())
    facts = dict(FACTS, **{"7": Facts(H.Place(True, "castle_holding", frozenset()), 3)})
    r = C.carry_districts(save, host, witness, facts, TABLE)
    assert "7" not in by_province(r.written)
    assert ("7", "outposts_01", "manor_houses_district needs villages_district") in r.dropped


def test_phase_one_inserts_the_districts_line_into_a_1_20_holding(host):
    # R41: a 1.20 holding has no districts line; the carry writes one, two slots wide (the conversion's), after type=
    save = WITNESS.replace(b"1.20.1.2", b"1.20.1.2")                # the 1.20 save is its own witness
    r = C.carry_districts(save, host, save, FACTS, TABLE, insert=True)
    assert by_province(r.written)["1"][0][1] == "villages_district"
    g = r.gamestate
    prov = next(e for e in gs.iter_entries(g, *gs.locate(g, "provinces").body) if e.key == b"1")
    body = g[prov.open:prov.close].decode()
    assert re.search(r'type="castle_holding"\n\t\t\tdistricts=\{ \d+ ' + E + r' \}', body)
    assert C.carry_districts(save, host, save, FACTS, TABLE).written == []      # without insert: nothing to fill


def test_a_holding_that_already_has_a_district_is_never_touched(host):
    r = C.carry_districts(SAVE, host, WITNESS, FACTS, TABLE)
    assert "6" not in by_province(r.written) and "6" not in by_province(r.refused)
    assert f"districts={{ 77 {E} }}".encode() in r.gamestate
