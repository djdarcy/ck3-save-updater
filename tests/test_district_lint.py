"""The district legality lint judges a save by the game's own rules, with the fresh 1.21 game as its control.

CONSEQUENCE: 9 (data) -- the game keeps illegal district states silently (2026-11-17), so this lint is the only thing
that tells a carried district from a broken one. The built-state carry's review (2026-11-19 13:35) found the S2 proof
of concept's Rome had passed "the re-save kept it" while breaking the tier rule three times.

Real saves only (private/data is gitignored; set CK3_REAL_SAVES=1). The control: a fresh 1.21 game must come out nearly
clean, with only the exceptions the game's own start makes (measured 13:5x: 25 dependent districts without urban
housing, 8 villages-with-urban-housing holdings, 21 urban housing outside a capital or city, 14 buildings). A reading
error in the gates shows up there first: the first reading of county goods gave 1,926 false breaches.
"""
import os
from pathlib import Path

import pytest

GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")
REF_121 = Path(__file__).resolve().parents[1] / "private" / "data" / "originals" / "reference-1.21" / \
    "ref_1_21_987_10_27.ck3"
ROME = Path(os.environ.get("USERPROFILE", "")) / "Documents" / "Paradox Interactive" / "Crusader Kings III" / \
    "save games" / "MIGRATE_TEST__s2-rome-poc-resaved.ck3"
REAL = os.environ.get("CK3_REAL_SAVES") == "1" and GAME.is_dir() and REF_121.exists()


def _lint(path):
    from ck3_save_migrator import district_lint as L
    from ck3_save_migrator import host_rules as H
    from ck3_save_migrator.savefile import read_save
    g = read_save(path).gamestate
    return L.lint(g, H.load(str(GAME)), L.province_facts(g, str(GAME)))


@pytest.mark.skipif(not REAL, reason="set CK3_REAL_SAVES=1 with the game and the 1.21 reference on disk")
def test_a_fresh_1_21_game_is_nearly_clean():
    r = _lint(REF_121)
    k = r.by_kind()
    assert r.districts > 7000                                      # it read the districts at all
    assert k["building illegal here"] <= 20                        # was 1,926 with the wrong county goods
    assert k["district without its prerequisite"] <= 30
    assert k["villages and urban housing together"] <= 10
    assert k["district disabled here"] <= 30
    assert "over the slot limit" not in k                          # the size formula held for every holding


@pytest.mark.skipif(not REAL, reason="set CK3_REAL_SAVES=1 with the game and the 1.21 reference on disk")
def test_the_games_county_capitals_are_each_countys_first_barony():
    # phase one judges a 1.20 save by 1.21's capitals (the map moved some: province 3204's walls were disabled after
    # the conversion, 2026-11-19 15:3x); the rule "first-listed barony" must equal what a fresh 1.21 game marks
    import re
    from ck3_save_migrator import district_lint as L
    from ck3_save_migrator import gamestate as gs
    from ck3_save_migrator.savefile import read_save
    g = read_save(REF_121).gamestate
    marked = set()
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        b = g[e.open:e.close]
        if re.search(rb"(?<!\w)capital_barony=yes", b):
            marked.add(re.search(rb'\bkey="?([^\s"]+)', b).group(1).decode())
    assert L.county_capital_baronies(str(GAME)) == marked and len(marked) > 3000


@pytest.mark.skipif(not (REAL and ROME.exists()), reason="the S2 Rome proof of concept's re-save is not on disk")
def test_the_rome_proof_of_concept_is_flagged_for_its_tiers():
    r = _lint(ROME)
    rome = [d for p, k, d in r.breaches if p == "2575" and k == "building illegal here"]
    assert len(rome) == 3 and all("needs district level" in d for d in rome)
