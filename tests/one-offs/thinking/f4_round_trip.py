"""F4's round-trip (the Director, 2026-11-18 17:10): a row copied from the 1.21 reference, shaped to 1.20, converted by
the game on load, should come back as the reference's own row. Where it does, the down-shaper's derivations carried and
invented nothing; where it does not, that field is the finding.

Copied rows are those the original 1.8.1 save lacks: county records by key, provinces by id with a holding. Compared:
a county's prosperity; a province's holding type and its main building (holding_district -> district -> first building).
Read only. Run: python -I -X utf8 tests/one-offs/thinking/f4_round_trip.py <original> <re-save> <1.21 reference>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def counties(g):
    return {e.key: g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "county_manager/counties").body) if e.key}


def holdings(g):
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        b = g[e.open:e.close]
        h = re.search(rb"[\s{]holding=\{", b)
        if e.key and h:
            out[e.key] = b[h.end() - 1:gs.match_brace(b, h.end() - 1) + 1]
    return out


def main_building(g, hb, cache):
    if "d" not in cache:
        cache["d"] = {e.key: g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body)}
        cache["b"] = {e.key: g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)}
    m = re.search(rb"\bholding_district=(\d+)", hb)
    d = cache["d"].get(m.group(1)) if m else None
    bl = re.search(rb"\bbuildings=\{\s*(\d+)", d) if d else None
    b = cache["b"].get(bl.group(1)) if bl else None
    t = re.search(rb'\btype="?([\w-]+)', b) if b else None
    return t.group(1) if t else None


def main(orig, resave, ref):
    o, s, r = (read_save(p).gamestate for p in (orig, resave, ref))
    co, cs, cr = counties(o), counties(s), counties(r)
    pr = lambda b: (re.search(rb"\bprosperity=([\d.]+)", b) or [None, None])[1]
    copied = [k for k in cs if k not in co and k in cr]
    c = collections.Counter("same" if pr(cs[k]) == pr(cr[k]) else "differs" for k in copied)
    print(f"copied county records: {len(copied)} | prosperity vs the reference: {dict(c)}")
    ho, hs, hr = holdings(o), holdings(s), holdings(r)
    typ = lambda hb: (re.search(rb'\btype="?(\w+)', hb) or [None, None])[1]
    cps = [p for p in hs if p not in ho and p in hr]
    ct = collections.Counter("same" if typ(hs[p]) == typ(hr[p]) else "differs" for p in cps)
    cs_, cr_ = {}, {}
    cm = collections.Counter()
    for p in cps:
        if typ(hr[p]) is None:
            continue
        a, b = main_building(s, hs[p], cs_), main_building(r, hr[p], cr_)
        cm["same" if a == b else ("missing in re-save" if a is None else "differs")] += 1
    print(f"copied provinces: {len(cps)} | holding type vs the reference: {dict(ct)} | main building: {dict(cm)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
