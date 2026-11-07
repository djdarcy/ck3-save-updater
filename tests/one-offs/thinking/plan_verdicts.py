"""For the verdict cache (design 2026-11-06__21-10-17): one plan of the founding save, as `status` makes it with no
--rules, printing every step's verdict, each detector's time, and the totals by verdict. The verdicts cached as
"done"/"unknown" stay re-checked under the design, so their time is the cache's floor.
Usage: python -I plan_verdicts.py"""
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import plan as PL  # noqa: E402

D = ROOT / "private" / "data"
t0 = time.perf_counter()
p = PL.plan_update(D / "originals/save games/Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3",
                   game_dir=r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game",
                   reference=str(D / "originals/reference-1.20/ref_1_20_987_10_27.ck3"),
                   old_game_dir=str(D / "versions/1.8.2/game"), rules_spec=None, detect=True,
                   portrait_mods=["2220098919", "2507209632", "2996881191"], use_record=False)
wall = time.perf_counter() - t0
by = defaultdict(list)
for s in p.steps:
    kind = ("needed" if s.reason.startswith("needed") else "done" if s.reason.startswith("done") else
            "unknown" if s.reason.startswith("unknown") else "not judged")
    t = p.detect_timings.get(s.id)
    by[kind].append((s.id, t))
    print(f"{s.id:4} {'runs' if s.will_run else 'skip':4} {kind:10} {f'{t:6.1f}s' if t is not None else '      '}  "
          f"{s.reason[:90]}")
print(f"\nwall {wall:.1f}s; detectors {sum(p.detect_timings.values()):.1f}s over {len(p.detect_timings)} steps")
for k, v in by.items():
    print(f"  {k:10} {len(v):3} steps, {sum(t or 0 for _, t in v):6.1f}s")
print(f"  total     {sum(len(v) for v in by.values()):3} steps = {len(p.steps)} in the plan")
