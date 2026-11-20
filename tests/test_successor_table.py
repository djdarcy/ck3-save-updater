"""The successor table: what each 1.20 regular building becomes in 1.21 (the built-state carry, 2026-11-19).

CONSEQUENCE: 8 (data) -- the carry writes what this table says; a row naming a building 1.21 does not define, or a
family left out, would write a wrong building or lose one silently.

The table is hand-maintained (djdarcy's answers go into it), so these tests check its shape and its promises: every
family has successors or an `open` reason; the three culture- or terrain-locked icon rows the review sent back are open;
and, with the game installed, every named successor is a line 1.21 defines in the district it names.
"""
import os
import re
from pathlib import Path

import pytest

from ck3_save_migrator.patches.model import tomllib   # tomli on Python 3.10, as the package reads it

TABLE = Path(__file__).resolve().parents[1] / "ck3_save_migrator" / "successors" / "successors_1_21.toml"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")


@pytest.fixture(scope="module")
def families():
    return tomllib.loads(TABLE.read_text(encoding="utf-8"))["families"]


def test_every_family_is_carried_or_says_why_not(families):
    assert len(families) >= 60
    for f, row in families.items():
        assert row["successors"] or row.get("open"), f
        for s in row["successors"]:
            assert set(s) >= {"building", "district", "source"} and not re.search(r"_\d+$", s["building"]), (f, s)


def test_the_locked_icon_rows_wait_for_djdarcy(families):
    # the review (2026-11-19 13:35): borghi, village hunter and turbary are culture- or terrain-locked, 1-2 in the
    # whole fresh world; an icon proposes, it does not decide
    for f in ("hill_farms", "hunting_grounds", "peat_quarries"):
        assert families[f]["successors"] == [] and families[f]["open"].startswith("open"), f


@pytest.mark.skipif(os.environ.get("CK3_REAL_SAVES") != "1" or not GAME.is_dir(), reason="needs the 1.21 game")
def test_every_named_successor_is_a_line_its_district_hosts(families):
    from ck3_save_migrator import host_rules as H
    host = H.load(str(GAME))
    for f, row in families.items():
        for s in row["successors"]:
            first = s["building"] + ("_1" if f"{s['building']}_1" in host.buildings else "_01")
            assert host.building_in(first, s["district"]).ok is not False, (f, s)
