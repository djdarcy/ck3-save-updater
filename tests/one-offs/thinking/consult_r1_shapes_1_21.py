"""Consultation round 1 (patch day 1.21): the save shapes of districts, buildings, roads, markets, routes.

Read-only. Prints the first entries of each 1.21 kind in a save, a province's holding, and structural counts:
districts by type, buildings per district, district fields, regular_district_slot_limit distribution.
Run: python -I -X utf8 tests/one-offs/thinking/consult_r1_shapes_1_21.py <save> [province id] [n first entries]
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

KINDS = ("districts/database", "buildings/database", "roads/database", "trade_markets/database",
         "trade_routes/database")


def show(g, path, n, width=700):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        print(f"\n== {path}: absent")
        return
    ents = list(gs.iter_entries(g, *b.body))
    print(f"\n== {path}: {len(ents)} entries")
    fields = collections.Counter()
    for e in ents:
        for m in re.finditer(rb"\n\t\t\t([a-z_0-9]+)=", g[e.open:e.close]):
            fields[m.group(1).decode()] += 1
    print("   depth-1 fields:", dict(fields.most_common(40)))
    for e in ents[:n]:
        print(f"-- {e.key.decode()}:\n{g[e.open:min(e.close + 1, e.open + width)].decode('utf-8', 'replace')}")
    return ents


def main(save, pid="7", n="2"):
    g = read_save(save).gamestate
    n = int(n)
    for k in KINDS:
        show(g, k, n)
    # districts: type counts, buildings per district, level
    try:
        b = gs.locate(g, "districts/database")
    except gs.GamestateError:
        return
    types, nb, lv = collections.Counter(), collections.Counter(), collections.Counter()
    for e in gs.iter_entries(g, *b.body):
        body = g[e.open:e.close]
        m = re.search(rb"\ttype=\"?(\w+)", body)
        types[m.group(1).decode() if m else "?"] += 1
        m = re.search(rb"\tbuildings=\{([^}]*)\}", body)
        nb[len(m.group(1).split()) if m else 0] += 1
        m = re.search(rb"\tlevel=(\d+)", body)
        lv[m.group(1).decode() if m else "-"] += 1
    print("\ndistrict types:", types.most_common(60))
    print("buildings per district:", sorted(nb.items()))
    print("district level:", sorted(lv.items()))
    # provinces: slot limit distribution and one province
    slots = collections.Counter()
    pb = gs.locate(g, "provinces")
    for e in gs.iter_entries(g, *pb.body):
        body = g[e.open:e.close]
        m = re.search(rb"regular_district_slot_limit=(\d+)", body)
        if m:
            slots[int(m.group(1))] += 1
        if e.key == pid.encode():
            print(f"\n-- province {pid}:\n{body[:1800].decode('utf-8', 'replace')}")
    print("regular_district_slot_limit:", sorted(slots.items()))


if __name__ == "__main__":
    main(*sys.argv[1:4])
