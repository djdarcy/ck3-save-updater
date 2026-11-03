"""Census: the production resolver against the descent on EVERY keyed child and EVERY bare token of the founding
save -- not only the positions R5 and R11 hand it, since a player's own pack may hand any. Read only.

Found the need: the fixture test (tests/test_blockindex.py) caught `color=rgb { ... }` blocks keyed differently, a
form R5's and R11's 1.3 M candidates never reached (2026-11-02). PREDICTION, after that fix: 0 mismatches.
Compared in batches of 400,000 positions to keep memory bounded.

Run:  python -I tests/one-offs/thinking/poc-block-index/verify_census.py <founding save.ck3>
"""

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.patches import blockindex as BI  # noqa: E402
from ck3_save_migrator.patches import paths as P  # noqa: E402

ANY_KEY = re.compile(rb"(?<![^\s{}])([A-Za-z_][\w.:\-]*)[ \t]*=")
ANY_VALUE = re.compile(rb"(?<![^\s{}])([\w.\"\-:]+)(?=[\s}])")
T = time.perf_counter


def main() -> int:
    d = sf.read_save(sys.argv[1]).gamestate
    t = T()
    pos = sorted({m.start(1) for m in ANY_KEY.finditer(d)} | {m.start(1) for m in ANY_VALUE.finditer(d)})
    print(f"{len(pos):,} positions found in {T() - t:.1f} s")
    BI.forget()
    t_new = t_old = 0.0
    bad = resolved = 0
    examples = []
    step = 400_000
    for i in range(0, len(pos), step):
        batch = pos[i:i + step]
        t = T(); new = P.resolve(d, batch); t_new += T() - t
        t = T(); old = P.resolve_by_descent(d, batch); t_old += T() - t
        resolved += len(old)
        for p in old.keys() | new.keys():
            if p not in old or p not in new or old[p][0] != new[p][0] or old[p][1] != new[p][1]:
                bad += 1
                if len(examples) < 5:
                    examples.append((p, d[max(0, p - 40):p + 40]))
        print(f"  {i + len(batch):,}/{len(pos):,}: mismatches so far {bad}")
    print(f"TOTAL: {bad} mismatches; {resolved:,} positions resolved of {len(pos):,} offered; "
          f"index {t_new:.0f} s, descent {t_old:.0f} s")
    for e in examples:
        print("  mismatch at", e)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
