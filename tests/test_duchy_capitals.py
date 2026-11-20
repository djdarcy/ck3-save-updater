"""R45: the witness's duchy-capital buildings into 1.21 duchy-capital districts (goal 2026-11-19__22-43-27, S3).

CONSEQUENCE: 8 (data) -- the game's 1.21 conversion of djdarcy's 1.20 campaign dropped all 9 duchy-capital buildings
(march, jousting lists, blacksmiths, royal forest, tax assessor). A wrong write puts a duchy-capital district where the
game would never allow one (it keeps illegal states silently); a missing one loses what the player built.

The concept: written only where the province may hold a duchy-capital district (its barony is the duchy's capital
barony AND the county's holder holds the duchy) and every gate the save answers holds; the rest named; a second run
changes nothing. These run on the founding campaign's own saves, skipped where absent.
"""
import os
from dataclasses import replace
from pathlib import Path

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import host_rules as H
from ck3_save_migrator.district_lint import Facts, province_facts, stage_two_facts

SAVES = Path(os.environ.get("USERPROFILE", "~")) / "Documents/Paradox Interactive/Crusader Kings III/save games"
CAND, V17 = SAVES / "MIGRATE_TEST__1.21-phase2-update6__v19-candidate.ck3", SAVES / "MIGRATE_TEST__v17.ck3"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
pytestmark = pytest.mark.skipif(not (CAND.exists() and V17.exists() and GAME.is_dir()),
                                reason="needs the v19 candidate, the v17 witness and the 1.21 game")


@pytest.fixture(scope="module")
def setup():
    from ck3_save_migrator.savefile import read_save
    H.load.cache_clear()
    host = H.load(str(GAME))
    g, w = read_save(CAND).gamestate, read_save(V17).gamestate
    return host, g, w, stage_two_facts(g, str(GAME), province_facts(g, str(GAME)))


def test_on_the_founding_campaign_seven_are_written_the_two_tax_assessors_named_and_a_second_run_writes_none(setup):
    host, g, w, facts = setup
    r = C.carry_duchy_capitals(g, host, w, facts)
    assert sorted((p, k, d) for p, k, d, _, _ in r.written) == [
        ("1114", "royal_forest_01", "ducal_residence_district"), ("1129", "royal_forest_01", "ducal_residence_district"),
        ("2508", "royal_forest_01", "ducal_residence_district"), ("476", "blacksmiths_01", "military_duchy_capital_district"),
        ("482", "march_01", "military_duchy_capital_district"), ("490", "jousting_lists_01", "military_duchy_capital_district"),
        ("5642", "march_01", "military_duchy_capital_district")]
    assert sorted(p for p, _, _ in r.named) == ["1362", "1381"]
    assert r.gamestate.count(b"duchy_capital_district=") == g.count(b"duchy_capital_district=") + 7
    again = C.carry_duchy_capitals(r.gamestate, host, w, stage_two_facts(r.gamestate, str(GAME),
                                                                         province_facts(r.gamestate, str(GAME))))
    assert again.written == []


def test_a_province_that_may_not_hold_a_duchy_capital_district_is_never_written(setup):
    host, g, w, facts = setup
    no = dict(facts)
    no["482"] = Facts(replace(facts["482"].place, duchy_capital=False), facts["482"].size_level)
    unknown = dict(facts)
    unknown["482"] = Facts(replace(facts["482"].place, duchy_capital=None), facts["482"].size_level)
    for f in (no, unknown):
        r = C.carry_duchy_capitals(g, host, w, f)
        assert "482" not in {p for p, *_ in r.written} and "482" in {p for p, _, _ in r.named}


def test_the_duchy_capital_fact_needs_both_the_flag_and_the_county_holder_holding_the_duchy(setup):
    _, g, _, facts = setup
    # all nine of v17's duchy-capital provinces qualify; b_roma (2575) lost its flag in the map change (F4)
    assert all(facts[p].place.duchy_capital for p in ("476", "482", "490", "5642", "1114", "1129", "2508", "1362", "1381"))
    assert facts["2575"].place.duchy_capital is False
    # the holder half: Lancaster's barony is d_lancaster's capital barony, but c_lancashire's holder does not hold the
    # duchy (one of 175 such on v19); red-green 2026-11-20: a mutant skipping the holder check survived without this
    assert facts["1639"].place.duchy_capital is False


def test_phase_one_reads_the_1_20_save_itself_and_writes_the_same_seven(setup):
    # S3 phase one (R48): before the game converts it, the 1.20 save is its own witness. Its facts come in 1.20's shapes
    # -- buildings inside the holding, culture on the province, quoted innovation keys (unread until 2026-11-20, when
    # every 1.20 culture came out with none discovered)
    host, _, w, _ = setup
    f20 = stage_two_facts(w, str(GAME), province_facts(w, str(GAME), capitals="game"))
    p = f20["476"].place
    assert p.main_building == "castle_01" and "blacksmiths_01" in p.buildings and len(p.innovations) > 5
    r = C.carry_duchy_capitals(w, host, w, f20)
    assert sorted(x for x, *_ in r.written) == ["1114", "1129", "2508", "476", "482", "490", "5642"]
    assert sorted(x for x, _, _ in r.named) == ["1362", "1381"]
    assert b"districts={" in r.gamestate[r.gamestate.rfind(b"\ndistricts={"):]   # the database a 1.20 save lacked
    again = C.carry_duchy_capitals(r.gamestate, host, r.gamestate,
                                   stage_two_facts(r.gamestate, str(GAME), province_facts(r.gamestate, str(GAME),
                                                                                          capitals="game")))
    assert again.written == []
