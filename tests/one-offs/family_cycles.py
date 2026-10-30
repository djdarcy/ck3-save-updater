"""family_cycles: does a save's kinship graph contain a cycle -- someone recorded as their own ancestor? (2026-10-28)

djdarcy: walking back to the founder of his family line in play6 hung the UI for 10+ minutes; a walk up the tree
that never ends is what a cycle in the parent links would produce. CK3 stores children, never parents: a parent is
found from every character's `family_data/child={ ... }` list (in living, dead_unprunable, characters/dead_prunable),
plus `real_father=` on the child. This builds child -> parents and looks for cycles with an iterative DFS
(colours, so each node is visited once), and reports the deepest ancestry chain found when there is none.

Known answer: a synthetic cycle (A child of B, B child of A) is found by --self-test.

Usage: python -I tests/one-offs/family_cycles.py <save.ck3> [<save.ck3> ...]
       python -I tests/one-offs/family_cycles.py --self-test
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
CHILD = re.compile(rb"\n\t+child=\{([^}]*)\}")
REAL_FATHER = re.compile(rb"\n\t+real_father=(\d+)")


def parents_of(g: bytes) -> dict[int, set[int]]:
    par: dict[int, set[int]] = defaultdict(set)
    for sec in SECTIONS:
        for i, e in T.entries(g, sec):
            body = g[e.open:e.close]
            for m in CHILD.finditer(body):
                for c in m.group(1).split():
                    if c.isdigit():
                        par[int(c)].add(i)
            rf = REAL_FATHER.search(body)
            if rf:
                par[i].add(int(rf.group(1)))
    return par


def find_cycles(par: dict[int, set[int]], limit: int = 10):
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[int, int] = defaultdict(int)
    depth: dict[int, int] = {}
    cycles = []
    for start in list(par):
        if colour[start] != WHITE:
            continue
        stack = [(start, iter(sorted(par.get(start, ()))))]
        path = [start]
        colour[start] = GREY
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                colour[node] = BLACK
                depth[node] = 1 + max((depth.get(p, 0) for p in par.get(node, ())), default=0)
                stack.pop()
                path.pop()
                continue
            if colour[nxt] == GREY:
                cyc = path[path.index(nxt):] + [nxt]
                if len(cycles) < limit:
                    cycles.append(cyc)
            elif colour[nxt] == WHITE:
                colour[nxt] = GREY
                stack.append((nxt, iter(sorted(par.get(nxt, ())))))
                path.append(nxt)
    return cycles, depth


def report(label, g):
    par = parents_of(g)
    cycles, depth = find_cycles(par)
    deepest = max(depth.items(), key=lambda kv: kv[1]) if depth else (None, 0)
    print(f"{label}: {len(par):,} characters with a parent; cycles found: {len(cycles)}"
          f"{' (first 10)' if len(cycles) >= 10 else ''}; deepest ancestry {deepest[1]} generations (from {deepest[0]})")
    for c in cycles:
        print("   cycle:", " -> parent ".join(map(str, c)))


def main():
    if sys.argv[1:] == ["--self-test"]:
        g = (b"living={\n1={\n\tfamily_data={\n\t\tchild={ 2 }\n\t}\n}\n2={\n\tfamily_data={\n\t\tchild={ 1 }\n\t}\n}\n"
             b"3={\n\tfamily_data={\n\t\tchild={ 4 }\n\t}\n}\n4={\n}\n}\n")
        cycles, _ = find_cycles(parents_of(g))
        print("self-test:", "ok" if cycles and set(cycles[0]) == {1, 2} else f"FAILED {cycles}")
        return
    for p in sys.argv[1:]:
        report(p, read_save(p).gamestate)


if __name__ == "__main__":
    main()
