"""MEASURE S0(c), step 1: a copy with one artifact duplicated under a new id and given to its owner.

Goal 2026-11-09__01-48-55 (the save editor), S0(c): "artifacts (id allocation, the minimal entry that loads and
survives a re-save)". Static finding F14: ids are (generation << 24) | slot, slots 0..4701 all used, no counter in the
save; so the new id is the next slot, generation 0.

The copy: artifact <src id>'s entry duplicated under <new id> in artifacts={ artifacts={ } }, and <new id> appended
to its owner's `inventory={ ... artifacts={ ... } }` (inside the owner's alive_data). Nothing else. Writes <out> (a
MIGRATE_TEST__ name) through savefile.write_save.

PREDICTION, written before the game runs: the game loads it and its own re-save keeps the artifact under <new id>
(owner and inventory unchanged), because the id is a free slot at generation 0; if the game renumbers or drops it,
the allocation rule is the game's and an edit must leave the id to it.

Run: python -I tests/one-offs/thinking/s0c_artifact_copy.py <in.ck3> <out.ck3> <src id> <new id>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

src, out, aid, new = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4]
if not out.name.startswith("MIGRATE_TEST__"):
    sys.exit("refused: the output must be a MIGRATE_TEST__ copy")
s = read_save(src)
g = s.gamestate
db = gs.locate(g, "artifacts/artifacts")
m = re.compile(rb"(?m)^\t\t" + aid.encode() + rb"=\{").search(g, db.open, db.close)
if not m:
    sys.exit(f"refused: no artifact {aid}")
if re.compile(rb"(?m)^\t\t" + new.encode() + rb"=\{").search(g, db.open, db.close):
    sys.exit(f"refused: id {new} is taken")
end = g.find(b"\n\t\t}", m.end()) + len(b"\n\t\t}")
entry = g[m.start():end]
owner = re.search(rb"(?m)^\t\t\towner=(\d+)", entry).group(1)
copy = b"\n\t\t" + new.encode() + entry[len(b"\t\t") + len(aid):]
# the owner's inventory: `owner=<id>` inside inventory={ ... artifacts={ ... } }
inv = re.compile(rb"inventory=\{\s*owner=" + owner + rb"\b").search(g)
if not inv:
    sys.exit(f"refused: no inventory for owner {owner.decode()}")
lst = re.compile(rb"artifacts=\{([^}]*)\}").search(g, inv.end())
ins_inv = lst.end(1)
new_g = g[:end] + copy + g[end:ins_inv] + b" " + new.encode() + b" " + g[ins_inv:] if end < ins_inv else \
    g[:ins_inv] + b" " + new.encode() + b" " + g[ins_inv:end] + copy + g[end:]
s.set_gamestate(new_g)
write_save(s, out)
print(f"wrote {out}: artifact {aid} copied as {new} (owner {owner.decode()}), entry {len(entry)} bytes; "
      f"inventory list now: {new_g[lst.start() + (len(copy) if end < ins_inv else 0):][:120]!r}")
