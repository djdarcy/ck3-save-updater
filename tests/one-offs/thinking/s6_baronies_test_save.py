"""The stripped baronies, given back (the two-phase DWP's unit 5, addenda ~12:15 and ~12:25): a test save.

1.21 moved some baronies to another county, and the game's conversion handed each to its new county's holder (63 of
the 66 one-barony vassals it stripped in djdarcy's re-save of v17). This writes them back with
carry_1_21.carry_baronies, from the v17 witness into that re-save (same date, 987.10.27), so a game run can answer the
Director's correction 2: does the game's NEXT re-save keep them?
Writes a NEW file only. Run:
python -I -X utf8 tests/one-offs/thinking/s6_baronies_test_save.py <1.21 re-save> <witness 1.20> <game dir> <out>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import carry_1_21 as C  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402


def main(resave, witness, game, out):
    out = pathlib.Path(out)
    assert not out.exists(), f"{out} exists; this writes new files only"
    s = read_save(resave)
    # run 1 (11:58, MIGRATE_TEST__1.21-baronies): 60 of 63 kept, but 56 contracts dropped: government= was missing
    r = C.carry_baronies(s.gamestate, read_save(witness).gamestate, C.barony_counties(game),
                         C.defined_governments(game))
    L = C._entries(r.gamestate, "living")
    print("the carried holders' governments:", collections.Counter(
        C.gov_of_landed(r.gamestate, L[h]) for _, h, _, _ in r.carried))
    print(f"carried {len(r.carried)}, skipped {len(r.skipped)}")
    print("skipped:", collections.Counter(why for _, _, why in r.skipped))
    print("contracts:", collections.Counter(lv for *_, lv in r.carried).most_common(5))
    print("examples:", r.carried[:4])
    if r.carried:
        s.set_gamestate(r.gamestate)
        write_save(s, out)
        print(f"wrote {out.name}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
