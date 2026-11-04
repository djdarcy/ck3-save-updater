"""culture_holders: who holds which culture, ours against the game's re-save (the culture goal's U1, part two).

Counties (`county_manager/counties`, `culture=<id>`) and characters (living, dead_unprunable; their own first-level
`culture=<id>`), each culture id turned into its template (else name) through that save's own culture_manager, so
ids that shift between saves cannot hide or fake a change. Prints how many counties and characters changed culture,
or lost it, with examples.

Usage: python -I tests/one-offs/thinking/culture_holders.py <ours.ck3> <game re-save.ck3>
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from culture_three_way import load  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402


def names(g: bytes) -> dict:
    b = gs.locate(g, "culture_manager")
    sub = g[b.body[0]:b.body[1]]
    out = {}
    for m in re.finditer(rb"\n\t\t(\d+)=\{", sub):
        end = sub.find(b"\n\t\t}", m.end())
        t = re.search(rb'(?:^|[\s{])(?:culture_template|name)=("[^"]*"|[^\s}]+)', sub[m.end():end])
        out[m.group(1)] = t.group(1).strip(b'"').decode() if t else "?"
    return out


def holders(g: bytes) -> dict:
    nm, out = names(g), {}
    b = gs.locate(g, "county_manager")
    for e in gs.iter_entries(g, *b.body):
        pass
    sub = g[b.body[0]:b.body[1]]
    for m in re.finditer(rb"\n\t\t([a-z]_[a-z0-9_]+)=\{", sub):
        end = sub.find(b"\n\t\t}", m.end())
        c = re.search(rb"(?:^|[\s{])culture=(\d+)", sub[m.end():end])
        out[("county", m.group(1).decode())] = nm.get(c.group(1), "?" + c.group(1).decode()) if c else None
    for sec in ("living", "dead_unprunable"):
        b = gs.locate(g, sec)
        for e in gs.iter_entries(g, *b.body):
            body = g[e.start:e.end]
            ind = re.match(rb"[^\n]*\n(\t+)", body)
            first = ind.group(1) if ind else b"\t\t"
            c = re.search(rb"\n" + first + rb"culture=(\d+)", body)
            out[(sec, e.key.decode() if e.key else "?")] = nm.get(c.group(1), "?" + c.group(1).decode()) if c else None
    return out


def main():
    a, b = holders(load(sys.argv[1])), holders(load(sys.argv[2]))
    for kind in ("county", "living", "dead_unprunable"):
        keys = [k for k in a if k[0] == kind and k in b]
        changed = [k for k in keys if a[k] and b[k] and a[k] != b[k]]
        lost = [k for k in keys if a[k] and not b[k]]
        gained = [k for k in keys if not a[k] and b[k]]
        print(f"{kind}: {len(keys)} in both; culture changed {len(changed)}, lost {len(lost)}, gained {len(gained)}")
        for label, ks in (("changed", changed), ("lost", lost)):
            if ks:
                print(f"   {label}: {[(k[1], a[k], b[k]) for k in ks[:5]]}")
                print(f"   {label} by culture: {Counter(a[k] for k in ks).most_common(6)}")


if __name__ == "__main__":
    main()
