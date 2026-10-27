"""dangling_title_vars: the character variables in a migrated save that name a title the migration removed, each
with its variable name, its owner, the old title's key (from the original save: campaign titles keep their ids),
and what R15's report says became of that title (class, successors). Answers djdarcy 2026-10-27: are these old
quests the migration breaks, and could they be remapped to the successor titles?

Usage: python -I tests/one-offs/dangling_title_vars.py <migrated.ck3> <original.ck3> <report.json>
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.lint import SectionIndex  # noqa: E402

NONE = {b"4294967295", b"18446744073709551615"}
KEY = re.compile(rb"\n\tkey=\"?([\w\-']+)")


def titles(g: bytes) -> dict[bytes, str]:
    b = SectionIndex(g).block("landed_titles/landed_titles")
    out = {}
    for e in gs.iter_entries(g, *b.body):
        m = KEY.search(g, e.open, min(e.close, e.open + 400))
        if e.key and m:
            out[e.key] = m.group(1).decode()
    return out


def main():
    new = sf.read_save(sys.argv[1]).gamestate
    old = sf.read_save(sys.argv[2]).gamestate
    table = {row["key"]: row for x in json.load(open(sys.argv[3], encoding="utf-8"))["rules"] if x["id"] == "R15"
             for row in x["extra"]["table"]}
    have, old_keys = titles(new), titles(old)
    idx = SectionIndex(new)
    lv = idx.block("living")
    rows = []
    for e in gs.iter_entries(new, *lv.body):
        body = new[e.open:e.close]
        # a variable entry: { flag="name" tick=.. data={ type=lt identity=N } } or a list item={ type=lt identity=N }
        for m in re.finditer(rb"type=lt\s+identity=(\d+)", body):
            i = m.group(1)
            if i in NONE or i in have:
                continue
            head = body[max(0, m.start() - 400):m.start()]
            flag = re.findall(rb'flag="?([\w\-.:]+)"?', head)
            lst = re.findall(rb'\n\t+name="?([\w\-.:]+)"?', head)
            rows.append({"char": e.key.decode(), "var": (flag or lst or [b"?"])[-1].decode(),
                         "title": old_keys.get(i, f"?{i.decode()}"), "id": i.decode()})
    by_var = Counter(r["var"] for r in rows)
    print(f"{len(rows)} dangling title scopes in living; by variable: {dict(by_var.most_common(20))}")
    fate = defaultdict(Counter)
    for r in rows:
        t = table.get(r["title"])
        fate[r["var"]][f"{t['class']} -> {t['successors'] or 'none'}" if t else "not in R15's table"] += 1
    for v, c in fate.items():
        print(f"  {v}:")
        for k, n in c.most_common(8):
            print(f"      {n:4}  {k}")
    for r in rows[:12]:
        print("   e.g.", r)


if __name__ == "__main__":
    main()
