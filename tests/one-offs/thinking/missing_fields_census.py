"""MEASURE (after finding F25): which entries lack, or leave empty, a field the game's own entries of that kind carry?
Read-only.

djdarcy, 2026-11-16: "What I'm concerned about is that there are OTHER fields similar to that one that we haven't
migrated properly." F25's shape: the carried custom faith was the only one of 104 faiths without `faith_type`, a field
1.20 added, and the game's own re-save wrote it as `faith_type=""`.

Since 0.5.19 this is a thin wrapper over savediff's `field_coverage` / `coverage_gaps` (the shared helper the lint check
also uses). For every database of the save (a section's entries, or one of its children's, with at least 20
entries), the fields that at least THRESHOLD of the witness's entries carry filled, and that our entries lack or leave
empty. The witness is the reference save's entries of the same kind when --reference is given (so a majority gap,
which no sibling comparison can see, is found), otherwise the save's own entries (the census as first written).

KNOWN ANSWERS (each checked when written, S1 of the carried-fields goal):
- on the game's re-save of an update made before 0.5.18 (`MIGRATE_TEST__s0a_control_resaved.ck3`), with the
  reference, faiths/database reports `faith_type` EMPTY in entry 103;
- on the reference itself, against itself, `religion` is no gap (it is on every faith, written on the same line as
  `faith_type`, which the old line-start reader missed).

Run: python -I tests/one-offs/thinking/missing_fields_census.py <save.ck3> [--reference <ref.ck3>] [--threshold 0.97]
     [--only <path,...>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator._vendor.savediff import keys as K  # noqa: E402
from ck3_save_migrator._vendor.savediff import text as T  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402


def gamestate(path: str) -> bytes:
    data = Path(path).read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


ap = argparse.ArgumentParser()
ap.add_argument("save")
ap.add_argument("--reference")
ap.add_argument("--threshold", type=float, default=0.97)
ap.add_argument("--only", help="comma-separated database paths, e.g. faiths/database,rites/database")
a = ap.parse_args()

g = gamestate(a.save)
gi = T.SectionIndex(g)
r = gamestate(a.reference) if a.reference else None
ri = T.SectionIndex(r) if r is not None else None
paths = a.only.split(",") if a.only else K.database_paths(g, gi)
witness_name = "the reference" if r is not None else "the save's own entries"
print(f"threshold {a.threshold}; witness: {witness_name}")
pairs = 0
for p in paths:
    ours = K.field_coverage(g, gi, p)
    wit = K.field_coverage(r, ri, p) if r is not None else ours
    if r is not None and not wit["entries"]:
        print(f"  {p:<44} nothing to compare with (the reference has no entries here)")
        continue
    for row in K.coverage_gaps(ours, wit, a.threshold):
        pairs += 1
        print(f"  {p:<44} {row['field']:<30} witness {row['witness_share']:.3f}  missing {row['missing']:>6}  "
              f"empty {row['empty']:>5} of {row['entries']:<6} e.g. missing {row['missing_examples'][:4]} "
              f"empty {row['empty_examples'][:4]}")
print(f"{pairs} (database, field) pairs over {len(paths)} databases")
