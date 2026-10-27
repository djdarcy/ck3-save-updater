"""pointer_cycles: every pointer field that points into its own table, found without naming it, checked for cycles.

2026-10-27: two of the campaign's engine stops are loops that end only when something along the way holds -- a liege
chain that reaches a top (the 8 November 987 freeze: a county that became its own liege), and an army split that
must move fewer armies than it holds (the 20 March 989 stop). The first kind is a cycle in a parent pointer, and a
save can be checked for it without knowing which fields are parents: a field whose values are mostly ids of the
same table IS a parent pointer, and a cycle in it is an engine loop with no exit.

A table is a top-level block, or the named child of one, whose entries are keyed by number. The living and dead
character tables share one id space and are checked as one. A field is any `name=<digits>` in a record (at any
depth, named by its innermost key); it is a pointer of its table when >= 60% of at least 20 values are ids there.

Usage: python -I tests/one-offs/pointer_cycles.py <save.ck3> [examples]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

FIELD = re.compile(rb"(?<![\w.])([a-z_][a-z0-9_]*)=(\d+)(?=\s)")
CHARACTERS = ("living", "dead_unprunable", "characters/dead_prunable")


def load(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":         # a plain-text save (-debug_mode autosave)
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def tables(g: bytes) -> dict[str, list[gs.Block]]:
    out = defaultdict(list)
    for name, blocks in (gs._top_index(g) or {}).items():
        for b in blocks:
            kids = list(gs.iter_entries(g, *b.body))
            if kids and sum(1 for k in kids if k.key and k.key.isdigit()) >= max(2, len(kids) // 2):
                out[name.decode()].append(b)
            elif kids and len(kids) <= 64 and all(k.key and not k.key.isdigit() for k in kids):
                for k in kids:
                    sub = list(gs.iter_entries(g, *k.body))
                    if sub and sum(1 for s in sub if s.key and s.key.isdigit()) >= max(2, len(sub) // 2):
                        out[f"{name.decode()}/{k.key.decode()}"].append(k)
    merged = defaultdict(list)
    for name, bl in out.items():
        merged["characters" if name in CHARACTERS else name].extend(bl)
    return merged


def cycles(edges: dict[int, int]) -> list[list[int]]:
    """Every cycle of a functional graph (each node has at most one successor)."""
    state, found = {}, []
    for start in edges:
        if start in state:
            continue
        path, pos, n = [], {}, start
        while n in edges and n not in state:
            state[n] = 1
            pos[n] = len(path)
            path.append(n)
            n = edges[n]
        if n in pos:                                   # closed on this walk
            found.append(path[pos[n]:])
        for p in path:
            state[p] = 2
    return found


def main():
    save = sys.argv[1]
    nex = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    g = load(save)
    total_fields = 0
    for name, blocks in sorted(tables(g).items()):
        recs = {}
        for b in blocks:
            for e in gs.iter_entries(g, *b.body):
                if e.key and e.key.isdigit():
                    recs[int(e.key)] = (e.open, e.close)
        vals = defaultdict(dict)                       # field -> {record id: first value}
        for rid, (a, z) in recs.items():
            for m in FIELD.finditer(g, a + 1, z):
                f = m.group(1).decode()
                vals[f].setdefault(rid, int(m.group(2)))
        for f, edges in sorted(vals.items()):
            inside = sum(1 for v in edges.values() if v in recs)
            if len(edges) < 20 or inside < 0.6 * len(edges):
                continue
            total_fields += 1
            own = {k: v for k, v in edges.items() if v in recs}
            cyc = cycles(own)
            selfs = [c for c in cyc if len(c) == 1]
            longer = [c for c in cyc if len(c) > 1]
            flag = "  <-- " if cyc else ""
            ex = ""
            if cyc:
                ex = "   e.g. " + "; ".join(" -> ".join(map(str, c + [c[0]])) for c in (selfs + longer)[:nex])
            print(f"{name:<40} {f:<28} {len(own):>8,} pointers  {len(selfs):>4} self  {len(longer):>4} longer{flag}{ex}")
    print(f"{save}: {total_fields} pointer fields checked")


if __name__ == "__main__":
    main()
