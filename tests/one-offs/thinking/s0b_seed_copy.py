"""MEASURE S0(b), step 1: a copy where every queued child_personality.4000 event before a date gets a new seed.

Goal 2026-11-09__01-48-55 (the save editor), S0(b): "does a changed seed in a queued triggered_event change its
outcome". child_personality.4000 (game/events/education_and_childhood/child_personality_events.txt:8838) has a
weighted random_list choosing a child's sexuality and fires a follow-up that sets it, so the outcome is the root's
`sexuality=` in a later save.

Writes <out> (a MIGRATE_TEST__ name) through savefile.write_save, each chosen block's `seed=N` replaced by
`seed=(N * 7 + 12345) % 2**31` (same digit count is not needed: the writer re-serialises), and prints the roots
changed so the compare step can read their sexuality in each arm. Refuses if no event matched.

PREDICTION, written before the runs (three arms in observe mode, ~a month each: control A, control B, edited):
  - control A == control B for every root (the game is repeatable from the same save and seeds);
  - edited differs from the controls for some roots, about a third (the list is weighted towards heterosexual),
    and only for roots whose event was reseeded -- then the queued seed decides the roll, and reroll is honest.
  If control A != control B, the game's own randomness is not repeatable and this design cannot tell; say so.

Run: python -I tests/one-offs/thinking/s0b_seed_copy.py <in.ck3> <out.ck3> <last date, e.g. 987.11.27>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

src, out, last = Path(sys.argv[1]), Path(sys.argv[2]), tuple(int(x) for x in sys.argv[3].split("."))
if not out.name.startswith("MIGRATE_TEST__"):
    sys.exit("refused: the output must be a MIGRATE_TEST__ copy")
s = read_save(src)
g = s.gamestate
parts, pos, roots = [], 0, []
for m in re.finditer(rb"(?m)^triggered_event=\{", g):
    end = g.find(b"\n}", m.end()) + 2
    blk = g[m.start():end]
    if not re.search(rb'event="?child_personality\.4000\b', blk):
        continue
    d = tuple(int(x) for x in re.search(rb"(?m)^\tdate=([\d.]+)", blk).group(1).split(b"."))
    if d > last:
        continue
    sm = re.search(rb"seed=(-?\d+)", blk)
    old = int(sm.group(1))
    new = (old * 7 + 12345) % 2**31
    root = re.search(rb"root=\{[^}]*identity=(\d+)", blk).group(1).decode()
    roots.append((root, ".".join(map(str, d)), old, new))
    a, b = m.start() + sm.start(1), m.start() + sm.end(1)
    parts += [g[pos:a], str(new).encode()]
    pos = b
if not roots:
    sys.exit("refused: no child_personality.4000 event before that date")
parts.append(g[pos:])
s.set_gamestate(b"".join(parts))
write_save(s, out)
print(f"wrote {out}: {len(roots)} events reseeded")
for r in roots:
    print("  root", r[0], "date", r[1], "seed", r[2], "->", r[3])
