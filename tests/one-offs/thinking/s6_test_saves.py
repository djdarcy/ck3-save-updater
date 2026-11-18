"""Patch day S6/S7 (decision C): two test saves for djdarcy to load in 1.21 and re-save.

1. MIGRATE_TEST__1.21-wonders.ck3: v17 (stamped 1.20.1.2) with carry_1_21.carry_wonders applied. Question: does the
   game's conversion keep the 134 wonder districts we wrote, as S2's Alhambra case predicts?
2. MIGRATE_TEST__1.21-roads120.ck3: v17 with an empty roads database and the 1.21 reference's roads written into it.
   Question (the unpack-test's open case 5): do roads written BEFORE the conversion survive it? If not, under C the
   roads copy runs after the first load.

Writes only new files (write_save refuses an existing one). Reads v17 and the reference; changes neither.
Run: python -I -X utf8 tests/one-offs/thinking/s6_test_saves.py <v17> <ref 1.21> <1.21 game dir> <out folder>
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import carry_1_21 as C  # noqa: E402
from ck3_save_migrator import host_rules as H  # noqa: E402
from ck3_save_migrator import roads as R  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402


def main(v17, ref, game, out):
    out = pathlib.Path(out)
    host = H.load(game)

    s = read_save(v17)
    r = C.carry_wonders(s.gamestate, host)
    s.set_gamestate(r.gamestate)
    p = out / "MIGRATE_TEST__1.21-wonders.ck3"
    write_save(s, p)
    print(f"{p.name}: {len(r.carried)} wonders carried, {len(r.unmapped)} unmapped, {len(r.skipped)} refused")
    print("   provinces to look at:", ", ".join(f"{pid} {b}" for pid, b, _, _ in r.carried[:6]))

    s = read_save(v17)
    g = s.gamestate + b"roads={\n\tdatabase={\n\t}\n}\n"
    rr = R.transplant_roads(g, read_save(ref).gamestate, R.defined_road_types(pathlib.Path(game)))
    assert rr.why_not is None, rr.why_not
    s.set_gamestate(rr.gamestate)
    p = out / "MIGRATE_TEST__1.21-roads120.ck3"
    write_save(s, p)
    print(f"{p.name}: {rr.carried} roads written before the conversion, {rr.links_dropped} route links dropped")


if __name__ == "__main__":
    main(*sys.argv[1:5])
