"""Unit 2, the third expectation (design addendum 07:40): after the transplanted save has run a few in-game months,
do the engine's new objects stay clear of the transplanted slots, and do the transplanted ids survive?

EARLIER is the save as transplanted (arm A); LATER is a save the game wrote after running (an autosave). Per space
the transplanted ids are those whose slot index is at or above the base the translator used, i.e. above the
original save's maximum index (given as --base space=N, or derived from ORIGINAL).

Prints per space: transplanted ids in EARLIER, how many survive in LATER with the same id, how many are gone,
new ids in LATER and where their slots fall (fresh above everything, reused, or ON A TRANSPLANTED SLOT -- the
failure the check exists for), with examples in hex.

Usage: python -I tests/one-offs/poc_newborn_check.py <original migrated save> <earlier.ck3> <later.ck3>
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

SPACES = ["character", "title", "house", "dynasty", "council_task", "vassal_contract", "coat_of_arms",
          "regiment", "artifact", "memory", "culture"]


def h(i):
    return f"0x{i:08X}(g{i >> 24},i{i & T.LOW})"


def gamestate(path: str) -> bytes:
    """A normal save through savefile; a plain-text save (header kind 00, what -debug_mode autosaves write) is
    the header line followed by the gamestate text."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def main():
    O = gamestate(sys.argv[1])
    A = gamestate(sys.argv[2])
    B = gamestate(sys.argv[3])
    print(f"original {Path(sys.argv[1]).name}\nearlier  {Path(sys.argv[2]).name}\nlater    {Path(sys.argv[3]).name}")
    failures = 0
    for sp in SPACES:
        o, a, b = T.space_ids(O, sp), T.space_ids(A, sp), T.space_ids(B, sp)
        base = max((i & T.LOW for i in o), default=-1) + 1
        trans = {i for i in a if (i & T.LOW) >= base}
        trans_slots = {i & T.LOW for i in trans}
        top = max((i & T.LOW for i in a), default=-1)
        new = sorted(i for i in b if i not in a)
        on_trans = [i for i in new if (i & T.LOW) in trans_slots]
        fresh = [i for i in new if (i & T.LOW) > top]
        between = [i for i in new if base <= (i & T.LOW) <= top and (i & T.LOW) not in trans_slots]
        below = [i for i in new if (i & T.LOW) < base]
        survive = len(trans & b)
        failures += len(on_trans)
        print(f"\n== {sp}: base {base:,}; transplanted {len(trans):,}, surviving with the same id {survive:,}, "
              f"gone {len(trans - b):,}")
        print(f"   new in later {len(new):,}: fresh above all {len(fresh):,}; in a gap between transplanted slots "
              f"{len(between):,}; below base (the campaign's own free slots) {len(below):,}; "
              f"ON A TRANSPLANTED SLOT {len(on_trans):,}")
        print(f"   new top bytes {dict(Counter(i >> 24 for i in new).most_common(6))}")
        for label, xs in (("fresh", fresh), ("gap", between), ("below", below), ("ON TRANSPLANTED", on_trans)):
            if xs:
                print(f"   {label} e.g. {[h(i) for i in xs[:4]]}")
        if trans - b:
            print(f"   gone e.g. {[h(i) for i in sorted(trans - b)[:4]]}")
    print(f"\nnew objects on a transplanted slot: {failures}  ->  {'PASS' if failures == 0 else 'FAIL'}")


if __name__ == "__main__":
    main()
