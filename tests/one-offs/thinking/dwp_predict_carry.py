"""The built-state carry DWP's predicted numbers: a model of the rule run over v17 and the S1 table, before any build.

Per held holding: its 1.20 regular buildings -> successors (settled S1 rows only; open rows are skipped and named) ->
grouped by the district that hosts them -> at most 2 district types (the converted save's regular_district_slot_limit)
chosen by most buildings, then by the higher sum of tiers -> per district at most the fresh game's largest free-slot
count for that type (its longest buildings list minus the primary). Everything not written is counted by reason.

Run: python -I -X utf8 tests/one-offs/thinking/dwp_predict_carry.py <v17> <ref 1.21> <s1 table.json>
Reads only.
"""
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402
import role_table_1_21 as rt  # noqa: E402


def lvl(k):
    t = k.rsplit("_", 1)[-1]
    return int(t) if t.isdigit() else 1


def caps(ref):
    g = read_save(ref).gamestate
    c = collections.Counter()
    for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body):
        b = g[e.open:e.close]
        t = re.search(rb"type=(\w+)", b).group(1).decode()
        m = re.search(rb"buildings=\{([^{}]*)\}", b)
        c[t] = max(c[t], len(m.group(1).split()) - 1 if m else 0)
    return c


def main(v17, ref21, table):
    rows = {(r["family"], r["holding"]): r for r in json.loads(pathlib.Path(table).read_text(encoding="utf-8"))}
    cap = caps(ref21)
    held = rt.old_holdings(read_save(v17).gamestate)
    n = collections.Counter()
    open_rows = collections.Counter()
    types_per_holding = collections.Counter()
    for pid, (ht, bl) in held.items():
        if not ht or not bl:
            continue
        plan = collections.defaultdict(list)
        for k in bl:
            r = rows.get((rt.fam(k), ht))
            if r is None or r["kind"] in ("holding line", "wonder"):
                continue
            if r["kind"] != "settled":
                n["skipped: open row"] += 1
                open_rows[r["family"]] += 1
                continue
            plan[r["district"]].append(lvl(k))
        if not plan:
            continue
        n["holdings with a carry"] += 1
        types_per_holding[len(plan)] += 1
        ranked = sorted(plan.items(), key=lambda x: (-len(x[1]), -sum(x[1])))
        for i, (d, levels) in enumerate(ranked):
            if i >= 2:
                n["dropped: third district type"] += len(levels)
                continue
            n["districts written"] += 1
            keep = min(len(levels), cap[d])
            n["buildings written"] += keep
            n["dropped: district full"] += len(levels) - keep
    for k in ("holdings with a carry", "districts written", "buildings written", "dropped: third district type",
              "dropped: district full", "skipped: open row"):
        print(f"{k:30} {n[k]:6}")
    print("district types per holding:", dict(sorted(types_per_holding.items())))
    print("free-slot caps used:", {d: cap[d] for d in ("villages_district", "walls_district", "urban_housing_district",
                                                         "manor_houses_district")})
    print("open rows by family (top 8):", open_rows.most_common(8))


if __name__ == "__main__":
    main(*sys.argv[1:4])
