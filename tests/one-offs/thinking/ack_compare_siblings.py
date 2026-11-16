"""MEASURE (acknowledge-child, after the failed load): how does Gabran's entry differ from his half-sister Conchenn's?

djdarcy, 2026-11-16: "How about we just focus on getting Bruide setup as the father of Gabran ... We can just look at
Aelfweard's other children and how those children like Conchenn have that configured?" The game shows Conchenn's
father as Bruide 64975; after the edit it does not show Gabran's. Both are now in both parents' child lists. This
prints each one's top-level fields (depth 1 of the entry) side by side, with the nested family_data fields, and
whether each parent's id appears anywhere inside the child's own entry.

Run: python -I tests/one-offs/thinking/ack_compare_siblings.py <save.ck3> [<child a> <child b>]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.characters import CharacterIndex  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

g = read_save(Path(sys.argv[1])).gamestate
a, b = (int(x) for x in sys.argv[2:4]) if len(sys.argv) > 3 else (78307, 16838491)
ix = CharacterIndex(g)


def fields(cid: int) -> dict:
    e = ix.living.get(cid) or ix.dead.get(cid)
    body = g[e.open:e.close]
    out = {}
    for m in re.finditer(rb"(?m)^\t(\w+)=([^\n]*)", body):
        out[m.group(1).decode()] = m.group(2).decode("utf-8", "replace")[:50]
    fam = re.search(rb"(?m)^\tfamily_data=\{\n(.*?)^\t\}", body, re.S)
    for m in re.finditer(rb"(?m)^\t\t(\w+)=([^\n]*)", fam.group(1) if fam else b""):
        out["family_data." + m.group(1).decode()] = m.group(2).decode()[:50]
    for parent in (64975, 65171, 57756):
        out[f"(mentions {parent})"] = str(len(re.findall(rb"(?<![\w.])" + str(parent).encode() + rb"(?![\w.])", body)))
    return out


fa, fb = fields(a), fields(b)
print(f"{'field':<34} {a:<28} {b}")
for k in sorted(set(fa) | set(fb)):
    va, vb = fa.get(k, "-"), fb.get(k, "-")
    flag = "" if (k in fa) == (k in fb) else "   <-- only one has it"
    print(f"{k:<34} {va[:26]:<28} {vb[:30]}{flag}")
