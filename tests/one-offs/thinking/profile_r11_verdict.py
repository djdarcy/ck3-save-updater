"""Profile R11's declarative verdict (the detector that took 105.6 s of 176 s on the 1.8.1 save, 2026-11-01).

PREDICTION (written before running): the time is in the `**` edits' candidate resolution -- for each prefilter hit,
working out the chain of enclosing block keys (paths.py) by scanning backwards from the hit, so the cost grows with
hits x depth. The regex prefilter itself over 222 MB should be a few seconds at most. If the profile instead shows the
prefilter regexes dominating, the fix is a cheaper pattern, not a block index.

Read only: reads the save given, runs the verdict, prints the top functions by cumulative and by own time.
Run:  python -I tests/one-offs/thinking/profile_r11_verdict.py <save.ck3> [rule id, default R11]
"""

import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.detect import Env, detect  # noqa: E402
from ck3_save_migrator.patches import read_pack  # noqa: E402


def main() -> None:
    save, rid = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "R11")
    t = time.perf_counter()
    g = sf.read_save(save).gamestate
    print(f"read {len(g) / 1e6:.1f} MB in {time.perf_counter() - t:.1f} s")
    env = Env(patches=read_pack().patches)
    prof = cProfile.Profile()
    t = time.perf_counter()
    prof.enable()
    d = detect(rid, g, env)
    prof.disable()
    print(f"{rid}: {d.line()} in {time.perf_counter() - t:.1f} s")
    st = pstats.Stats(prof)
    st.sort_stats("cumulative").print_stats(18)
    st.sort_stats("tottime").print_stats(12)


if __name__ == "__main__":
    main()
