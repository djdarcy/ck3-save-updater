"""roads.transplant_roads: a 1.21 save without roads gets the reference's (patch day S7, class 2).

Measured on 1.21.0 (2026-11-17): the game's own conversion leaves roads/database empty; the reference holds 4,201
roads (type, tier, two dates, sometimes trade_routes links). Synthetic gamestates in the same shape.
"""
import pytest

from ck3_save_migrator import roads as R

REF = (b"meta_data={ version=\"1.21.0\" }\n"
       b"roads={\n\tdatabase={\n"
       b"\t\t0={\n\t\t\ttype=aachen_to_brabant_road\n\t\t\ttier=0\n\t\t\tupgrade_start_date=-1.1.1\n"
       b"\t\t\tdecay_start_date=-1.1.1\n\t\t}\n"
       b"\t\t1={\n\t\t\ttype=al-qahira_to_giza_road\n\t\t\ttier=1\n\t\t\ttrade_routes={ 10 11 }\n"
       b"\t\t\tupgrade_start_date=-1.1.1\n\t\t\tdecay_start_date=-1.1.1\n\t\t}\n"
       b"\t\t2={\n\t\t\ttype=gone_in_this_version_road\n\t\t\ttier=0\n\t\t}\n"
       b"\t}\n}\n")
TARGET = (b"meta_data={ version=\"1.21.0\" }\n"
          b"provinces={ 1={ x=1 } }\n"
          b"roads={\n\tdatabase={\n\t}\n}\n"
          b"trade_routes={\n\tdatabase={\n\t}\n}\n")
DEFINED = {"aachen_to_brabant_road", "al-qahira_to_giza_road"}


def test_an_empty_roads_database_gets_the_references_roads():
    r = R.transplant_roads(TARGET, REF, DEFINED)
    assert r.why_not is None and r.carried == 2 and r.links_dropped == 1
    roads = R._entries(r.gamestate)
    assert [e.key for e in roads] == [b"0", b"1"]                       # the reference's ids, in order
    body1 = r.gamestate[roads[1].open:roads[1].close]
    assert b"type=al-qahira_to_giza_road" in body1 and b"tier=1" in body1
    assert b"trade_routes" not in body1                                  # routes are the game's (the goal's Out)
    head, tail = TARGET.split(b"roads={")
    assert r.gamestate.startswith(head) and r.gamestate.endswith(b"trade_routes={\n\tdatabase={\n\t}\n}\n")


def test_a_road_the_game_does_not_define_is_skipped_and_named():
    r = R.transplant_roads(TARGET, REF, DEFINED)
    assert r.skipped_undefined == ["gone_in_this_version_road"]
    assert b"gone_in_this_version_road" not in r.gamestate


def test_without_a_list_of_defined_types_every_road_is_carried():
    assert R.transplant_roads(TARGET, REF).carried == 3


@pytest.mark.parametrize("target, why", [
    (TARGET.replace(b"roads={\n\tdatabase={\n\t}\n}\n", b""), "not a 1.21 save"),
    (None, "already holds roads"),
])
def test_nothing_is_written_when_the_save_is_not_ready_for_roads(target, why):
    if target is None:                                                    # roads already there: the game's or ours
        target = R.transplant_roads(TARGET, REF, DEFINED).gamestate
    r = R.transplant_roads(target, REF, DEFINED)
    assert why in r.why_not and r.gamestate == target and r.carried == 0


def test_a_reference_without_roads_writes_nothing():
    r = R.transplant_roads(TARGET, TARGET, DEFINED)
    assert "reference holds no roads" in r.why_not and r.gamestate == TARGET


def test_defined_road_types_reads_past_the_bom_and_keeps_hyphens(tmp_path):
    # both broke on the real 1.21 files (2026-11-17): the BOM hid each file's first key, and \w+ cut "al-..." short
    d = tmp_path / "common" / "roads" / "road_types"
    d.mkdir(parents=True)
    (d / "00_base_roads.txt").write_bytes(b"\xef\xbb\xbfaachen_to_brabant_road = {\n\ttier = 0\n}\n"
                                          b"# a_comment_road = {\nal-qahira_to_giza_road = {\n\ttier = 0\n}\n")
    assert R.defined_road_types(tmp_path) == {"aachen_to_brabant_road", "al-qahira_to_giza_road"}
