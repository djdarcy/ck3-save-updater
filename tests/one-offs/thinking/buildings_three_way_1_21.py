"""Patch day 1.21, measure 2: what became of v17's buildings in 1.21's conversion.

v17 (1.20) keeps a holding's buildings in provinces/<id>/holding/buildings. 1.21 keeps districts/database and
buildings/database. For each save: how many buildings in all, how many provinces hold any, and one province shown
in all three (by id) so the shapes can be compared.
Known answer: province 7 in v17 holds 5 buildings (castle_01, hunting_grounds_01, common_tradeport_02,
curtain_walls_01, peat_quarries_01), read by hand from the save.
Run: python -I -X utf8 tests/one-offs/thinking/buildings_three_way_1_21.py <v17> <resave> <ref> [province id]
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def old_buildings(g):
    """province id -> [building types] from provinces/<id>/holding/buildings (1.20 shape)."""
    out = {}
    b = gs.locate(g, "provinces")
    for e in gs.iter_entries(g, *b.body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", body)
        if not h:
            continue
        m = re.search(rb"\n\t\t\tbuildings=\{(.*?)\n\t\t\t\}", body[h.end():], re.S) or \
            re.search(rb"\n\t\t\tbuildings=\{(.*?) \}\n", body[h.end():], re.S)
        if m:
            out[e.key.decode()] = [t.decode() for t in re.findall(rb'type="?(\w+)', m.group(1))]
    return out


def new_buildings(g):
    """counts of districts and buildings by type (1.21 shape), and province id -> raw holding text."""
    types = collections.Counter()
    try:
        bb = gs.locate(g, "buildings/database")
        for e in gs.iter_entries(g, *bb.body):
            m = re.search(rb"type=(\w+)", g[e.open:e.open + 200])
            types[m.group(1).decode() if m else "?"] += 1
    except gs.GamestateError:
        pass
    return types


def province(g, pid):
    b = gs.locate(g, "provinces")
    e = next((e for e in gs.iter_entries(g, *b.body) if e.key == pid.encode()), None)
    return g[e.open:e.open + 900].decode("utf-8", "replace") if e else None


def main(v17, resave, ref, pid="7"):
    gv, gr, gf = (read_save(p).gamestate for p in (v17, resave, ref))
    ob = old_buildings(gv)
    print(f"known answer: v17 province 7 = {ob.get('7')}")
    print(f"v17: {sum(len(v) for v in ob.values())} buildings in {len(ob)} provinces' holdings")
    for name, g in (("resave", gr), ("ref", gf)):
        t = new_buildings(g)
        print(f"{name}: {sum(t.values())} buildings in buildings/database; top types: {t.most_common(8)}")
    ob_r = old_buildings(gr)
    print(f"resave: {sum(len(v) for v in ob_r.values())} buildings still in the old holding shape ({len(ob_r)} provinces)")
    for name, g in (("v17", gv), ("resave", gr), ("ref", gf)):
        print(f"\n--- province {pid} in {name} ---\n{province(g, pid)}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
