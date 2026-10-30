"""family_breadth: how many descendants do a save's founders have? (2026-10-28)

family_cycles.py found no cycle in play6 (depth 44 generations, against the 1.20 reference's 43), so the hang when
walking to the family founder is not a loop. A family-tree view also lays out descendants, and a campaign since 867
can give one founder a very large tree. This counts, for every character, the distinct descendants reachable through
`family_data/child` (memoised over the DAG), and prints the largest, with name, house and birth year.

Known answer: --self-test (1 -> 2, 3; 2 -> 4; 3 -> 4: character 1 has 3 distinct descendants).

Usage: python -I tests/one-offs/family_breadth.py <save.ck3> [...] [--top N]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
CHILD = re.compile(rb"\n\t+child=\{([^}]*)\}")
NAME = re.compile(rb'\n\tfirst_name="([^"]*)"')
HOUSE = re.compile(rb"\n\tdynasty_house=(\d+)")
BIRTH = re.compile(rb"\n\tbirth=(\d+)")


def graph(g: bytes):
    kids, info = {}, {}
    for sec in SECTIONS:
        for i, e in T.entries(g, sec):
            body = g[e.open:e.close]
            ks = [int(c) for m in CHILD.finditer(body) for c in m.group(1).split() if c.isdigit()]
            kids[i] = ks
            head = body[:2000]
            n, h, b = NAME.search(head), HOUSE.search(head), BIRTH.search(head)
            info[i] = (n.group(1).decode(errors="replace") if n else "?", h.group(1).decode() if h else "-",
                       b.group(1).decode() if b else "?")
    return kids, info


def descendant_counts(kids):
    """Distinct descendants per node, by bitset-free set union bottom-up (iterative post-order)."""
    memo: dict[int, frozenset] = {}
    for root in kids:
        if root in memo:
            continue
        stack = [(root, False)]
        while stack:
            n, done = stack.pop()
            if n in memo:
                continue
            if done:
                s = set()
                for c in kids.get(n, ()):
                    s.add(c)
                    s |= memo.get(c, frozenset())
                memo[n] = frozenset(s)
                continue
            stack.append((n, True))
            stack.extend((c, False) for c in kids.get(n, ()) if c not in memo)
    return {n: len(s) for n, s in memo.items()}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    top = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--top=")), 6)
    if "--self-test" in sys.argv:
        c = descendant_counts({1: [2, 3], 2: [4], 3: [4], 4: []})
        print("self-test:", "ok" if c[1] == 3 else f"FAILED {c}")
        return
    for p in args:
        kids, info = graph(read_save(p).gamestate)
        counts = descendant_counts(kids)
        best = sorted(counts.items(), key=lambda kv: -kv[1])[:top]
        print(f"{p}: {len(kids):,} characters; largest descendant trees:")
        for i, n in best:
            print(f"   {n:7,}  {i} {info[i][0]} (house {info[i][1]}, born {info[i][2]})")


if __name__ == "__main__":
    main()
