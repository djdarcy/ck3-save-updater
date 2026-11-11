"""MEASURE S0(a), step 1: make the set-sex test copy -- one character's `female=yes` removed, nothing else.

Goal 2026-11-09__01-48-55 (the save editor), S0(a): "what the game recomputes on load when only female=yes changes".
The founding case is Conchenn nic Bruide, character 78307 (finding 2026-11-09__01-52-22).

Writes `<out>` (a MIGRATE_TEST__ name in the save games folder) through savefile.write_save (never in place, atomic,
verified). Refuses unless exactly one `\\tfemale=yes` line sits in the character's own entry, and checks the result
differs from the input by exactly that line (len and a diff of the gamestates).

Run: python -I tests/one-offs/thinking/s0a_set_sex_copy.py <in.ck3> <out.ck3> <character id>

PREDICTION, written before the game runs (the measurement's question is what the game does with it):
  1. The game loads the copy without a crash and the re-save keeps 78307 male (no female=yes).
  2. Her DNA string is unchanged by the game (it stores genes, not a sex); her portrait reads as a boy
     (sex-specific gene templates are chosen at draw time) -- the re-save's dna equals the input's.
  3. The game does NOT rewrite anything else of hers on load; differences between control and edited re-saves are
     limited to her entry and things computed from sex at the next yearly/monthly tick (e.g. a title's heir
     list under male-preference succession, betrothal validity). At 7 she holds no title, so heir lists that name
     her may reorder; that reordering is the game's own and needs no edit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

src, out, cid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
if not out.name.startswith("MIGRATE_TEST__"):
    sys.exit("refused: the output must be a MIGRATE_TEST__ copy")
s = read_save(src)
g = s.gamestate
e = {str(k): v for k, v in T.entries(g, "living")}.get(cid)
if e is None:
    sys.exit(f"refused: {cid} is not a living character")
body = g[e.open:e.close]
lines = [m for m in re.finditer(rb"(?m)^\tfemale=yes\r?\n", body)]
if len(lines) != 1:
    sys.exit(f"refused: {len(lines)} female=yes lines in {cid}'s entry, expected 1")
m = lines[0]
start, end = e.open + m.start(), e.open + m.end()
new = g[:start] + g[end:]
s.set_gamestate(new)
res = write_save(s, out)
back = read_save(out).gamestate
assert len(g) - len(back) == end - start and back == new, "the written gamestate is not the input minus one line"
print(f"wrote {out} ({out.stat().st_size:,} bytes): removed {g[start:end]!r} at gamestate offset {start:,}; "
      f"verified: {getattr(res, 'verified', '?')}")
