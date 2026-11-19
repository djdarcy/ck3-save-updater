"""C11 (test plan 2026-11-18__20-40-31, addendum 21:25): the 169 copied holdings whose main building after the game's
load differs from the 1.21 reference's own. Lists each difference as (reference -> chain's 1.20 write -> re-save),
so it shows whether our write or the game's conversion moved it.

Read only. Run: python -I -X utf8 tests/one-offs/thinking/c11_main_building_pairs.py <original> <chain> <re-save> <1.21 ref>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ck3_save_migrator.savefile import read_save  # noqa: E402
from f4_round_trip import holdings, main_building  # noqa: E402


def chain_main(hb):
    """The main building the chain wrote: the first typed entry of the holding's 1.20 buildings list."""
    m = re.search(rb"\bbuildings=\{\s*\{\s*type=\"?([\w-]+)", hb)
    return m.group(1) if m else None


def main(orig, chain, resave, ref):
    o, c, s, r = (read_save(p).gamestate for p in (orig, chain, resave, ref))
    ho, hc, hs, hr = holdings(o), holdings(c), holdings(s), holdings(r)
    typ = lambda hb: (re.search(rb'\btype="?(\w+)', hb) or [None, None])[1]
    cps = [p for p in hs if p not in ho and p in hr and typ(hr[p]) is not None]
    cs_, cr_ = {}, {}
    pairs, where = collections.Counter(), collections.Counter()
    for p in cps:
        a, b = main_building(s, hs[p], cs_), main_building(r, hr[p], cr_)
        if a == b:
            continue
        w = chain_main(hc[p]) if p in hc else None
        pairs[(b, w, a)] += 1
        where["our write already differed" if w != b else "the game's conversion changed it"] += 1
    print(f"copied holdings compared: {len(cps)} | differing: {sum(pairs.values())} | {dict(where)}")
    for (b, w, a), n in pairs.most_common(25):
        dec = lambda x: x.decode() if x else None
        print(f"{n:4}  reference {dec(b)}  ->  chain wrote {dec(w)}  ->  re-save {dec(a)}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
