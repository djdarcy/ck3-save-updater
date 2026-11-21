"""R50 on a real 1.20 save, before any game load: which duchies it adds, which counties move, what else the transplant
inserts, and whether de jure links stay consistent. Goal 2026-11-20__16-02-08 S4 (the 11 new 1.21 duchies).

Usage: python -I tests/one-offs/thinking/r50_poc.py <1.20 save> <ref-1.21> <game dir> <out.ck3>
Writes only <out.ck3>, and refuses to overwrite it.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import rules as R  # noqa: E402
from ck3_save_migrator.rules.to_1_21 import r50_new_duchies  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


class Shim:
    def result(self, **kw):
        return kw


def links(g):
    liege, vass = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        m = re.search(rb"\n\tde_jure_liege=(\d+)", b)
        v = re.search(rb"\n\tde_jure_vassals=\{([^}]*)\}", b)
        if m:
            liege[e.key] = m.group(1)
        if v:
            vass[e.key] = set(v.group(1).split())
    a = sum(1 for k, p in liege.items() if k not in vass.get(p, set()))
    b = sum(1 for d, vs in vass.items() for c in vs if liege.get(c) != d)
    return a, b


def main(src, ref, game, out):
    out = Path(out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    save = read_save(src)
    ctx = R.RuleContext(reference=Path(ref), game_dir=Path(game))
    res = r50_new_duchies(save, ctx, Shim())
    print(json.dumps(res, indent=1)[:3000])
    print("de jure links broken (child unlisted, listed child elsewhere):", links(save.gamestate))
    from ck3_save_migrator.savefile import write_save
    write_save(save, out)
    print("wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:5])
