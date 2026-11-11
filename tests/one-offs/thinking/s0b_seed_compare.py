"""MEASURE S0(b), step 2: did a new seed change the outcome? Each reseeded child's `sexuality=` in three saves.

Inputs: the roots list s0b_seed_copy.py printed (a text file), and the game's console saves of control A, control B and
the edited (reseeded) copy, each run in observe mode past the events' dates. Plain-text saves are read raw.
Prints per root: date, sexuality in A, B, edited; then the counts: A==B, edited==A, and roots whose event had not fired
in some arm (sexuality still none). Read-only.

Run: python -I tests/one-offs/thinking/s0b_seed_compare.py <roots.txt> <A.ck3> <B.ck3> <edited.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

roots = re.findall(r"root (\d+) date (\S+)", Path(sys.argv[1]).read_text(encoding="utf-8"))
saves = [Path(p).read_bytes() for p in sys.argv[2:5]]


def sexuality(g: bytes, cid: str) -> str:
    living = g.find(b"\nliving={")
    m = re.compile(rb"(?m)^" + cid.encode() + rb"=\{").search(g, living)
    if not m:
        return "(gone)"
    nxt = re.compile(rb"(?m)^\d+=\{").search(g, m.end())
    body = g[m.end():nxt.start() if nxt else m.end() + 20000]
    s = re.search(rb"(?m)^\tsexuality=(\w+)", body)
    return s.group(1).decode() if s else "(unset)"


same_ab = diff_e = unfired = 0
for cid, date in roots:
    a, b, e = (sexuality(g, cid) for g in saves)
    flag = "" if a == b == e else ("  <- edited differs" if a == b else "  <- A != B")
    print(f"{cid:>10} {date:<10} A={a:<12} B={b:<12} edited={e:<12}{flag}")
    same_ab += a == b
    diff_e += a == b and e != a
    unfired += "none" in (a, b, e) or "(unset)" in (a, b, e)
print(f"roots {len(roots)}: A==B {same_ab}; edited differs where A==B {diff_e}; some arm unfired/none {unfired}")
