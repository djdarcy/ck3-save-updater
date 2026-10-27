"""scope_refs: every stored script scope (`type=<kind> identity=<id>`) in a save, by kind and section, and how many
point at nothing (or, for a province, at one the target map makes impassable).

2026-10-27: the 989.1.1 crash was a council task's `target={ type=prov identity=9542 }`, a province 1.20 made
impassable. djdarcy: "Sounds like that's another generic case of a linter check we should have to validate all
events / actions?" This measures the general case on a save and on 1.20's own fresh save (the control) before it
becomes a check.

Usage: python -I tests/one-offs/scope_refs.py "<game dir>" <save.ck3> [<save.ck3> ...]
"""
from __future__ import annotations

import bisect
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.lint import CHAR_SECTIONS, SectionIndex  # noqa: E402
from ck3_save_migrator.mapdata import impassable_provinces  # noqa: E402

SCOPE = re.compile(rb"type=(\w+)\s+identity=(\d+)")
TOP = re.compile(rb"(?m)^([A-Za-z_]\w*)=")


def ids(g: bytes, idx: SectionIndex, path: str) -> set[bytes]:
    """Entry ids of a database, whatever their indentation (the transplant writes copied entries at column 0)."""
    b = idx.block(path)
    return {e.key for e in gs.iter_entries(g, *b.body) if e.key} if b is not None else set()


nested_ids = ids


def main():
    bad_map = impassable_provinces(Path(sys.argv[1]))
    for p in sys.argv[2:]:
        g = sf.read_save(p).gamestate
        idx = SectionIndex(g)
        known = {
            b"char": set().union(*(ids(g, idx, s) for s in CHAR_SECTIONS)),
            b"lt": ids(g, idx, "landed_titles/landed_titles"),
            b"prov": nested_ids(g, idx, "provinces"),
            b"faith": nested_ids(g, idx, "religion/faiths"),
            b"artifact": nested_ids(g, idx, "artifacts/artifacts"),
            b"dynasty": nested_ids(g, idx, "dynasties/dynasties"),
            b"house": nested_ids(g, idx, "dynasties/dynasty_house"),
            b"culture": nested_ids(g, idx, "culture_manager/cultures"),
        }
        tops = [(m.start(), m.group(1).decode()) for m in TOP.finditer(g)]
        starts = [s for s, _ in tops]
        total, dangling, imp = Counter(), Counter(), Counter()
        ex = defaultdict(list)
        for m in SCOPE.finditer(g):
            kind, i = m.group(1), m.group(2)
            if i == b"4294967295":                     # the game's "none"; 1.20 writes 1,065 in a fresh save
                continue
            sec = tops[bisect.bisect_right(starts, m.start()) - 1][1]
            total[kind.decode()] += 1
            if kind in known and known[kind] and i not in known[kind]:
                dangling[(kind.decode(), sec)] += 1
                if len(ex[(kind.decode(), sec)]) < 3:
                    ex[(kind.decode(), sec)].append(i.decode())
            if kind == b"prov" and int(i) in bad_map:
                imp[sec] += 1
        print(f"== {p}")
        print("  scopes by kind:", dict(total.most_common(12)))
        print("  dangling (kind, section):")
        for k, n in dangling.most_common(20):
            print(f"    {n:6,}  {k[0]:9} {k[1]:30} e.g. {ex[k]}")
        print("  provinces the map makes impassable, by section:", dict(imp))


if __name__ == "__main__":
    main()
