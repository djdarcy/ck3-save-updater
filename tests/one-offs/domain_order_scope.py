"""domain_order_scope: which characters does the v0.3.5 domain-order fix change, and why? (2026-10-30, Unit C1)

The fix (`transplant._primary_first`, applied at transplant.py ~1502) puts a ruler's highest-tier title first in his
domain -- the first domain entry is the primary title -- but only for characters whose domain the transplant edits
(the seam's promotions and R15's hand-back), and never when the first title has no tier letter (a runtime x_ title).
The director (ruling b, pending djdarcy): measure its scope before djdarcy rules.

Predictions, written before running: (P1) every character whose domain ORDER differs between the founding save and the
output also had its domain SET changed (titles added or dropped by the seam or R15); none reordered without a set
change. (P2) Beidh 50822's domain is untouched and still starts with x_x_762.

Compares, per character id present in both saves, the domain as title KEYS (ids differ between saves; keys do not),
and classifies: unchanged / set changed, first title kept / set changed, first title changed (the fix or the change
itself put another title first) / same set, reordered (would contradict P1).

Usage: python -I tests/one-offs/domain_order_scope.py <original.ck3> <output.ck3> [--player 50822]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DOMAIN = re.compile(rb"\n\t\tdomain=\{([^}]*)\}")
KEY = re.compile(rb'\n\t+key="?([^"\s]+)"?')
RANK = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5, "h": 6}


def domains(g: bytes):
    keys = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        m = KEY.search(g[e.open:e.open + 400])
        if m:
            keys[i] = m.group(1).decode()
    out = {}
    for i, e in T.entries(g, "living"):
        m = DOMAIN.search(g[e.open:e.close])
        if m:
            out[i] = [keys.get(int(x), f"#{x}") for x in m.group(1).split()]
    return out


def main():
    a = sys.argv[1:]
    player = int(a[a.index("--player") + 1]) if "--player" in a else 50822
    o, n = domains(read_save(a[0]).gamestate), domains(read_save(a[1]).gamestate)
    c, rows = Counter(), []
    for cid in sorted(set(o) & set(n)):
        do, dn = o[cid], n[cid]
        if do == dn:
            c["unchanged"] += 1
            continue
        if not do or not dn:
            c["domain emptied" if not dn else "domain gained (was empty)"] += 1
            continue
        same_set = set(do) == set(dn)
        first_changed = do[0] != dn[0]
        kind = ("same set, reordered" if same_set else
                "set changed, first title changed" if first_changed else "set changed, first title kept")
        c[kind] += 1
        if first_changed or same_set:
            added = [k for k in dn if k not in do]
            dropped = [k for k in do if k not in dn]
            moved_up = dn[0] in do[1:] or RANK.get(dn[0][:1], 0) > RANK.get(do[0][:1], 0)
            why = ("MOVED UP by the fix: a barony was first, the promoted county now first (seam promotion)"
                   if moved_up and do[0][:1] == "b" and dn[0][:1] == "c" else
                   "MOVED UP by the fix: a higher title now first" if moved_up else
                   "replaced in place: the first title's key changed at the same tier (a 1.20 successor)"
                   if dn[0] not in do and do[0] not in dn and dn[0][:1] == do[0][:1] else "other")
            rows.append((cid, do[0], dn[0], len(do), len(dn), added[:3], dropped[:3], kind, why))
    only_o, only_n = set(o) - set(n), set(n) - set(o)
    print(f"characters with a domain: original {len(o):,}, output {len(n):,}; in both {len(set(o) & set(n)):,}; "
          f"only original {len(only_o):,}, only output {len(only_n):,}")
    for k, v in c.most_common():
        print(f"   {v:6,}  {k}")
    print("\ncharacters whose first title changed (or same set reordered):")
    whys = Counter(r[8] for r in rows)
    print("   by reason:", dict(whys))
    for r in rows[:40]:
        print(f"   {r[0]}: first {r[1]} -> {r[2]}  ({r[3]} -> {r[4]} titles; +{r[5]} -{r[6]})  [{r[7]}; {r[8]}]")
    print(f"\nplayer {player}: original {o.get(player, ['--'])[:4]}  output {n.get(player, ['--'])[:4]}  "
          f"unchanged: {o.get(player) == n.get(player)}")
    print("P1 (no reorder without a set change):", "holds" if c["same set, reordered"] == 0 else "FAILS")


if __name__ == "__main__":
    main()
