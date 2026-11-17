"""S1 (patch-day goal): ids in a save that point at no row -- districts, buildings, markets.

After to_1_20 runs from a 1.21 reference, R14 copies whole provinces (and R16 titles) from the reference in 1.21 shape,
so their district ids and title trade_market ids may point into databases the target does not have.
Checks:
  provinces' holding_district / resource_district / districts={...} / special_district / great_district /
    duchy_capital_district -> districts/database;
  districts' buildings={...} -> buildings/database;
  titles' trade_market= -> trade_markets/database.
4294967295 is the game's none.
Known answer: the 1.21 reference itself has no dangling ids.
Run: python -I -X utf8 tests/one-offs/thinking/s1_dangling_1_21.py <save.ck3> [<save.ck3> ...]
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NONE = b"4294967295"


def ids(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return None
    return {e.key for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}


def refs(g, path, pattern):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return []
    out = []
    for m in re.finditer(pattern, g[b.open:b.close]):
        out += [x for x in m.group(1).split() if x.isdigit() and x != NONE]
    return out


def main(*saves):
    for s in saves:
        g = read_save(s).gamestate
        d, bl, tm = ids(g, "districts/database"), ids(g, "buildings/database"), ids(g, "trade_markets/database")
        print(f"\n{pathlib.Path(s).name}: districts {len(d) if d is not None else 'absent'}, "
              f"buildings {len(bl) if bl is not None else 'absent'}, markets {len(tm) if tm is not None else 'absent'}")
        pd = refs(g, "provinces", rb"\b(?:holding_district|resource_district|special_district|great_district|"
                                  rb"duchy_capital_district)=(\d+)") + \
            refs(g, "provinces", rb"\n\t\t\tdistricts=\{([^}]*)\}")
        db = refs(g, "districts/database", rb"\bbuildings=\{([^}]*)\}")
        tt = refs(g, "landed_titles/landed_titles", rb"\btrade_market=(\d+)")
        for name, rs, table in (("province -> district", pd, d), ("district -> building", db, bl),
                                ("title -> market", tt, tm)):
            dangling = [r for r in rs if table is None or r not in table]
            print(f"  {name:22} refs {len(rs):6}  dangling {len(dangling):6}  e.g. {dangling[:5]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
