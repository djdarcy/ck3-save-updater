"""U1 schemes PoC: does 1.8's scheme_freeze_days make 1.20 freeze every carried scheme for good?

Measured 2026-11-04: on load 1.20 gives all 1,334 carried schemes freeze_data={ frozen=yes scheme_freeze_days=0
reason="" }, and after four years of observer play the 816 still running are frozen with their progress unchanged.
Schemes the game starts itself have no freeze_data unless frozen for a reason (FREEZE_REASON_TRAVELING ...).

Hypothesis: the loader turns scheme_freeze_days (present on every 1.8 scheme, always 0) into a freeze.
Prediction (before running): with the field deleted, the carried schemes come back without freeze_data, and over about
a year of observer play some of their progress or phases change. Refuted if they are frozen again.

Writes a new save; the input is never touched. Usage: python -I poc_scheme_thaw.py <in.ck3> <out.ck3>"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

save = sf.read_save(sys.argv[1])
d = save.gamestate
s = gs.locate(d, "schemes/active")
p = gs.EditPass()
n = 0
for e in gs.iter_entries(d, *s.body):
    for c in gs.iter_children(d, *e.body):
        if c.key == b"scheme_freeze_days":
            a, b = gs.removal_span(d, c.start, c.value_end)
            p.add(gs.Edit(a, b, b"", "poc", e.key.decode()))
            n += 1
p.apply_to(save)
sf.write_save(save, sys.argv[2])
back = sf.read_save(sys.argv[2]).gamestate
print(f"deleted scheme_freeze_days from {n} schemes; left in the output: {len(re.findall(rb'scheme_freeze_days', back))}")
