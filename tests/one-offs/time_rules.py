"""Time each migration rule in-process on a real save, to find a slow or stuck one.

Usage: python tests/one-offs/time_rules.py <save.ck3> [reference.ck3] [rule ids, comma list]   (from the project root)
Runs the rules in registry order on one in-memory copy, printing each rule's wall time and
counts as it finishes (flushes per rule, so a stuck rule is the last name printed). Writes nothing.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator.rules import RuleContext, select  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
save = read_save(sys.argv[1])
ref = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else None
spec = sys.argv[3] if len(sys.argv) > 3 else "all"
ctx = RuleContext(game_dir=Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game"), reference=ref,
                  wos_shape="faith")
for rule in select(spec):
    print(f"-> {rule.id} {rule.name} ...", flush=True)
    t0 = time.time()
    r = rule.run(save, ctx)
    note = r.extra.get("skipped", "")
    print(f"   {rule.id} {time.time() - t0:7.1f}s  matched {r.matched:,} edited {r.edited:,} {note}", flush=True)
