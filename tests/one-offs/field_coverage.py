"""field_coverage: which fields does the target game write on (nearly) every entry of a kind that a migrated save's
entries lack? (2026-10-30)

nickname_text was found by a player noticing garbled names: 1.20 writes it on every character, a 1.8.1 save has
none, and the migrator never added it. djdarcy: "we should be looking at the linter to see what else in the same
vain as the missing titles might similarly be borked". This is the census that finds the whole class at once.

For each database section given (entries keyed by id or key), it counts, per depth-1 field key, the share of entries
carrying it -- in the reference (a save the target game wrote) and in the migrated save, the latter split into
entries that exist in the reference by id (transplanted from it) and the rest (carried from the old save). A field
the reference carries on >= --min share of entries while the carried entries carry it on < --max share is a
candidate. Field presence is all it reads: values are not compared.

Known answer: on characters, nickname_text is a candidate (reference 100%, carried 0%).

Usage: python -I tests/one-offs/field_coverage.py <reference.ck3> <migrated.ck3> [--min 0.9] [--max 0.5]
                                                 [--section living ...]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DEFAULT_SECTIONS = ["living", "dead_unprunable", "characters/dead_prunable", "landed_titles/landed_titles",
                    "dynasties/dynasty_house", "dynasties/dynasties", "artifacts/artifacts", "religion/faiths",
                    "culture_manager/cultures", "provinces", "mercenary_company_manager/mercenary_companies",
                    "holy_orders/holy_orders", "character_memory_manager/database", "coat_of_arms/coat_of_arms_manager_database"]
FIELD = re.compile(rb"\n\t([A-Za-z_][A-Za-z0-9_]*)=")


def coverage(g: bytes, section: str, ids_from: set | None = None):
    """-> (entries, Counter of field -> entries carrying it, set of ids). With ids_from, only entries whose id is
    (or is not, by the caller) in that set are counted: returns two tallies."""
    inside, outside = Counter(), Counter()
    n_in = n_out = 0
    ids = set()
    for i, e in T.entries(g, section):
        ids.add(i)
        body = g[e.open:e.close]
        keys = set(FIELD.findall(body))
        if ids_from is not None and i in ids_from:
            n_in += 1
            inside.update(keys)
        else:
            n_out += 1
            outside.update(keys)
    return ids, (n_in, inside), (n_out, outside)


def main():
    a = sys.argv[1:]
    ref, mig = read_save(a[0]).gamestate, read_save(a[1]).gamestate
    lo = float(a[a.index("--min") + 1]) if "--min" in a else 0.9
    hi = float(a[a.index("--max") + 1]) if "--max" in a else 0.5
    sections = [a[i + 1] for i, x in enumerate(a) if x == "--section"] or DEFAULT_SECTIONS
    known = False
    for sec in sections:
        try:
            rids, _, (rn, rc) = coverage(ref, sec)
            _, (tn, tc), (cn, cc) = coverage(mig, sec, ids_from=rids)
        except Exception as ex:  # a section absent or shaped differently in one save: say so, never skip silently
            print(f"{sec}: not read ({type(ex).__name__}: {ex})")
            continue
        if rn == 0:
            print(f"{sec}: no entries in the reference")
            continue
        print(f"{sec}: reference {rn:,} entries; migrated {tn:,} with a reference id + {cn:,} others")
        rows = []
        for k, c in rc.items():
            rs = c / rn
            cs = cc.get(k, 0) / cn if cn else 0.0
            if rs >= lo and cs < hi:
                rows.append((rs, cs, k.decode(), tc.get(k, 0) / tn if tn else None))
        for rs, cs, k, ts in sorted(rows, key=lambda r: (-r[0], r[1])):
            t = f"{ts:5.1%}" if ts is not None else "  -  "
            print(f"   {k:32s} reference {rs:6.1%}  carried {cs:6.1%}  (reference-id entries {t})")
            if sec == "living" and k == "nickname_text":
                known = True
    print("known answer (living: nickname_text flagged):", "ok" if known else "NOT FOUND -- check the method")


if __name__ == "__main__":
    main()
