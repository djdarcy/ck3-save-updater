"""How full the game's 1.21 conversion leaves each holding's districts, against a fresh 1.21 game at the same date
(the class note 2026-11-18__21-32-48, members 1 and 7; graduated from the session's inline counts at 21:3x).

Per save: built buildings by district slot, regular district slots filled of all, and the top building keys. Then, for
resource districts, the provinces where the fresh game has a resource building and the converted save has none, by
building key: whether the gap is history-placed (a fresh game puts it there at the date) or something else.

Read only. Run: python -I -X utf8 tests/one-offs/thinking/conversion_fill.py <converted 1.21 save> <fresh 1.21 save>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NONE = b"4294967295"


def fill(g: bytes):
    """slot -> count, (filled, total) regular slots, key counts, and province -> resource building key."""
    bt = {e.key: (re.search(rb'type="?([\w-]+)', g[e.open:e.close]) or [0, b"?"])[1].decode()
          for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body) if e.key}
    dl = {e.key: g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if e.key}
    slot, keys, resource = collections.Counter(), collections.Counter(), {}
    filled = total = 0
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        x = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", x)
        if not h:
            continue
        hb = x[h.end() - 1:gs.match_brace(x, h.end() - 1) + 1]
        if not re.search(rb"\n\t\t\ttype=", hb):
            continue
        ds = re.search(rb"\bdistricts=\{([^}]*)\}", hb)
        regs = ds.group(1).split() if ds else []
        total += len(regs)
        filled += sum(r != NONE for r in regs)
        for f, d in re.findall(rb"\b(\w+_district)=(\d+)", hb) + [(b"regular_district", r) for r in regs if r != NONE]:
            m = re.search(rb"buildings=\{([^}]*)\}", dl.get(d, b""))
            for z in (m.group(1).split() if m else []):
                if z == NONE:
                    continue
                slot[f.decode()] += 1
                keys[bt.get(z, "?")] += 1
                if f == b"resource_district":
                    resource[e.key.decode()] = bt.get(z, "?")
    return slot, (filled, total), keys, resource


def main(converted, fresh):
    out = {}
    for name, p in (("converted", converted), ("fresh", fresh)):
        slot, (f, t), keys, res = fill(read_save(p).gamestate)
        out[name] = res
        print(f"== {name}: regular district slots filled {f} of {t}")
        print(f"   built buildings by slot: {dict(slot)}")
        print(f"   top keys: {keys.most_common(8)}")
    gap = collections.Counter(out["fresh"][p] for p in out["fresh"] if p not in out["converted"])
    print(f"== resource buildings a fresh game has where the converted save has none: {sum(gap.values())}")
    for k, n in gap.most_common(12):
        print(f"{n:5}  {k}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
