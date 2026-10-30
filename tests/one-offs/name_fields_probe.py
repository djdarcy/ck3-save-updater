"""name_fields_probe: what does a save store in a character's name-related fields? (2026-10-30)

djdarcy: in play6, Beidh's grandfather shows as `Echmarcach " of Ireland` and the founder Uilleam as
`Uilleam of " of Ireland`; their grand nicknames were clipped. This prints, for chosen characters (by id, or by
first name), every depth-1 line of the character's block whose key mentions name, nick, epithet, title or dynasty,
side by side for two saves, so the change is visible field by field.

Usage: python -I tests/one-offs/name_fields_probe.py <original.ck3> <migrated.ck3> [--id 28792] [--name Echmarcach]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
KEY = re.compile(rb"^\t([a-z_]*(?:name|nick|epithet|title|dynasty|house)[a-z_]*)=(.*)$", re.M)


def fields(g: bytes, cid: int):
    for sec in SECTIONS:
        for i, e in T.entries(g, sec):
            if i == cid:
                body = g[e.open:e.close]
                return sec, [(m.group(1).decode(), m.group(2).decode("utf-8", "replace")) for m in KEY.finditer(body)]
    return None, []


def ids_named(g: bytes, name: str):
    pat = re.compile(rb'\n\tfirst_name="' + re.escape(name.encode()) + rb'"')
    out = []
    for sec in SECTIONS:
        for i, e in T.entries(g, sec):
            if pat.search(g[e.open:e.open + 600]):
                out.append(i)
    return out


def main():
    a = sys.argv[1:]
    orig, mig = read_save(a[0]).gamestate, read_save(a[1]).gamestate
    ids = [int(a[i + 1]) for i, x in enumerate(a) if x == "--id"]
    for i, x in enumerate(a):
        if x == "--name":
            ids += ids_named(orig, a[i + 1])
    for cid in ids:
        so, fo = fields(orig, cid)
        sm, fm = fields(mig, cid)
        print(f"== character {cid}: original in {so}, migrated in {sm}")
        keys = list(dict.fromkeys([k for k, _ in fo] + [k for k, _ in fm]))
        do, dm = dict(fo), dict(fm)
        for k in keys:
            vo, vm = do.get(k, "(absent)"), dm.get(k, "(absent)")
            mark = "   " if vo == vm else " * "
            print(f"{mark}{k:24s} original: {vo[:70]:70s} migrated: {vm[:70]}")


if __name__ == "__main__":
    main()
