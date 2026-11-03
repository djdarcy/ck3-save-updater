"""The production resolver (paths.resolve, over blockindex) against the descent it replaced (paths.resolve_by_descent),
on every position the engine hands it while planning R5 and R11 on the founding save -- the POC's arm A1 again, on
the shipped code rather than the POC's copy. Read only.

PREDICTION: 0 mismatches over the same 1,297,345 positions; the plans' edit lists equal (R5 99, R11 997).
Run:  python -I tests/one-offs/thinking/poc-block-index/verify_production.py <founding save.ck3>
"""

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))

from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.patches import engine as E  # noqa: E402
from ck3_save_migrator.patches import paths as P  # noqa: E402
from ck3_save_migrator.patches import read_pack  # noqa: E402

T = time.perf_counter
NEW = P.resolve


def main() -> int:
    d = sf.read_save(sys.argv[1]).gamestate
    pack = read_pack()
    calls = []

    def recording(data, positions):
        calls.append(list(positions))
        return P.resolve_by_descent(data, positions)
    P.resolve = recording
    old_plans = {r: E.plan(d, pack.patches[r], {}) for r in ("R5", "R11")}
    P.resolve = NEW
    total = bad = 0
    for poss in calls:
        t = T(); new = NEW(d, poss); tn = T() - t
        old = P.resolve_by_descent(d, poss)
        miss = sum(1 for p in old.keys() | new.keys()
                   if p not in old or p not in new or old[p][0] != new[p][0] or old[p][1] != new[p][1])
        total += len(set(poss)); bad += miss
        print(f"{len(poss):,} positions: mismatches {miss}; production resolve {tn:.1f} s")
    plans_equal = all(E.plan(d, pack.patches[r], {}).edits == old_plans[r].edits for r in ("R5", "R11"))
    print(f"TOTAL: {bad} mismatches over {total:,} positions; plans equal: {plans_equal}")
    return 0 if bad == 0 and plans_equal else 1


if __name__ == "__main__":
    sys.exit(main())
