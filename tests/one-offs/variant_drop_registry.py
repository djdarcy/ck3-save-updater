"""variant_drop_registry: a diagnostic copy of a save with part (c)'s additions to ONE registry list removed.

The additions are the ids (or name-map lines) the base save's list holds that a save made before part (c) does not
(e2e_1b). Registries: culture_manager/template_cultures, dynasties/static_dynasties,
dynasties/static_dynasty_houses (id lists), coat_of_arms/coat_of_arms_manager_name_map (key=coat lines).
`--keep-fraction a/b` keeps only the a-th of b equal slices of the additions (for halving a list). Never a migration.

Usage: python -I tests/one-offs/variant_drop_registry.py <base.ck3> <pre-part-c.ck3> <registry path> <out.ck3>
                                                         [--keep-slice a/b]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

PAIR = re.compile(rb"(?m)^(\t*)([^\s={}]+)=(\d+)[ \t]*\n")


def main():
    base_p, good_p, path, out = sys.argv[1:5]
    keep = sys.argv[sys.argv.index("--keep-slice") + 1] if "--keep-slice" in sys.argv else None
    save = sf.read_save(base_p)
    g, good = save.gamestate, sf.read_save(good_p).gamestate
    b, gb = gs.locate(g, path), gs.locate(good, path)
    body, gbody = g[b.open + 1:b.close], good[gb.open + 1:gb.close]
    if path.endswith("name_map"):
        have = {m.group(2) for m in PAIR.finditer(gbody)}
        entries = [m for m in PAIR.finditer(body)]
        added = [m for m in entries if m.group(2) not in have]
        if keep:
            a, n = (int(x) for x in keep.split("/"))
            k = len(added)
            kept = set(id(m) for m in added[k * (a - 1) // n: k * a // n])
            added = [m for m in added if id(m) not in kept]
        drop = {m.start() for m in added}
        new = b"".join(m.group(0) for m in entries if m.start() not in drop)
        rest = PAIR.sub(b"", body)          # anything that is not a pair line stays, at the end
        newbody = new + rest
    else:
        have = set(gbody.split())
        ids = body.split()
        added = [x for x in ids if x not in have]
        if keep:
            a, n = (int(x) for x in keep.split("/"))
            k = len(added)
            kept = set(added[k * (a - 1) // n: k * a // n])
            added = [x for x in added if x not in kept]
        drop = set(added)
        newbody = b" " + b" ".join(x for x in ids if x not in drop) + b" "
    save.replace_range(b.open + 1, b.close, newbody)
    sf.write_save(save, out, force=True)
    print(f"{path}: removed {len(added)} added entries; wrote {out}")


if __name__ == "__main__":
    main()
