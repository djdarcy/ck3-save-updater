"""impassable_refs: every location-like field in a save that names a province the target map makes impassable,
counted by top-level section and field (2026-10-27: the 989.1.1 crash writes through a province pointer that a
province with no barony lacks; moving the one army off 9542 did not stop it, so what else stands there?).

Usage: python -I tests/one-offs/impassable_refs.py <game dir> <save.ck3> [<save.ck3> ...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.mapdata import impassable_provinces  # noqa: E402

FIELD = re.compile(rb"[\n\t ](location|current_location|province|prev|destination|capital_province|origin|home)"
                   rb"=(\d+)")
TOP = re.compile(rb"(?m)^([A-Za-z_][\w]*)=\{?")


def main():
    game = Path(sys.argv[1])
    bad = impassable_provinces(game)
    for p in sys.argv[2:]:
        g = sf.read_save(p).gamestate
        tops = [(m.start(), m.group(1).decode()) for m in TOP.finditer(g)]
        starts = [s for s, _ in tops]
        import bisect
        c, ex = Counter(), defaultdict(list)
        for m in FIELD.finditer(g):
            if int(m.group(2)) in bad:
                i = bisect.bisect_right(starts, m.start()) - 1
                k = (tops[i][1] if i >= 0 else "?", m.group(1).decode())
                c[k] += 1
                if len(ex[k]) < 3:
                    ex[k].append(m.group(2).decode())
        print(f"== {p}")
        for k, n in c.most_common():
            print(f"  {n:6,}  {k[0]:28} {k[1]:18} e.g. {ex[k]}")


if __name__ == "__main__":
    main()
