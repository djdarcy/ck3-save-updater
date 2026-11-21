"""R47: the innovations new in 1.21 that the game's conversion never gives a culture (goal 2026-11-19__22-43-27, S1).

CONSEQUENCE: 8 (data) -- the game's 1.21 conversion of djdarcy's 1.20 campaign left 18 of 1.21's 131 innovations off
all 284 cultures, and two years of play added none: no culture could research prospecting, coppicing, heavy plow,
monasticism and the rest, or the buildings they gate. Written undiscovered into a copy of the converted save, they
were researched in play (678 culture entries in progress after two years; the same span on the unrepaired save: 0).

The concept: add only what the fresh 1.21 game lists and this save lists for no culture; undiscovered, except where
the fresh game's culture of the same template starts with it AND this culture has reached the innovation's era; never
touch an innovation the save already lists; a second run changes nothing.
"""
import os
from pathlib import Path

import pytest

from ck3_save_migrator import carry_1_21 as C

ERAS = {"innovation_old": "culture_era_tribal", "innovation_new_early": "culture_era_early_medieval",
        "innovation_new_high": "culture_era_high_medieval"}


def culture(cid, template, eras_done, innovations):
    era_rows = "".join(f" {{\n\t\t\t\t\ttype={e}\n\t\t\t\t\tprogress=100\n\t\t\t\t}}\n" for e in eras_done)
    inn_rows = "".join(f" {{\n\t\t\t\t\ttype={i}\n" + (f"\t\t\t\t\tprogress={p}\n" if p else "") + "\t\t\t\t}\n"
                       for i, p in innovations)
    return (f"\t\t{cid}={{\n\t\t\tculture_template=\"{template}\"\n\t\t\tculture_era_data={{{era_rows} }}\n"
            f"\t\t\tculture_innovation={{{inn_rows} }}\n\t\t\tname=\"{template}\"\n\t\t}}\n")


def save(*cultures):
    return ("date=987.10.27\nculture_manager={\n\tcultures={\n" + "".join(cultures) + "\t}\n}\n").encode()


# the fresh 1.21 game: lists all three; the "han" template starts with innovation_new_early discovered
REF = save(culture(0, "han", ["culture_era_tribal", "culture_era_early_medieval"],
                   [("innovation_old", 100), ("innovation_new_early", 100), ("innovation_new_high", None)]),
           culture(1, "akan", ["culture_era_tribal"],
                   [("innovation_old", None), ("innovation_new_early", None), ("innovation_new_high", None)]))


def listed(g):
    return {e.key.decode(): inn for e, _, _, inn, _ in C._cultures(g)}


def test_missing_innovations_are_added_to_every_culture_undiscovered_unless_the_evidence_says_otherwise():
    conv = save(culture(5, "han", ["culture_era_tribal", "culture_era_early_medieval"], [("innovation_old", 100)]),
                culture(6, "han", ["culture_era_tribal"], [("innovation_old", None)]),        # era not reached
                # era reached, so only its template's evidence keeps it undiscovered (red-green 2026-11-20: with
                # the tribal era alone, a mutant ignoring the template survived)
                culture(7, "akan", ["culture_era_tribal", "culture_era_early_medieval"], [("innovation_old", None)]))
    r = C.insert_missing_innovations(conv, REF, ERAS)
    got = listed(r.gamestate)
    assert r.missing == ["innovation_new_early", "innovation_new_high"] and r.cultures == 3
    assert got["5"]["innovation_new_early"] == 100          # same template has it discovered, era reached
    assert got["6"]["innovation_new_early"] is None          # same template, but early medieval not reached
    assert got["7"]["innovation_new_early"] is None          # its template starts without it
    assert all(got[c]["innovation_new_high"] is None for c in "567")
    assert r.discovered == [("5", "han", "innovation_new_early")]
    assert got["5"]["innovation_old"] == 100                 # what was there is untouched


def test_an_entry_a_culture_has_is_never_altered_a_gap_on_some_cultures_is_filled_and_a_second_run_changes_nothing():
    # the conversion's second kind of gap: an innovation some cultures list (5: in progress) and others do not (6)
    conv = save(culture(5, "han", ["culture_era_tribal", "culture_era_early_medieval"],
                        [("innovation_old", 100), ("innovation_new_high", 40)]),
                culture(6, "akan", ["culture_era_tribal"], [("innovation_old", None)]))
    r = C.insert_missing_innovations(conv, REF, ERAS)
    got = listed(r.gamestate)
    assert r.missing == ["innovation_new_early", "innovation_new_high"] and r.added == 3
    assert got["5"]["innovation_new_high"] == 40              # its progress kept, no second entry
    assert got["6"]["innovation_new_high"] is None            # the gap filled, undiscovered
    assert r.gamestate.count(b"type=innovation_new_high") == 2
    again = C.insert_missing_innovations(r.gamestate, REF, ERAS)
    assert again.missing == [] and again.added == 0 and again.gamestate == r.gamestate


