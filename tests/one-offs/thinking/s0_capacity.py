"""S0 (1), the built-state carry plan 2026-11-19__01-21-19: capacity. Per holding, the 1.20 regular buildings (every
built building except the holding's own main one) against 1.21's room: the converted save's
regular_district_slot_limit, and how many buildings one regular district holds in a fresh 1.21 game.

Read only. Run: python -I -X utf8 tests/one-offs/thinking/s0_capacity.py <1.20 save> <its 1.21 re-save> <1.21 reference>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NONE = b"4294967295"


def holdings(g):
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        x = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", x)
        if h:
            hb = x[h.end() - 1:gs.match_brace(x, h.end() - 1) + 1]
            if re.search(rb"\n\t\t\ttype=", hb):
                out[e.key] = hb
    return out


def main(old, conv, ref):
    o, c, r = (read_save(p).gamestate for p in (old, conv, ref))
    ho, hc = holdings(o), holdings(c)
    pairs = collections.Counter()
    over = 0
    for p, hb in ho.items():
        bl = re.search(rb"\bbuildings=\{", hb)
        inner = hb[bl.end():gs.match_brace(hb, bl.end() - 1)] if bl else b""
        built = re.findall(rb'\{\s*(?:disabled=yes\s*)?type="?([\w-]+)', inner)
        regular = max(0, len(built) - 1)                       # the first is the holding's main building
        lim = re.search(rb"regular_district_slot_limit=(\d+)", hc.get(p, b""))
        slots = int(lim.group(1)) if lim else 0
        pairs[(regular, slots)] += 1
    # buildings per regular district, fresh game: the districts a holding lists under districts={ }
    dl = {e.key: r[e.open:e.close] for e in gs.iter_entries(r, *gs.locate(r, "districts/database").body) if e.key}
    per = collections.Counter()
    for hb in holdings(r).values():
        ds = re.search(rb"\bdistricts=\{([^}]*)\}", hb)
        for d in (ds.group(1).split() if ds else []):
            if d == NONE:
                continue
            m = re.search(rb"buildings=\{([^}]*)\}", dl.get(d, b""))
            ids = m.group(1).split() if m else []
            per[(len([x for x in ids if x != NONE]), len(ids))] += 1
    print("1.20 regular buildings per holding vs 1.21 regular district slots (count of holdings):")
    by_slots = collections.defaultdict(collections.Counter)
    for (n, s), k in pairs.items():
        by_slots[s][n] += k
    for s in sorted(by_slots):
        tot = sum(by_slots[s].values())
        print(f"  {s} slots: {tot} holdings | regular buildings: {dict(sorted(by_slots[s].items()))}")
    print("fresh 1.21 regular districts, (buildings built, list length incl. empty slots):", dict(per.most_common(10)))
    return pairs, per


if __name__ == "__main__":
    main(*sys.argv[1:4])
