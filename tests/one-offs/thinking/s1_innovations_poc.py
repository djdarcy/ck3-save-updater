"""Goal 2026-11-19__22-43-27, S1 poc: write the 18 missing innovations into a copy of the converted campaign.

Uses the product function `carry_1_21.insert_missing_innovations` (the rule will call the same one). The output is
loaded in the game (observe mode, time running) and saved again; the falsifiable prediction, written first:
  - the re-save lists all 131 innovations for every culture (the game keeps the inserted entries);
  - after months of play some culture has `progress` on at least one of the 18 (research advances), where two years
    of play on v19 itself produced none (they were not listed);
  - no new error-log lines against a control load of v19.
CONTROL: v19 itself through the same run shows 0 cultures with any of the 18.

Run: python -I -X utf8 tests/one-offs/thinking/s1_innovations_poc.py <v19> <fresh 1.21 ref> <1.21 game dir> <out.ck3>
Writes only <out.ck3> (a new MIGRATE_TEST__ file).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import carry_1_21  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402


def main(v19, ref, game, out):
    s = read_save(v19)
    r = carry_1_21.insert_missing_innovations(s.gamestate, read_save(ref).gamestate, carry_1_21.innovation_eras(game))
    print(f"missing {len(r.missing)}: {r.missing}")
    print(f"cultures given entries: {r.cultures}; discovered (evidence): {len(r.discovered)} {r.discovered}")
    again = carry_1_21.insert_missing_innovations(r.gamestate, read_save(ref).gamestate, carry_1_21.innovation_eras(game))
    print(f"second pass: missing {len(again.missing)}, changed {again.gamestate != r.gamestate}")
    s.set_gamestate(r.gamestate)
    print(write_save(s, out))


if __name__ == "__main__":
    main(*sys.argv[1:])
