"""landless_army_owners: characters with no domain who own map units or command armies (2026-10-27: is the 989.1.1
crash an army whose owner the hand-back left landless?). Usage: python -I tests/one-offs/landless_army_owners.py <save.ck3>..."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.lint import SectionIndex, _val, _DOMAIN, _ENTRY_COL0  # noqa: E402

for p in sys.argv[1:]:
    g = sf.read_save(p).gamestate
    idx = SectionIndex(g)
    lv = idx.block("living")
    landed = set()
    for m in _ENTRY_COL0.finditer(g, lv.open, lv.close):
        end = g.find(b"\n}", m.end(), lv.close)
        d = _DOMAIN.search(g, m.end(), end if end > 0 else lv.close)
        if d and d.group(1).split():
            landed.add(m.group(1))
    living = {m.group(1) for m in _ENTRY_COL0.finditer(g, lv.open, lv.close)}
    ub = idx.block("units")
    rows = []
    for e in gs.iter_entries(g, *ub.body):
        t = g[e.open:e.close]
        o = _val(t, b"owner")
        if o is not None and o in living and o not in landed:
            rows.append((e.key.decode(), o.decode(), (_val(t, b"location") or b"-").decode(), (_val(t, b"army") or b"-").decode()))
    print(f"== {p}: {len(rows)} units owned by landless characters")
    for r in rows[:30]:
        print("   unit %s owner %s location %s army %s" % r)
