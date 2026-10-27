"""variant_undo_promotion: a test variant of a migrated save in which one 1c-bis family promotion is undone.

The game hangs on 987.11.8 in a loop over county c_kuzeytorg (16745), whose parent field the game set to itself at
runtime; the county is one 1c-bis gave to a family baron (Liber, 70790) instead of the old count (79743). This
writes a copy where the county goes to the old count instead (the rule's non-family branch), Liber keeping his
barony, so one launch can say whether the promotion is what the game trips over. A diagnostic, never a migration.

Usage: python -I tests/one-offs/variant_undo_promotion.py <in.ck3> <out.ck3> [county id] [promoted id] [old count id]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    src, out = sys.argv[1:3]
    county, promoted, old = (sys.argv[3:6] + ["16745", "70790", "79743"][len(sys.argv[3:6]):])
    save = sf.read_save(src)
    g = save.gamestate
    edits = []
    t = next(e for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body) if e.key == county.encode())
    m = re.compile(rb"\n\tholder=" + promoted.encode() + rb"\n").search(g, t.start, t.end)
    edits.append((m.start(), m.end(), b"\n\tholder=" + old.encode() + b"\n"))
    living = {e.key: e for e in gs.iter_entries(g, *gs.locate(g, "living").body) if e.key in (promoted.encode(), old.encode())}
    p = living[promoted.encode()]
    d = re.compile(rb"\n\t\tdomain=\{([^}]*)\}").search(g, p.start, p.end)
    ids = [x for x in d.group(1).split() if x != county.encode()]
    edits.append((d.start(1), d.end(1), b" " + b" ".join(ids) + b" "))
    o = living[old.encode()]
    d2 = re.compile(rb"\n\t\tdomain=\{([^}]*)\}").search(g, o.start, o.end)
    edits.append((d2.start(1), d2.end(1), d2.group(1).rstrip() + b" " + county.encode() + b" "))
    for s, e, rep in sorted(edits, reverse=True):
        save.replace_range(s, e, rep)
    sf.write_save(save, out, force=True)
    print(f"county {county}: holder {promoted} -> {old}; {promoted}'s domain {ids}; wrote {out}")


if __name__ == "__main__":
    main()
