"""R44: each holding's main building goes back to the witness's tier (the built-state carry, 2026-11-19).

CONSEQUENCE: 8 (data) -- the game's 1.21 conversion resets every main building above tier 1 (274 on the founding
campaign: 164 tribe_02, 56 city_02, 51 temple_02, 3 castle_02, measured on v18 against v17, 14:1x). A wrong restore
puts a tier 1.21 does not define, or one the holding never had, at the root of the holding's tier chain.

The concept: only a raise, only to the witness's key in the same line, only where 1.21's holding district hosts it.
"""
import re

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import host_rules as H


@pytest.fixture
def host(tmp_path):
    c = tmp_path / "common"
    for d in ("holdings", "districts", "buildings"):
        (c / d).mkdir(parents=True)
    (c / "holdings" / "h.txt").write_text(
        "castle_holding = {\n\tprimary_district = castle_holding_district\n}\n"
        "tribal_holding = {\n\tprimary_district = tribal_holding_district\n}\n", encoding="utf-8")
    (c / "districts" / "holding_districts.txt").write_text(
        "castle_holding_district = {\n\tprimary_building = castle_01\n}\n"
        "tribal_holding_district = {\n\tprimary_building = tribe_01\n}\n", encoding="utf-8")
    (c / "buildings" / "b.txt").write_text(
        "castle_01 = {\n\tnext_building = castle_02\n}\ncastle_02 = {\n\tnext_building = castle_03\n}\ncastle_03 = {\n}\n"
        "tribe_01 = {\n}\n", encoding="utf-8")                      # tribe_02 is not defined here: refused
    H.load.cache_clear()
    return H.load(str(tmp_path))


def province_121(pid, district):
    return (f"\t{pid}={{\n\t\tholding={{\n\t\t\ttype=castle_holding\n\t\t\tdistricts={{ 4294967295 4294967295 }}\n"
            f"\t\t\tholding_district={district}\n\t\t}}\n\t}}\n")


def province_120(pid, holding, keys):
    bl = " ".join(f'{{\n\t\t\t\t\ttype="{k}"\n\t\t\t\t}}\n' for k in keys)
    return f'\t{pid}={{\n\t\tholding={{\n\t\t\ttype="{holding}"\n\t\t\tbuildings={{ {bl} }}\n\t\t}}\n\t}}\n'


SAVE = ("meta_data={ version=\"1.21.0\" }\nprovinces={\n"
        + province_121(1, 101) + province_121(2, 102) + province_121(3, 103) + province_121(4, 104) + "}\n"
        "buildings={\n\tdatabase={\n\t\t201={\n\t\t\ttype=castle_01\n\t\t}\n\t\t202={\n\t\t\ttype=castle_02\n\t\t}\n"
        "\t\t203={\n\t\t\ttype=tribe_01\n\t\t}\n\t\t204={\n\t\t\ttype=castle_01\n\t\t}\n\t}\n}\n"
        "districts={\n\tdatabase={\n"
        + "".join(f"\t\t{d}={{\n\t\t\tbuildings={{ {b} }}\n\t\t\ttype={t}\n\t\t\towner={p}\n\t\t}}\n"
                  for p, d, b, t in ((1, 101, 201, "castle_holding_district"), (2, 102, 202, "castle_holding_district"),
                                     (3, 103, 203, "tribal_holding_district"), (4, 104, 204, "castle_holding_district")))
        + "\t}\n}\n").encode()

WITNESS = ("meta_data={ version=\"1.20.1.2\" }\nprovinces={\n"
           + province_120(1, "castle_holding", ["castle_03", "farm_estates_02"])   # raised to the witness's tier
           + province_120(2, "castle_holding", ["castle_01"])                      # never lowered
           + province_120(3, "tribal_holding", ["tribe_02"])                       # tribe_02 undefined: refused
           + province_120(4, "castle_holding", ["farm_estates_03"])                # no main line in the witness
           + "}\n").encode()


def building_types(g):
    return {e.key.decode(): re.search(rb"type=(\S+)", g[e.open:e.close]).group(1).decode()
            for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)}


def test_a_main_building_is_raised_to_the_witnesss_tier_and_never_lowered(host):
    r = C.carry_holding_tiers(SAVE, host, WITNESS)
    assert r.restored == [("1", "castle_01", "castle_03")]
    t = building_types(r.gamestate)
    assert t == {"201": "castle_03", "202": "castle_02", "203": "tribe_01", "204": "castle_01"}


def test_a_tier_the_game_does_not_define_is_refused_and_named(host):
    r = C.carry_holding_tiers(SAVE, host, WITNESS)
    assert [(p, k) for p, k, _ in r.skipped] == [("3", "tribe_02")]
    assert "not a building this game defines" in r.skipped[0][2]


def test_nothing_changes_but_the_one_type_and_a_clean_save_is_returned_untouched(host):
    r = C.carry_holding_tiers(SAVE, host, WITNESS)
    assert r.gamestate.replace(b"type=castle_03", b"type=castle_01", 1) == SAVE
    assert C.carry_holding_tiers(SAVE, host, SAVE.replace(b"1.21.0", b"1.20")).gamestate is SAVE   # no witness lines
