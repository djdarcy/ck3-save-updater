"""Unit 4b: what the ids inside a reference save's religion/faiths/rites point at (titles? artifacts? cultures?).

Usage: python tests/one-offs/measure_unit4b_refs.py [<extracted gamestate>]   (default: the 987 reference)
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402

REF = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "private/data/extracted/ref_1_20_987_10_27/gamestate"
d = REF.read_bytes()


def v(b, k):
    h = gs.find_keys(d, b, k)
    return d[h[0].value_start:h[0].value_end].decode().strip('"') if h else None


titles = {t.key.decode(): v(t, "key") for t in gs.iter_entries(d, *gs.locate(d, "landed_titles/landed_titles").body)}
cultures = {c.key.decode(): (v(c, "culture_template") or v(c, "name")) for c in gs.iter_entries(d, *gs.locate(d, "culture_manager/cultures").body)}
faiths = list(gs.iter_entries(d, *gs.locate(d, "faiths/database").body))
rites = list(gs.iter_entries(d, *gs.locate(d, "rites/database").body))
print(f"{REF.parent.name}: {len(titles):,} titles, {len(cultures)} cultures, {len(faiths)} faiths, {len(rites)} rites")

rh = Counter(titles.get(v(f, "religious_head"), v(f, "religious_head")) for f in faiths if v(f, "religious_head") != "4294967295")
print("faith religious_head -> title key:", dict(rh))
el = []
for f in faiths:
    for k in ("active_clerical_electors", "inactive_clerical_electors"):
        h = gs.find_keys(d, f, k)
        if h and h[0].block:
            el += [titles.get(d[c.start:c.end].decode(), "?" + d[c.start:c.end].decode()) for c in gs.iter_children(d, *h[0].block.body)]
print(f"clerical electors -> title keys ({len(el)}): {el[:12]}")
orgs = Counter(v(f, "organization") for f in faiths)
print(f"faith organization ids: {len(orgs)} distinct")
om = gs.find_section(d, "organization_manager")
print("organization_manager head:\n" + d[om.start:om.start + 900].decode(errors="replace"))
rc = Counter()
for r in rites:
    h = gs.find_keys(d, r, "cultures")
    if h and h[0].block:
        for c in gs.iter_children(d, *h[0].block.body):
            rc[cultures.get(d[c.start:c.end].decode(), "?")] += 1
print("rite cultures -> culture keys:", dict(rc))
hor = Counter(v(r, "head_of_rite") == "4294967295" for r in rites)
print(f"rites with head_of_rite set: {hor[False]} / {len(rites)}")
hs = gs.locate(d, "religion/holy_sites")
sample = next(iter(gs.iter_entries(d, *hs.body)))
print("a holy site:\n" + d[sample.start:sample.end].decode(errors="replace")[:600])
bar = Counter(titles.get(v(h, "barony"), "?")[:2] for h in gs.iter_entries(d, *hs.body))
print("holy site barony -> title tier prefixes:", dict(bar))
ghw = gs.locate(d, "religion/great_holy_wars")
print(f"great_holy_wars body bytes: {ghw.close - ghw.open}; content: {d[ghw.open:ghw.open + 300]!r}")
fs = gs.find_keys(d, gs.find_section(d, "faiths"), "saints")
print(f"faiths/saints: {'present' if fs else 'absent'}; faith saints lists: "
      f"{sum(1 for f in faiths if gs.find_keys(d, f, 'saints'))}")
