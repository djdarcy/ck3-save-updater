"""Print the real-save results of R25-R30, the numbers P4 writes into test_real_987_counts (goal 2026-11-05__09-39-46).
Same save, selection and context as that test. Usage: python -I real_counts.py"""
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import rules as R, savefile as sf  # noqa: E402
from tests.test_rules import GAME, REAL_987  # noqa: E402

save = sf.read_save(REAL_987)
res = {r.id: r for r in R.run_rules(save, R.select("all", include_off=("R7",)), R.RuleContext(game_dir=GAME))}
for rid in ("R25", "R26", "R27", "R28", "R29", "R30"):
    r = res.get(rid)
    print(rid, None if r is None else (r.matched, r.edited, {k: v for k, v in (r.extra or {}).items()
                                                              if not isinstance(v, (list, dict)) or len(v) < 6}))
