"""apply_rule: run selected rules on an already-built save and write a new file (never in place), for trying a
rule on a play save without a full five-minute migrate (2026-10-27: R22 on play5_play.ck3).

Usage: python -I tests/one-offs/apply_rule.py <in.ck3> <out.ck3> <rules> [<game dir>]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

src, dst, sel = sys.argv[1], sys.argv[2], sys.argv[3]
game = Path(sys.argv[4]) if len(sys.argv) > 4 else None
save = sf.read_save(src)
for r in R.run_rules(save, R.select(sel), R.RuleContext(game_dir=game)):
    print(f"{r.id} {r.name}: matched {r.matched} edited {r.edited}")
    print("   ", json.dumps(r.extra)[:1500])
sf.write_save(save, dst, force=True)
print("wrote", dst)