V19 = Path(os.environ.get("USERPROFILE", "~")) / "Documents/Paradox Interactive/Crusader Kings III/save games/MIGRATE_TEST__1.21-phase2-update6__v19.ck3"
REF_SAVE = Path(__file__).resolve().parents[1] / "private/data/originals/reference-1.21/ref_1_21_987_10_27.ck3"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")


@pytest.mark.skipif(not (V19.exists() and REF_SAVE.exists() and GAME.is_dir()), reason="needs the v19 golden, the 1.21 reference and the game")
def test_on_the_founding_campaign_every_culture_lists_what_a_fresh_game_lists():
    from ck3_save_migrator.savefile import read_save
    ref = read_save(REF_SAVE).gamestate
    r = C.insert_missing_innovations(read_save(V19).gamestate, ref, C.innovation_eras(GAME))
    fresh = set().union(*(inn for *_, inn, _ in C._cultures(ref)))
    # 18 missing on all cultures, 7 on some; 67 discovered by the evidence rule (prosperity_01 29, pattern_welding 26,
    # monasticism 7, heavy_plow 3, craft_ordinances 1, prosperity_02 1), none of which v17 listed for that culture
    # 27 since 2026-11-20: the two Legacy of Persia innovations (prefixed keys) the reader missed before, on 229 cultures
    assert len(r.missing) == 27 and r.cultures == 284 and r.added == 6302 and len(r.discovered) == 67
    assert {"fp3_innovation_fritware", "fp3_innovation_mural_sextant"} <= set(r.missing)
    assert all(fresh <= set(inn) for *_, inn, _ in C._cultures(r.gamestate))


def test_g1_a_key_the_reference_lists_on_some_cultures_only_is_never_spread():
    """djdarcy 2026-11-20: "I don't want innovations that are truly meant to be limited to cultures / religious groups /
    regions / etc to be applied universally." Fresh games list every innovation on every culture (108 in ref-1.20, 133
    in ref-1.21, none partial); a reference that lists a key on some cultures only is evidence it is limited, so it is
    left alone and reported."""
    ref = save(culture(0, "han", ["culture_era_tribal"], [("innovation_old", None), ("innovation_regional", None)]),
               culture(1, "akan", ["culture_era_tribal"], [("innovation_old", None)]))
    conv = save(culture(5, "akan", ["culture_era_tribal"], []), culture(6, "han", ["culture_era_tribal"], []))
    r = C.insert_missing_innovations(conv, ref, ERAS)
    got = listed(r.gamestate)
    assert r.missing == ["innovation_old"] and r.partial == ["innovation_regional"]
    assert all("innovation_regional" not in got[c] for c in "56")       # not even on the han culture
    assert all(got[c] == {"innovation_old": None} for c in "56")


OURS_1_20 = Path(os.environ.get("USERPROFILE", "~")) / "Documents/Paradox Interactive/Crusader Kings III/save games/_Beidh_of_Ireland_987_10_27_Bruide-issues.ck3"
REF_1_20 = Path(__file__).resolve().parents[1] / "private/data/originals/reference-1.20/ref_1_20_987_10_27.ck3"


@pytest.mark.skipif(not (OURS_1_20.exists() and REF_1_20.exists() and GAME.is_dir()), reason="needs djdarcy's 1.20 re-save, the 1.20 reference and the game")
def test_r49_on_the_founding_campaign_in_1_20_fills_the_three_innovations_1_8_never_listed():
    """ours-1.20 (djdarcy's 1.20 re-save of our output, read only) lacked Pole Vault on 228 cultures and Legacy of
    Persia's two on 229; R49's core gives every culture all 108, writes none discovered (no fresh 1.20 culture starts
    with them), and a second run changes nothing."""
    from ck3_save_migrator.savefile import read_save
    ref = read_save(REF_1_20).gamestate
    eras = C.innovation_eras(GAME)
    r = C.insert_missing_innovations(read_save(OURS_1_20).gamestate, ref, eras)
    assert r.missing == ["fp3_innovation_fritware", "fp3_innovation_mural_sextant", "innovation_pole_vault"]
    assert r.added == 228 + 229 + 229 and r.discovered == [] and r.partial == []
    fresh = set.intersection(*(set(inn) for *_, inn, span in C._cultures(ref) if span is not None))
    assert len(fresh) == 108 and all(fresh <= set(inn) for *_, inn, span in C._cultures(r.gamestate) if span is not None)
    again = C.insert_missing_innovations(r.gamestate, ref, eras)
    assert again.added == 0 and again.gamestate == r.gamestate
