"""U3 PoC: carry 1.8's innovation-spread marker into 1.20's field. In each culture_manager culture, rename
exposure_marker="X" to spread_marker=X (1.20 writes it unquoted) and delete exposure_type=... (1.20 has no such field);
culture_marker is kept as it is. Writes a new save; the input is never touched.

Prediction (2026-11-04, before running): the game's first-day re-save of the output keeps spread_marker on all 201
cultures, and the load's error.log loses the 206 + 201 "Unexpected token: exposure_type / exposure_marker" lines with no
new error naming spread_marker. Refuted if the re-save drops the markers again, or new errors appear.

Usage: python -I poc_spread_marker.py <in.ck3> <out.ck3>"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

save = sf.read_save(sys.argv[1])
d = save.gamestate
cm = gs.locate(d, "culture_manager/cultures")
p = gs.EditPass()
renamed = dropped = 0
for e in gs.iter_entries(d, *cm.body):
    for c in gs.iter_children(d, *e.body):
        if c.key == b"exposure_marker":
            value = d[c.value_start:c.value_end].strip(b'"')
            p.add(gs.Edit(c.start, c.value_end, b"spread_marker=" + value, "U3", e.key.decode()))
            renamed += 1
        elif c.key == b"exposure_type":
            a, b = gs.removal_span(d, c.start, c.value_end)
            p.add(gs.Edit(a, b, b"", "U3", e.key.decode()))
            dropped += 1
p.apply_to(save)
sf.write_save(save, sys.argv[2])
back = sf.read_save(sys.argv[2]).gamestate
print(f"renamed {renamed}, dropped exposure_type {dropped}; output has exposure_ {len(re.findall(rb'exposure_', back))}, "
      f"spread_marker {len(re.findall(rb'spread_marker=', back))}")
