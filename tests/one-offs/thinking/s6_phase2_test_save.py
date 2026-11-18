"""Phase two for a player who never ran phase one (the Director, 2026-11-18, correction 5): a test save.

Takes the game's own 1.21 re-save of v17 (djdarcy's, made before the tool existed for 1.21) and writes into it the
wonders read from the 1.20 witness (v17: carry_1_21.carry_wonders(..., witness=)) and the 1.21 reference's roads.
Both saves are dated 987.10.27, so the same-date rule (correction 1) holds. Question: does the game's next re-save KEEP
them (correction 2's check), as S2's 1.21.0-stamped cases kept ours?
Writes a NEW file only. Run:
python -I -X utf8 tests/one-offs/thinking/s6_phase2_test_save.py <1.21 re-save> <witness 1.20> <ref 1.21> <game dir> <out>
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import carry_1_21 as C  # noqa: E402
from ck3_save_migrator import host_rules as H  # noqa: E402
from ck3_save_migrator import roads as R  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402


def main(resave, witness, ref, game, out):
    s = read_save(resave)
    w = C.carry_wonders(s.gamestate, H.load(game), witness=read_save(witness).gamestate)
    rr = R.transplant_roads(w.gamestate, read_save(ref).gamestate, R.defined_road_types(pathlib.Path(game)))
    assert rr.why_not is None, rr.why_not
    s.set_gamestate(rr.gamestate)
    write_save(s, pathlib.Path(out))
    print(f"{pathlib.Path(out).name}: {len(w.carried)} wonders from the witness, {rr.carried} roads")


if __name__ == "__main__":
    main(*sys.argv[1:6])
