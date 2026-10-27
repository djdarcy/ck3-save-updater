"""primary_title_rank: rulers whose primary title (the first entry of their domain) is of a lower tier than the
highest title they hold.

2026-10-27, from the decompiled ck3 1.20.1.2 (private/code/ck3/1.20.1.2/functions/ck3+0x28b43fa.c, 0x28b92ae.c,
0x23135a0.c): when the game makes a ruler independent, it sets the primary title's liege to none, then gives each
other non-barony title the primary title as liege when the primary outranks it, else the PRIMARY's liege. The setter
refuses to move a barony off its county. So a count whose primary title is his barony gets his county made its own
liege, and the "which kingdom" routine (0x23186e0) loops forever on it: the 987.11.8 freeze (Liber, 70790,
domain={ 3884 16745 }: b_kuzeytorg first).

Usage: python -I tests/one-offs/primary_title_rank.py <save.ck3> [<save.ck3> ...] [--examples N]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import shape_diff as P  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402

TIER = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5, "h": 5}


def main():
    n_ex = int(sys.argv[sys.argv.index("--examples") + 1]) if "--examples" in sys.argv else 8
    for path in [a for a in sys.argv[1:] if not a.startswith("--") and not a.isdigit()]:
        g = P.load(path)
        key = {}
        for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
            if e.key and e.key.isdigit():
                m = re.search(rb'\n\tkey="?([^"\s]+)', g[e.start:min(e.end, e.start + 300)])
                if m:
                    key[e.key.decode()] = m.group(1).decode()
        bad, rulers, kinds = [], 0, Counter()
        for e in gs.iter_entries(g, *gs.locate(g, "living").body):
            body = g[e.start:e.end]
            d = re.search(rb"\n\t\tdomain=\{([^}]*)\}", body)
            if not d or not d.group(1).split():
                continue
            ids = [x.decode() for x in d.group(1).split()]
            tiers = [TIER.get(key.get(i, "?")[0], 0) for i in ids]
            rulers += 1
            if tiers[0] < max(tiers):
                bad.append((e.key.decode(), [key.get(i, i) for i in ids]))
                kinds[f"primary tier {tiers[0]} < highest {max(tiers)}"] += 1
        print(f"== {Path(path).name}: rulers {rulers}; primary title outranked by another held title: {len(bad)} {dict(kinds)}")
        for cid, titles in bad[:n_ex]:
            print(f"     {cid}: domain {titles[:6]}")


if __name__ == "__main__":
    main()
