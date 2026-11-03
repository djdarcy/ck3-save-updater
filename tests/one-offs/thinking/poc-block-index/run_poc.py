"""POC: the in-memory block index as the `**` resolver (director's ruling 2026-11-02).

PREDICTIONS (written before running):
  A1  equivalence: for EVERY position the engine hands paths.resolve while planning R5 and R11 on the founding save
      (R11 alone: 102,517 + 924 + 1,190,027), index_resolve.resolve returns the same dict -- same keys, the same
      ancestor Blocks in order, the same Child -- with 0 mismatches.
      Pass: 0 mismatches over all calls. Fallback: classify the mismatches; if they are a fixable class (a key the
      index reads differently), fix the index and re-run; if not, step 2 of the unit (share today's resolve).
  A2  the plans: engine.plan for R5 and R11 with the index resolver gives exactly the edits it gives today
      (R5 99, R11 997 on this save). Pass: equal edit lists. Fallback: as A1.
  A3  time: index build ~11 s once, then R5 + R11 resolve in a few seconds, against ~100 s+ today.
  C1  CONTROL (must fail): the same comparison with one ancestor key corrupted in the index -> mismatches > 0.
  C2  CONTROL (must fail): an index built for the gamestate with one byte inserted near its start (a splice),
      used on the unspliced bytes -> mismatches > 0. Shows why the index is keyed to the bytes object.
If C1 or C2 passes (0 mismatches), the method is broken and no result is reported.

Read only: reads one save, writes nothing. Production code untouched (paths.resolve wrapped in this process only).
Run:  python -I tests/one-offs/thinking/poc-block-index/run_poc.py <founding save.ck3>
"""

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE))

import index_resolve as IR  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.patches import engine as E  # noqa: E402
from ck3_save_migrator.patches import paths as P  # noqa: E402
from ck3_save_migrator.patches import read_pack  # noqa: E402

T = time.perf_counter
ORIG = P.resolve


def compare(old: dict, new: dict, limit: int = 4) -> tuple[int, list]:
    bad, examples = 0, []
    for p in set(old) | set(new):
        a, b = old.get(p), new.get(p)
        same = a is not None and b is not None and list(a[0]) == list(b[0]) and a[1] == b[1]
        if not same:
            bad += 1
            if len(examples) < limit:
                examples.append((p, None if a is None else ([x.key for x in a[0]][-3:], a[1].key),
                                 None if b is None else ([x.key for x in b[0]][-3:], b[1].key)))
    return bad, examples


def main() -> int:
    d = sf.read_save(sys.argv[1]).gamestate
    pack = read_pack()
    rows = []

    # ---- today's resolve, recording every call the engine makes for R5 and R11
    calls: list[tuple[str, list[int], dict, float]] = []

    def recording(data, positions):
        t = T(); r = ORIG(data, positions); calls.append((cur[0], list(positions), r, T() - t))
        return r
    cur = [""]
    P.resolve = recording
    plans_old = {}
    for rid in ("R5", "R11"):
        cur[0] = rid
        t = T(); plans_old[rid] = E.plan(d, pack.patches[rid], {}); print(f"today  {rid} plan {T() - t:.1f} s")
    P.resolve = ORIG

    # ---- A1: the index on exactly those calls
    t = T(); idx = IR.Index(d); t_build = T() - t
    print(f"index: {len(idx.opens):,} blocks built in {t_build:.1f} s")
    total_pos = total_bad = 0
    t_new = 0.0
    for rid, poss, old, t_old in calls:
        t = T(); new = IR.resolve(d, poss, idx); dt = T() - t; t_new += dt
        bad, ex = compare(old, new)
        total_pos += len(set(poss)); total_bad += bad
        print(f"A1 {rid}: {len(poss):,} positions, {len(old):,} resolved; today {t_old:.1f} s, index {dt:.1f} s; "
              f"mismatches {bad}")
        for e in ex:
            print("   ", e)
    rows.append(("A1 equivalence", f"{total_bad} mismatches over {total_pos:,} positions",
                 "SURVIVED" if total_bad == 0 else "REFUTED"))

    # ---- A2: whole plans with the index resolver
    P.resolve = lambda data, positions: IR.resolve(data, positions, idx if data is d else None)
    a2 = []
    for rid in ("R5", "R11"):
        t = T(); pn = E.plan(d, pack.patches[rid], {}); dt = T() - t
        po = plans_old[rid]
        same = po.edits == pn.edits and po.stats == pn.stats
        a2.append(same)
        print(f"A2 {rid}: edits today {len(po.edits)}, index {len(pn.edits)}; equal: {same}; plan {dt:.1f} s")
    P.resolve = ORIG
    rows.append(("A2 plans", f"R5 and R11 edit lists equal: {a2}", "SURVIVED" if all(a2) else "REFUTED"))
    t_old_total = sum(c[3] for c in calls)
    rows.append(("A3 time", f"today {t_old_total:.1f} s of resolve; index {t_build:.1f} s build + {t_new:.1f} s", "--"))

    # ---- C1: a corrupted key in the index must be caught
    rid, poss, old, _ = max(calls, key=lambda c: len(c[2]))
    parent_open = old[next(iter(old))][0][-1].open
    i = list(idx.opens).index(parent_open)
    bad_idx = IR.Index.__new__(IR.Index)
    bad_idx.__dict__.update(idx.__dict__)
    bad_idx.ks = IR.array("q", idx.ks); bad_idx.ke = IR.array("q", idx.ke); bad_idx._blocks = {}
    bad_idx.ke[i] = bad_idx.ke[i] - 1 if bad_idx.ke[i] > bad_idx.ks[i] + 1 else bad_idx.ke[i] + 1
    c1, _ = compare(old, IR.resolve(d, poss, bad_idx))
    rows.append(("C1 control: one key corrupted", f"{c1} mismatches (must be > 0)", "FAILED as designed" if c1 else "PASSED: METHOD BROKEN"))

    # ---- C2: a stale index (built before a 1-byte splice) used on the unspliced bytes must be caught
    d2 = d[:200] + b" " + d[200:]
    stale = IR.Index(d2)
    stale.d = d                                         # forced use on the wrong bytes, as a stale cache would
    try:
        c2, _ = compare(old, IR.resolve(d, poss, stale))
        seen = f"{c2} mismatches (must be > 0)"
    except Exception as exc:                            # a stale index can also make the child parser raise
        c2, seen = 1, f"raised {type(exc).__name__}: {exc} (a detected failure)"
    rows.append(("C2 control: stale index", seen, "FAILED as designed" if c2 else "PASSED: METHOD BROKEN"))

    print("\n| arm | observation | verdict |\n|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
