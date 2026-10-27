"""variant_drop_unrun_coordinators: a diagnostic copy of a migrated save with rule R20 applied alone (drop the AI war
coordinators that were created and never run, the war plans that name them, and those plans' ids in the owners'
AI strategies), for a soak.

2026-10-27: the 20 March 989 / 990 stop is the AI's CAIUnitStack splitting its army groups without end, because its
CAIWarCoordinator's supply limit (+0x78, loaded from supply_limit) is 0. The 1.8.1 campaign holds 6 of 172
coordinators that were never run (no war_stance, supply_limit 0); 1.20 writes none. The first version of this
script dropped coordinators and plans but left the plans' ids in ai/ai_strategies, and the game crashed on load
(05:19, ck3+0x1aca4b0); the rule now removes those too. Never a migration: a copy for a soak.

Usage: python -I tests/one-offs/variant_drop_unrun_coordinators.py <migrated.ck3> <out.ck3>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    src, out = sys.argv[1:3]
    save = sf.read_save(src)
    res = R.run_rules(save, R.select("R20"), R.RuleContext())[0]
    sf.write_save(save, out, force=True)
    print(f"wrote {out}: R20 matched {res.matched}, edited {res.edited}; {res.extra}")


if __name__ == "__main__":
    main()
