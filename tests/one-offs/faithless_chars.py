"""Where do 1.8.1 characters without faith= get their faith? Test candidate inheritance sources.

Usage: python tests/one-offs/faithless_chars.py   (from the project root)
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
d = OLD.read_bytes()


def v(block, key):
    h = gs.find_keys(d, block, key)
    return d[h[0].value_start:h[0].value_end].decode().strip('"') if h else None


chars = {}
for e in gs.iter_entries(d, *gs.find_section(d, "living").body):
    chars[e.key.decode()] = {"faith": v(e, "faith"), "culture": v(e, "culture"), "house": v(e, "dynasty_house")}
dead = {}
for e in gs.iter_entries(d, *gs.find_section(d, "dead_unprunable").body):
    dead[e.key.decode()] = {"faith": v(e, "faith"), "house": v(e, "dynasty_house")}
houses = {}
for h in gs.iter_entries(d, *gs.locate(d, "dynasties/dynasty_house").body):
    houses[h.key.decode()] = {k: v(h, k) for k in ("head_of_house", "dynasty", "founder")}
dyns = {}
for x in gs.iter_entries(d, *gs.locate(d, "dynasties/dynasties").body):
    dyns[x.key.decode()] = {"head": v(x, "dynasty_head")}
print(f"living {len(chars):,}; dead_unprunable {len(dead):,}; houses {len(houses):,}; dynasties {len(dyns):,}")
print("house child keys present:", {k: sum(1 for h in houses.values() if h[k]) for k in ("head_of_house", "dynasty", "founder")})


def faith_of(cid):
    c = chars.get(cid) or dead.get(cid)
    return c["faith"] if c else None


for label, src in (("house head", lambda c: (houses.get(c["house"]) or {}).get("head_of_house")),
                   ("dynasty head", lambda c: (dyns.get((houses.get(c["house"]) or {}).get("dynasty")) or {}).get("head")),
                   ("house founder", lambda c: (houses.get(c["house"]) or {}).get("founder"))):
    agree = disagree = nofaith_src = 0
    covered = Counter()
    for cid, c in chars.items():
        s = src(c)
        sf = faith_of(s) if s else None
        if c["faith"] is not None:
            if sf is None:
                continue
            agree += sf == c["faith"]
            disagree += sf != c["faith"]
        else:
            covered["source has faith" if sf else ("source exists, no faith" if s else "no source")] += 1
    print(f"{label:13}: chars WITH faith agree {agree:,} / disagree {disagree:,};  chars WITHOUT faith -> {dict(covered)}")

print("\nheads of house: share with faith=", end=" ")
heads = {h["head_of_house"] for h in houses.values() if h["head_of_house"]}
print(f"{sum(1 for x in heads if faith_of(x)):,} of {len(heads):,}")
nf = [cid for cid, c in chars.items() if c["faith"] is None]
print(f"faithless that are heads of their house: {sum(1 for x in nf if x in heads):,} of {len(nf):,}")
