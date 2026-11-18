"""F3, the static invariants of a 1.20-stamped chain built from a 1.21 reference (goal 2026-11-18__17-11-09).

Five checks the one game load (F4) must not be the first to see; each prints its count, and 0 is a pass:
1. title keys held twice;
2. field names in the output no v17 row has (titles, provinces' holdings, characters' landed_data, county records,
   domiciles: depth 1, and depth 2 inside holding and landed_data);
3. holdings with a type and no buildings list;
4. county records without development;
5. ids into databases the save lacks: title trade_market, holding *_district=, landed_data trade_routes.
Graduated from the collab's probes p17/p18 (round 3, 2026-11-18__16-49-33). Read only.
Run: python -I -X utf8 tests/one-offs/chain_invariants.py <chain output.ck3> <v17.ck3>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

KEY = re.compile(rb'\bkey="?([\w\-\']+)')


def _fields(body: bytes, inside: bytes | None = None) -> set[bytes]:
    """Field names at depth 1 of an entry, or at depth 1 of its ``inside`` block."""
    if inside is not None:
        m = re.search(rb"[\s{]" + inside + rb"=\{", body)
        if not m:
            return set()
        body = body[m.end() - 1:gs.match_brace(body, m.end() - 1) + 1]
    out, depth = set(), 0
    for m in re.finditer(rb'"(?:[^"\\]|\\.)*"|[{}]|([\w\-]+)=', body):
        t = m.group(0)
        if t == b"{":
            depth += 1
        elif t == b"}":
            depth -= 1
        elif m.group(1) and depth == 1:
            out.add(m.group(1))
    return out


SPOTS = (("landed_titles/landed_titles", None), ("provinces", b"holding"), ("living", b"landed_data"),
         ("county_manager/counties", None), ("domiciles/database", None))


def vocab(g: bytes) -> dict:
    out = {}
    for path, inside in SPOTS:
        s = set()
        try:
            blk = gs.locate(g, path)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *blk.body):
            if e.key:
                s |= _fields(g[e.open:e.close], inside)
        out[(path, inside)] = s
    return out


def main(chain, v17):
    g, v = read_save(chain).gamestate, read_save(v17).gamestate
    lt = gs.locate(g, "landed_titles/landed_titles")
    keys = collections.Counter()
    for e in gs.iter_entries(g, *lt.body):
        if e.key:
            m = KEY.search(g[e.open:min(e.close, e.open + 400)])
            if m:
                keys[m.group(1)] += 1
    dup = sum(1 for n in keys.values() if n > 1)
    vg, vv = vocab(g), vocab(v)
    extra = {f"{p}{'/' + i.decode() if i else ''}": sorted(x.decode() for x in vg.get((p, i), set()) - vv.get((p, i), set()))
             for p, i in SPOTS}
    extra = {k: x for k, x in extra.items() if x}
    no_buildings = 0
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        b = g[e.open:e.close]
        h = re.search(rb"[\s{]holding=\{", b)
        if h:
            hb = b[h.end() - 1:gs.match_brace(b, h.end() - 1) + 1]
            if re.search(rb'\btype="?\w', hb) and not re.search(rb"\bbuildings=\{", hb):
                no_buildings += 1
    cm = gs.locate(g, "county_manager/counties")
    no_dev = sum(1 for e in gs.iter_entries(g, *cm.body) if e.key and not re.search(rb"\bdevelopment=", g[e.open:e.close]))
    dangling = {"title trade_market": len(re.findall(rb"\n\t+trade_market=\d", g[lt.open:lt.close])),
                "holding *_district": len(re.findall(rb"\n\t+\w+_district=\d", g[gs.locate(g, 'provinces').open:
                                                                                   gs.locate(g, 'provinces').close])),
                "landed trade_routes": len(re.findall(rb"\n\t+trade_routes=", g))}
    print(f"1 title keys held twice: {dup}")
    print(f"2 field names no v17 row has: {sum(len(x) for x in extra.values())} {extra}")
    print(f"3 holdings with a type and no buildings list: {no_buildings}")
    print(f"4 county records without development: {no_dev}")
    print(f"5 ids into missing databases: {sum(dangling.values())} {dangling}")
    ok = not dup and not extra and not no_buildings and not no_dev and not sum(dangling.values())
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
