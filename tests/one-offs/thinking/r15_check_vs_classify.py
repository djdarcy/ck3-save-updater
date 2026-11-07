"""MEASURE: can R15's check say "done" while R15's own classifier still has work (moved baronies)?

The refactor advisor (2026-11-07, row 7) read that the check (detect._dead_titles) counts only title keys the game no
longer defines, while R15 runs deadtitles.classify, which also renames MOVED baronies (defined in both versions, on
another province). A save with moved baronies and no dead keys would be judged "done" and R15 skipped.

Per save: the check's verdict and count; classify's mappings by kind (dead / moved). The bug fires when the check
says done and classify finds anything. Known answer: the founding save has 96 dead titles and 10 moved baronies
(deadtitles.py docstring, 1.8.1 -> 1.20).

Run: python -I tests/one-offs/thinking/r15_check_vs_classify.py <game dir> <old game dir> <save.ck3> ...
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import deadtitles as D  # noqa: E402
from ck3_save_migrator.detect import Env, _dead_titles  # noqa: E402
from ck3_save_migrator.lint import defined_title_keys  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

game, old = Path(sys.argv[1]), Path(sys.argv[2])
_, conversion = defined_title_keys(game)
for p in map(Path, sys.argv[3:]):
    g = read_save(p).gamestate
    d = _dead_titles(g, Env(game_dir=game))
    maps = D.classify(g, old / "common" / "landed_titles", game / "common" / "landed_titles", set(conversion))
    kinds = Counter(m.kind for m in maps)
    fires = d.state == "done" and bool(maps)
    print(f"{p.name[-40:]}: check {d.state} ({d.count}); classify {dict(kinds)}; "
          f"{'BUG FIRES: R15 would be skipped with work to do' if fires else 'no skip'}")
