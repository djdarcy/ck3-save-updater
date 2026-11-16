"""MEASURE (acknowledge-child failed in the game): where does a save record a child's father?

djdarcy loaded MIGRATE_TEST__ack_honest.ck3 (2026-11-15): Gabran's wild_oat trait was gone, but the game did not
show Bruide as his father. The edit had added Gabran to Bruide's family_data child={ } list only. So the father must
also live somewhere else. This prints every place a known child's id appears in the save, with the top-level section
and the line, so the second record can be found.

KNOWN CASE: Conchenn 78307, whose father the game shows as Bruide 64975.

Run: python -I tests/one-offs/thinking/legitimize_where_is_father.py <save.ck3> <child id> [<father id>]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

g = read_save(Path(sys.argv[1])).gamestate
cid = sys.argv[2].encode()
father = sys.argv[3].encode() if len(sys.argv) > 3 else None
tops = [(b.start, b.end, b.key.decode()) for b in gs.iter_entries(g, 0, len(g)) if b.key]


def section(p: int) -> str:
    for a, z, k in tops:
        if a <= p < z:
            return k
    return "?"


where = Counter()
for m in re.finditer(rb"(?<![\w.])" + cid + rb"(?![\w.])", g):
    p = m.start()
    ls = g.rfind(b"\n", 0, p) + 1
    le = g.find(b"\n", p)
    line = g[ls:le].decode("utf-8", "replace").strip()
    key = re.sub(r"\d+", "N", line)[:60]
    where[(section(p), key)] += 1
print(f"occurrences of {cid.decode()}: {sum(where.values())}")
for (sec, key), n in sorted(where.items(), key=lambda kv: -kv[1]):
    print(f"  {n:>4}  [{sec}]  {key}")
if father:
    print(f"\nlines holding both {cid.decode()} and {father.decode()}:")
    for m in re.finditer(rb"(?m)^[^\n]*(?<![\w.])" + cid + rb"(?![\w.])[^\n]*$", g):
        if re.search(rb"(?<![\w.])" + father + rb"(?![\w.])", m.group(0)):
            print(f"  [{section(m.start())}] {m.group(0).decode('utf-8', 'replace').strip()[:150]}")
