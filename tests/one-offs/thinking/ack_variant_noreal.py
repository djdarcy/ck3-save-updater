"""POC (acknowledge-child): does the game take Bruide as Gabran's father once `real_father` is gone?

After `acknowledge-child 16838491 64975 honest`, the game showed Gabran's real father and no father (djdarcy,
2026-11-15 and 2026-11-16, loaded twice). Compared field by field with his half-sister Conchenn (whose father the game
shows as Bruide), the only parentage difference left is Gabran's `real_father=57756` (ack_compare_siblings.py).

This writes a copy of the edited save with that one line removed, so Gabran's parentage is exactly Conchenn's.

PREDICTION, written before the load: the game shows Bruide as Gabran's father. If it does not, `real_father` is not
the cause, and the father link is decided somewhere the save comparison did not reach.

Run: python -I tests/one-offs/thinking/ack_variant_noreal.py <edited.ck3> <out MIGRATE_TEST__*.ck3>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.characters import CharacterIndex  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

src, out = Path(sys.argv[1]), Path(sys.argv[2])
if not out.name.startswith("MIGRATE_TEST__"):
    sys.exit("refused: the output must be a MIGRATE_TEST__ copy")
s = read_save(src)
g = s.gamestate
e = CharacterIndex(g).living[16838491]
line = b"\t\treal_father=57756\n"
at = g.find(line, e.open, e.close)
if at < 0 or g.count(line, e.open, e.close) != 1:
    sys.exit("refused: Gabran's entry does not hold exactly one real_father=57756 line")
s.set_gamestate(g[:at] + g[at + len(line):])
write_save(s, out)
print(f"wrote {out}: removed {line!r} at {at}")
