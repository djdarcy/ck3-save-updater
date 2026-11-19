"""A new id never lands on an index the game already uses (the test plan's C4, the cleanup's G3, 2026-11-18).

CONSEQUENCE: 10 (data) -- a clash makes the game drop the row on its next load.

1.21's databases give each row an id whose high byte is a generation and whose low 24 bits are the row's index; the
index is what must be unique. The same mistake, "largest whole id + 1", was made three times in this project:
- 2026-11-05, the transplant's contract writer: a new contract took another contract's slot and the game crashed;
- 2026-11-18, carry_1_21's contracts (R37): 56 of 63 restored contracts were dropped on the next load;
- 2026-11-18, carry_wonders' buildings and districts: found by this concept, before it bit (the 1.21 reference holds
  generations 0-2 in both databases, and its largest id + 1 lands on an index in use).
Each allocator is one row here, so the next one is a line, not a lesson relearned.
"""
import os
from pathlib import Path

import pytest

from ck3_save_migrator import carry_1_21 as C
from ck3_save_migrator import gamestate as gs
from tests.test_carry_1_21 import SAVE, host  # noqa: F401  (the synthetic 1.21 game folder fixture)

GEN = 1 << 24
# a row of generation 1 at index 5, and a row of generation 0 at index 6: the largest whole id + 1 is GEN | 6, whose
# index 6 is taken
MIXED = (f"\t\t{GEN | 5}={{\n\t\t\ttype=x\n\t\t}}\n\t\t6={{\n\t\t\ttype=y\n\t\t}}\n")


def database(top: str) -> bytes:
    return f"{top}={{\n\tdatabase={{\n{MIXED}\t}}\n}}\n".encode()


def low_indexes(g: bytes, path: str) -> list[int]:
    return [int(e.key) & 0xFFFFFF for e in gs.iter_entries(g, *gs.locate(g, path).body) if e.key and e.key.isdigit()]


@pytest.mark.parametrize("path, top", [("vassal_contracts/database", "vassal_contracts"),
                                       ("buildings/database", "buildings"),
                                       ("districts/database", "districts")])
def test_the_next_index_is_free_in_every_1_21_database(path, top):
    g = database(top)
    taken = set(low_indexes(g, path))
    assert C._next_index(g, path) not in taken


def test_carry_wonders_gives_each_new_building_and_district_a_free_index(host):  # noqa: F811
    g = SAVE + database("buildings") + database("districts")
    r = C.carry_wonders(g, host)
    assert r.carried
    for path in ("buildings/database", "districts/database"):
        idx = low_indexes(r.gamestate, path)
        assert len(idx) == len(set(idx)), (path, sorted(idx))


REF_121 = Path(__file__).resolve().parents[1] / "private" / "data" / "originals" / "reference-1.21" / \
    "ref_1_21_987_10_27.ck3"


@pytest.mark.skipif(os.environ.get("CK3_REAL_SAVES") != "1" or not REF_121.exists(),
                    reason="set CK3_REAL_SAVES=1 with the 1.21 reference on disk (private/data is gitignored)")
def test_the_next_index_is_free_in_the_real_1_21_reference():
    from ck3_save_migrator.savefile import read_save
    g = read_save(REF_121).gamestate
    for path in ("vassal_contracts/database", "buildings/database", "districts/database"):
        assert C._next_index(g, path) not in set(low_indexes(g, path)), path
