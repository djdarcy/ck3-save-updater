"""Tests for the unit-3 migration rules (R1-R7) and their CLI.

Synthetic saves only (tests/fixtures/make_ck3.py RULES_META/RULES_BODY), plus one
real-save run of every rule, opt-in with CK3_REAL_SAVES=1 because it takes ~50 s.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3, make_game_dir

ROOT = Path(__file__).resolve().parents[1]
REAL_987 = ROOT / "private" / "data" / "originals" / "save games" / \
    "Arch-Abbot_Beidh_of_Omni_Church_Council_987_10_27_husband_died.ck3"
GAME = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")

DATA = RULES_META + RULES_BODY


@pytest.fixture
def save(tmp_path):
    p = tmp_path / "in.ck3"
    p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    return sf.read_save(p)


def run(save, spec, ctx=None):
    return {r.id: r for r in R.run_rules(save, R.select(spec, include_off=("R7",) if "R7" in spec else ()),
                                          ctx or R.RuleContext())}


def without(data: bytes, *chunks: bytes) -> bytes:
    """``data`` with each chunk removed once, in order -- the exact expected result of a deletion."""
    for c in chunks:
        assert data.count(c) >= 1, c
        data = data.replace(c, b"", 1)
    return data


CONV_1 = b"\t\t\t\tconverging={\n\t\t\t\t\tdays=4709\n\t\t\t\t\topinion=20.6\n\t\t\t\t}\n"
CONV_2 = b"\t\t\t\tconverging={\n\t\t\t\t\ttotal_days=3650\n\t\t\t\t\tdays=1411\n\t\t\t\t\topinion=15\n\t\t\t\t}\n"


# --------------------------------------------------------------------------- R1
class TestR1:
    def test_deletes_every_converging_and_nothing_else(self, save):
        res = run(save, "R1")["R1"]
        assert (res.matched, res.edited) == (2, 2)
        assert save.gamestate == without(DATA, CONV_1, CONV_2)

    def test_idempotent(self, save):
        run(save, "R1")
        once = save.gamestate
        assert run(save, "R1")["R1"].edited == 0 and save.gamestate == once


# --------------------------------------------------------------------------- R2
class TestR2:
    def test_reencodes_lossless_values(self, save):
        res = run(save, "R2")["R2"]
        g = save.gamestate
        assert b'flags="AA=="' in g and b'flags="AQ=="' in g
        assert b'"AAAAAA=="' not in g and b'"AQAAAA=="' not in g
        assert (res.matched, res.edited) == (4, 2)
        assert res.extra["values"] == {'"AAAAAA=="': 1, '"AQAAAA=="': 1, '"AAEAAA=="': 1, '"Aw=="': 1}

    def test_high_byte_left_and_reported(self, save):
        res = run(save, "R2")["R2"]
        assert b'flags="AAEAAA=="' in save.gamestate
        assert [x["value"] for x in res.extra["left_unchanged"]] == ['"AAEAAA=="']
        assert res.extra["left_unchanged"][0]["kind"] == "friend"

    def test_only_flag_values_change(self, save):
        run(save, "R2")
        exp = DATA.replace(b'flags="AAAAAA=="', b'flags="AA=="').replace(b'flags="AQAAAA=="', b'flags="AQ=="')
        assert save.gamestate == exp


# --------------------------------------------------------------------------- R3
class TestR3:
    def test_moves_names_after_coat_of_arms(self, save):
        res = run(save, "R3")["R3"]
        g = save.gamestate
        assert (b"\tcoat_of_arms_id=7\n\ttitle_name_data={\n\t\tname=\"Papacy\"\n\t\tarticle=\"the \"\n"
                b"\t\tadj=\"Papal\"\n\t}\n\tdefault_coa=yes\n") in g
        assert b"\tholder=66845\n\tdate=976.3.4\n" in g             # inline keys gone, neighbours kept
        assert (b"\tcoat_of_arms_id=13\n\ttitle_name_data={\n\t\tname=\"Black Horde\"\n\t\tadj=\"Mongol\"\n"
                b"\t\tpre=\"Mongolo\"\n\t}\n}\n") in g
        assert res.matched == 3                                        # papal, black horde, the x_ dynamic
        inserts, deleted = 3, 3 + 3 + 1                                # papal name/adj/article, horde name/adj/pre, x_ name
        assert res.edited == inserts + deleted

    def test_title_without_coat_of_arms_gets_block_at_name_line(self, save):
        run(save, "R3")
        assert b'\tkey="x_x_1848"\n\ttitle_name_data={\n\t\tname="Dynamic"\n\t}\n\tdate=900.1.1\n' in save.gamestate

    def test_title_without_names_untouched(self, save):
        run(save, "R3")
        assert b'\tkey="d_knights_hospitaler"\n\tholder=500\n\tde_jure_liege=0\n\tcoat_of_arms_id=20\n}' \
            in save.gamestate

    def test_side_table(self, save):
        names = run(save, "R3")["R3"].extra["names"]
        assert names["k_papal_state"] == {"name": "Papacy", "adj": "Papal", "article": "the "}
        assert names["e_black_horde"] == {"name": "Black Horde", "adj": "Mongol", "pre": "Mongolo"}

    def test_rest_of_gamestate_untouched(self, save):
        lt = gs.locate(DATA, "landed_titles/landed_titles")
        run(save, "R3")
        g = save.gamestate
        new_lt = gs.locate(g, "landed_titles/landed_titles")
        assert g[:new_lt.open] == DATA[:lt.open]
        assert g[new_lt.close:] == DATA[lt.close:]


# --------------------------------------------------------------------------- R4
class TestR4:
    def test_blanks_removed_in_both_copies(self, save):
        res = run(save, "R4")["R4"]
        assert res.extra["blanks_removed"] == {"meta_data": 3, "top-level": 3}
        assert (res.matched, res.edited) == (2, 6)
        exp = DATA.replace(b'settings={ "" "" "" normal', b"settings={ normal") \
                  .replace(b'setting={ "" "" "" normal', b"setting={ normal")
        assert save.gamestate == exp

    def test_meta_copy_and_length_follow(self, save, tmp_path):
        run(save, "R4")
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert b'""' not in back.meta and back.header.meta_len == len(RULES_META) - 9 and back.warnings == []


# --------------------------------------------------------------------------- R5
class TestR5:
    def test_empty_keys_removed_everywhere(self, save):
        res = run(save, "R5")["R5"]
        assert res.matched == 2 and res.extra["by_parent"] == {"decision_cooldowns": 1, "interaction_cooldowns": 1}
        exp = DATA.replace(b"\t\tdecision_cooldowns={\n\t\t\t=-5000.1.1\n", b"\t\tdecision_cooldowns={\n", 1) \
                  .replace(b"\t\tinteraction_cooldowns={\n\t\t\t=-5000.1.1\n", b"\t\tinteraction_cooldowns={\n", 1)
        assert save.gamestate == exp

    def test_equals_at_line_start_inside_a_string_is_not_a_key(self, save):
        res = run(save, "R5")["R5"]
        assert b'desc="a line\n=not a key"' in save.gamestate
        assert res.extra["candidates"] == 3 and res.matched == 2


# --------------------------------------------------------------------------- R6
class TestR6:
    def test_dead_titles_reported(self, save, tmp_path):
        res = run(save, "R6", R.RuleContext(game_dir=make_game_dir(tmp_path / "game")))["R6"]
        dead = {d["key"]: d for d in res.extra["dead"]}
        assert set(dead) == {"e_black_horde"}                          # x_ skipped, hospitaler converted
        assert res.extra["converted_by_game"] == {"d_knights_hospitaler": "d_knights_hospitaller"}
        row = dead["e_black_horde"]
        assert row["id"] == "18" and row["ref_keys"].get("liege_title") == 1
        assert res.edited == 0 and save.gamestate == DATA

    def test_skipped_without_game_dir(self, save, tmp_path):
        res = run(save, "R6", R.RuleContext(game_dir=tmp_path / "nope"))["R6"]
        assert "skipped" in res.extra and res.matched == 0

    def test_commented_definitions_ignored(self, tmp_path):
        defined, conv = __import__("ck3_save_migrator.rules.to_1_20", fromlist=["x"]).defined_title_keys(
            make_game_dir(tmp_path / "game"))
        assert "k_papal_state" in defined and "k_commented_out" not in defined


# --------------------------------------------------------------------------- R7
class TestR7:
    def test_bump_both_copies(self, save, tmp_path):
        res = run(save, "R7")["R7"]
        assert res.extra["before"] == {"save_game_version": "8", "version": '"1.8.1"'}
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert b'version="1.20.1.2"' in back.meta and b"save_game_version=18" in back.meta
        assert b"portraits_version=3" in back.meta
        assert back.gamestate.startswith(back.meta) and back.warnings == []

    def test_portraits_only_when_given(self, save):
        run(save, "R7", R.RuleContext(portraits_version=5))
        assert b"portraits_version=5" in save.gamestate

    def test_r7_in_all_and_last(self):
        # A3 (2026-10-24): with save_game_version=8 the 1.20 loader runs a legacy conversion that
        # crashes; with 18 it reaches In Game -- so the bump is default-on and runs after everything
        ids = [r.id for r in R.select("all")]
        assert ids[-1] == "R7"


# --------------------------------------------------------------------------- registry
class TestRegistry:
    def test_select_by_id_and_name_in_registry_order(self):
        assert [r.id for r in R.select("title-names,R1")] == ["R1", "R3"]

    def test_unknown_rule(self):
        with pytest.raises(ValueError, match="unknown rule"):
            R.select("R99")

    def test_every_rule_documented(self):
        for r in R.REGISTRY:
            assert r.name and r.since and r.description and r.apply.__doc__

    def test_registry_order_is_dependency_order(self):
        assert [r.id for r in R.REGISTRY] == ["R1", "R2", "R3", "R4", "R5", "R6", "R11", "R8", "R10", "R9", "R12",
                                              "R15", "R14", "R16", "R17", "R7"]

    def test_transplant_rules_are_opt_in_and_bring_the_write_step(self):
        assert "R14" not in [r.id for r in R.select("all")]
        assert [r.id for r in R.select("R14")] == ["R14", "R17"]
        assert [r.id for r in R.select("all", include_off=("new-titles",))][-3:] == ["R14", "R17", "R7"]

    def test_all_rules_compose(self, save, tmp_path):
        res = R.run_rules(save, R.select("all"), R.RuleContext(game_dir=make_game_dir(tmp_path / "g")))
        assert [r.id for r in res] == ["R1", "R2", "R3", "R4", "R5", "R6", "R11", "R8", "R10", "R9", "R12", "R7"]
        assert all("skipped" in r.extra for r in res if r.id in ("R8", "R10", "R9", "R12"))   # no reference
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert back.warnings == []
        for gone in (b"converging", b'"AAAAAA=="', b'\n\tname="Papacy"', b'""', b"\t=-5000"):
            assert gone not in back.gamestate


# --------------------------------------------------------------------------- CLI
def cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "ck3_save_migrator", *args], capture_output=True, text=True, cwd=ROOT)


class TestCLI:
    def test_migrate_rules_report(self, tmp_path):
        src = tmp_path / "in.ck3"
        src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
        game = make_game_dir(tmp_path / "game")
        r = cli("migrate", str(src), "--rules", "all", "--report", str(tmp_path / "r.json"),
                "--game-dir", str(game), "--reference", "none", "-o", str(tmp_path / "out.ck3"))
        assert r.returncode == 0, r.stderr
        rep = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
        assert [x["id"] for x in rep["rules"]] == ["R1", "R2", "R3", "R4", "R5", "R6", "R11", "R8", "R10", "R9", "R12", "R7"]
        assert not list(tmp_path.glob("*__wos-*"))          # no reference -> no branch, one output
        assert rep["rules"][0]["edited"] == 2 and rep["output_sha256"] == sf.sha256((tmp_path / "out.ck3").read_bytes())

    def test_bump_version_flag(self, tmp_path):
        src = tmp_path / "in.ck3"
        src.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
        r = cli("migrate", str(src), "--bump-version", "--reference", "none", "-o", str(tmp_path / "out.ck3"))
        assert r.returncode == 0, r.stderr
        assert b'version="1.20.1.2"' in sf.read_save(tmp_path / "out.ck3").meta

    def test_unknown_rule_exit_1(self, tmp_path):
        src = tmp_path / "in.ck3"
        src.write_bytes(build_ck3())
        assert cli("migrate", str(src), "--rules", "R99", "-o", str(tmp_path / "o.ck3")).returncode == 1

    def test_rules_listing(self):
        r = cli("rules")
        assert r.returncode == 0 and all(i in r.stdout for i in ("R7", "R8", "R10", "R12"))


# --------------------------------------------------------------------------- real save (opt-in)
@pytest.mark.skipif(not (REAL_987.exists() and GAME.exists() and os.environ.get("CK3_REAL_SAVES") == "1"),
                    reason="set CK3_REAL_SAVES=1 (needs private/data and the game install; ~50 s)")
def test_real_987_counts():
    save = sf.read_save(REAL_987)
    res = {r.id: r for r in R.run_rules(save, R.select("all", include_off=("R7",)), R.RuleContext(game_dir=GAME))}
    assert (res["R1"].matched, res["R1"].edited) == (76433, 76433)
    assert (res["R2"].matched, res["R2"].edited, len(res["R2"].extra["left_unchanged"])) == (48357, 48357, 0)
    assert (res["R3"].matched, res["R3"].edited) == (12702, 12702 + 12702 + 3508 + 45 + 43)
    assert res["R4"].extra["blanks_removed"] == {"meta_data": 69, "top-level": 69}
    assert res["R5"].extra["by_parent"] == {"decision_cooldowns": 98, "interaction_cooldowns": 1}
    assert len(res["R6"].extra["dead"]) == 96
    assert res["R6"].extra["converted_by_game"] == {"d_knights_hospitaler": "d_knights_hospitaller"}
    assert res["R7"].edited == 2
