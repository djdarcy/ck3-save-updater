"""MEASURE (after finding F25): which entries lack a field that almost all their siblings have? Read-only.

djdarcy, 2026-11-16: "What I'm concerned about is that there are OTHER fields similar to that one that we haven't
migrated properly." F25's shape: the carried custom faith was the only one of 104 faiths without `faith_type`, a field
1.20 added. This looks for the same shape in every database of a save: for each set of numbered entries (a section's
own entries, or its `database={ }`, one level down), the depth-1 fields present in at least THRESHOLD of the entries,
and the entries that lack each one.

Run it on the game's own re-save of an updated save: whatever the game fills in by itself on load is present there,
so what is still missing is what the update must supply. Kind 00 (a console save) and kind 02 are both read.

KNOWN ANSWER: on a save made by an update before 0.5.18, faiths must report `faith_type` missing from one entry
(the custom faith).

Run: python -I tests/one-offs/thinking/missing_fields_census.py <save.ck3> [threshold, default 0.97]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402

data = Path(sys.argv[1]).read_bytes()
THRESHOLD = float(sys.argv[2]) if len(sys.argv) > 2 else 0.97
h = parse_header(data[:64])
g = data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate
FIELD = re.compile(rb"(?m)^\t*(\w+)=")


def fields(e) -> set:
    """The keys at depth 1 of an entry: lines one tab deeper than its own key line."""
    body = g[e.open + 1:e.close]
    line_start = g.rfind(b"\n", 0, e.start) + 1
    depth = e.start - line_start + 1
    want = b"\n" + b"\t" * depth
    out = set()
    for m in re.finditer(rb"\n(\t+)(\w+)=", body):
        if len(m.group(1)) == depth:
            out.add(m.group(2).decode())
    return out


def numbered(start: int, end: int):
    return [e for e in gs.iter_entries(g, start, end) if e.key and e.key.isdigit()]


report = []
for top in gs.iter_entries(g, 0, len(g)):
    if not top.key:
        continue
    groups = [(top.key.decode(), numbered(top.open + 1, top.close))]
    for child in gs.iter_entries(g, top.open + 1, top.close):
        if child.key and not child.key.isdigit():
            groups.append((f"{top.key.decode()}/{child.key.decode()}", numbered(child.open + 1, child.close)))
    for name, ents in groups:
        if len(ents) < 20:
            continue
        sets = [(e, fields(e)) for e in ents]
        freq = Counter(f for _, s in sets for f in s)
        for f, n in freq.items():
            if THRESHOLD <= n / len(ents) < 1.0:
                lacking = [e.key.decode() for e, s in sets if f not in s]
                report.append((name, f, len(ents), len(lacking), lacking[:6]))
print(f"threshold {THRESHOLD}: fields in at least that share of a database's entries, and the entries without them")
for name, f, total, n, ex in sorted(report, key=lambda r: (r[0], -r[3])):
    print(f"  {name:<38} {f:<34} missing in {n:>5} of {total:<6} e.g. {ex}")
print(f"{len(report)} (database, field) pairs")
