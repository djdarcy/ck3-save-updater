"""Write the table of 1.20 building slots per province, for downshape.Provinces (goal F2, option (b), 2026-11-18).

A 1.20 holding lists one entry per building slot, filled or empty (province 9537: 4 entries, 2 empty). The count does
not follow 1.21's regular_district_slot_limit, nor the holding type alone (goal file, 17:3x), so a copied 1.21
holding takes its 1.20 count from this table: province id -> entries in a fresh 1.20 game's buildings list.
Read only on the reference; writes the JSON the package ships.
Run: python -I -X utf8 tests/one-offs/make_slot_table.py <1.20 reference.ck3> ck3_save_migrator/known_slots/1.20.1.2.json
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def main(ref, out):
    g = read_save(ref).gamestate
    table = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if not (e.key and e.key.isdigit()):
            continue
        b = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", b)
        if not h:
            continue
        hb = b[h.end() - 1:gs.match_brace(b, h.end() - 1) + 1]
        bl = re.search(rb"\bbuildings=\{", hb)
        if bl:
            inner = hb[bl.end():gs.match_brace(hb, bl.end() - 1)]
            table[e.key.decode()] = len(re.findall(rb"\{", inner))
    p = pathlib.Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"source": "a fresh 1.20.1.2 game at 987.10.27 (ref_1_20_987_10_27.ck3)",
                             "slots": table}, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"{p}: {len(table)} provinces")


if __name__ == "__main__":
    main(*sys.argv[1:3])
