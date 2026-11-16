"""MEASURE (carried-fields S3): what does lint's carried-fields check report on real saves, and what does it cost?

Before wiring it into every update, the allow-list and the threshold must rest on what it actually says. Read-only.
KNOWN ANSWER: on a pre-0.5.18 output (MIGRATE_TEST__play14.ck3) faith 103's faith_type is reported; on the 0.5.18
output it is not; on the reference against itself nothing is reported (check L2).

Run: python -I tests/one-offs/thinking/fields_lint_measure.py <save.ck3> [--reference <ref.ck3>]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402


def gamestate(path: str) -> bytes:
    data = Path(path).read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


ap = argparse.ArgumentParser()
ap.add_argument("save")
ap.add_argument("--reference")
a = ap.parse_args()
g = gamestate(a.save)
r = gamestate(a.reference) if a.reference else None
t = time.time()
rep = L.LintReport()
L.check_reference_fields(g, rep, r)
print(f"{time.time() - t:.1f} s; witness: {L.field_witness(g, r)[0]}")
for f in rep.findings:
    print(f"[{f.severity}] {f.check}: {f.count}")
    for ex in f.examples:
        print(f"    {ex[:230]}")
for s in rep.skipped:
    print(f"[skipped] {s}")
