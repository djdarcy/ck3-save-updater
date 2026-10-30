"""company_title_keys: does each mercenary company's title carry the key x_mc_<company id>? (2026-10-30)

Running savediff's graph on real saves (PR #13 review): play6 has 289 of 640 companies whose title key is not
x_mc_<company id> (e.g. company 389 holds x_mc_390), the game's own 1.20 save 0 of 562, the 1.8.1 original 122 of 473.
This reads companies (mercenary_company_manager/mercenary_companies: title=<title id>) and title keys
(landed_titles/landed_titles: key=...) directly, and reports per save: companies, matching, off by how much, a
title that is missing or not x_mc_ at all -- so it can be seen whether the mismatch comes with the old save or from
the migration, and in which direction.

Known answer: on the game's own 1.20 save every company matches.

Usage: python -I tests/one-offs/company_title_keys.py <save.ck3> [...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

TITLE = re.compile(rb"\n\t+title=(\d+)")        # entries sit at depth 3 in these sections; the first match is depth 1
KEY = re.compile(rb'\n\t+key="?([^"\s]+)"?')


def report(path: str):
    g = read_save(path).gamestate
    keys = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        m = KEY.search(g[e.open:e.open + 400])
        if m:
            keys[i] = m.group(1).decode()
    c, examples = Counter(), {}
    for cid, e in T.entries(g, "mercenary_company_manager/mercenary_companies"):
        m = TITLE.search(g[e.open:e.close])
        if not m:
            kind = "no title field"
        else:
            k = keys.get(int(m.group(1)))
            if k is None:
                kind = "title missing"
            elif not k.startswith("x_mc_"):
                kind = f"not x_mc_ ({k[:12]})"
            else:
                n = int(k[5:]) if k[5:].isdigit() else None
                kind = "match" if n == cid else (f"off by {n - cid:+d}" if n is not None else "x_mc_ non-numeric")
        c[kind] += 1
        examples.setdefault(kind, (cid, m and int(m.group(1)), m and keys.get(int(m.group(1)))))
    total = sum(c.values())
    print(f"{Path(path).name}: {total} companies")
    for kind, n in c.most_common():
        print(f"   {n:4d}  {kind:24s} e.g. company {examples[kind][0]} -> title {examples[kind][1]} {examples[kind][2]}")


def main():
    for p in sys.argv[1:]:
        report(p)


if __name__ == "__main__":
    main()
