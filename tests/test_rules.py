"""Tests for the unit-3 migration rules (R1-R7) and their CLI.

Synthetic saves only (tests/fixtures/make_ck3.py RULES_META/RULES_BODY), plus one
real-save run of every rule, opt-in with CK3_REAL_SAVES=1 because it takes ~50 s.
"""

from __future__ import annotations

import json
import os
import re
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
    @staticmethod
    def blanks(g: bytes) -> dict:
        """The "" tokens in meta_data's game_rules and in the top-level game_rules section(s)."""
        meta = gs.find_child(g, gs.find_section(g, "meta_data"), "game_rules")
        top = list(gs.find_sections(g, "game_rules"))
        return {"meta_data": g[meta.open:meta.close].count(b'""'),
                "top-level": sum(g[b.open:b.close].count(b'""') for b in top)}

    def test_blanks_removed_in_both_copies(self, save):
        res = run(save, "R4")["R4"]
        # (the Python rule reported this as extra["blanks_removed"]; the patch's output shows it)
        before, after = self.blanks(DATA), self.blanks(save.gamestate)
        assert {k: before[k] - after[k] for k in before} == {"meta_data": 3, "top-level": 3}
        assert after == {"meta_data": 0, "top-level": 0}
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
        # (the Python rule reported extra["by_parent"] == {"decision_cooldowns": 1, "interaction_cooldowns": 1})
        for parent in (b"decision_cooldowns", b"interaction_cooldowns"):
            entry = parent + b"={\n\t\t\t=-5000.1.1\n"
            assert (DATA.count(entry), save.gamestate.count(entry)) == (1, 0), parent
        assert res.matched == 2 and res.edited == 2
        exp = DATA.replace(b"\t\tdecision_cooldowns={\n\t\t\t=-5000.1.1\n", b"\t\tdecision_cooldowns={\n", 1) \
                  .replace(b"\t\tinteraction_cooldowns={\n\t\t\t=-5000.1.1\n", b"\t\tinteraction_cooldowns={\n", 1)
        assert save.gamestate == exp

    def test_equals_at_line_start_inside_a_string_is_not_a_key(self, save):
        res = run(save, "R5")["R5"]
        assert b'desc="a line\n=not a key"' in save.gamestate
        # (the Python rule reported extra["candidates"] == 3: three lines begin with '=', two of them keys)
        assert len(re.findall(rb"(?m)^[ \t]*=", DATA)) == 3 and res.matched == 2


# --------------------------------------------------------------------------- R21
DEAD = (b"dead_unprunable={\n"
        b"2974={\n\tfirst_name=\"Al-Mansur\"\n\tdead_data={\n\t\tdate=775.1.1\n\t\tliege=3595\n"
        b"\t\tliege_title=8061\n\t\tdomain={ 8061 11 }\n\t}\n}\n"
        b"3595={\n\tfirst_name=\"Al-Mahdi\"\n\tdead_data={\n\t\tdate=785.1.1\n\t\tliege=2974\n"
        b"\t\tdomain={ 8061 11 }\n\t}\n}\n"
        b"10={\n\tfirst_name=\"Indep\"\n\tdead_data={\n\t\tdate=800.1.1\n\t\tliege=10\n\t}\n}\n"
        b"11={\n\tfirst_name=\"Vassal\"\n\tdead_data={\n\t\tdate=801.1.1\n\t\tliege=10\n\t\tliege_title=5\n\t}\n}\n"
        b"}\n")


class TestR21:
    @pytest.fixture
    def dsave(self, tmp_path):
        p = tmp_path / "dead.ck3"
        p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY + DEAD))
        return sf.read_save(p)

    def test_drops_the_liege_of_dead_characters_on_a_loop_only(self, dsave):
        """The 1.8.1 campaign's Al-Mansur <-> Al-Mahdi loop is broken; a self-liege (how 1.20 writes a ruler who
        died independent) and a vassal whose chain ends at him are left alone."""
        res = run(dsave, "R21")["R21"]
        assert res.matched == 2 and res.extra["characters"] == [2974, 3595] and res.edited == 3
        exp = without(RULES_BODY + DEAD, b"\t\tliege=3595\n", b"\t\tliege_title=8061\n", b"\t\tliege=2974\n")
        assert dsave.gamestate.endswith(exp[-len(DEAD) + 25:])
        assert b"liege=10\n\t}" in dsave.gamestate and b"liege=10\n\t\tliege_title=5" in dsave.gamestate

    def test_a_second_run_changes_nothing(self, dsave):
        run(dsave, "R21")
        before = dsave.gamestate
        res = run(dsave, "R21")["R21"]
        assert res.matched == 0 and res.edited == 0 and dsave.gamestate == before


# --------------------------------------------------------------------------- R20
AI = (b"ai={\n\twar_coordinator_db={\n"
      b"\t\t10={\n\t\t\twar=1\n\t\t\tsupply_limit=0\n\t\t\tgarrison_limit=0\n\t\t\tstack_size=0\n\t\t}\n"       # never run
      b"\t\t11={\n\t\t\twar=2\n\t\t\twar_stance=\"defender_defensive\"\n\t\t\tsupply_limit=2400\n\t\t}\n"   # run
      b"\t}\n\twar_plan_db={\n"
      b"\t\t20={\n\t\t\twar=1\n\t\t\twar_coordinator=10\n\t\t\towner=5\n\t\t}\n"
      b"\t\t21={\n\t\t\twar=2\n\t\t\twar_coordinator=11\n\t\t\towner=5\n\t\t}\n"
      b"\t\t22={\n\t\t\twar=1\n\t\t\twar_coordinator=10\n\t\t\towner=6\n\t\t}\n\t}\n"
      b"\tai_strategies={\n"
      b"\t\t5={\n\t\t\tadvanced_ai_data={\n\t\t\t\twar_plans={ 20 21 }\n\t\t\t\tbudget_reserved=0\n\t\t\t}\n\t\t}\n"
      b"\t\t6={\n\t\t\tadvanced_ai_data={\n\t\t\t\twar_plans={ 22 }\n\t\t\t\tbudget_reserved=0\n\t\t\t}\n\t\t}\n"
      b"\t}\n}\n")


class TestR20:
    @pytest.fixture
    def asave(self, tmp_path):
        p = tmp_path / "ai.ck3"
        p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY + AI))
        return sf.read_save(p)

    def test_drops_never_run_coordinators_their_plans_and_the_plans_in_strategies(self, asave):
        """The 1.8.1 campaign's never-run coordinators (no stance, supply limit 0) made 1.20's AI split an army
        stack without end; a plan left listed in a strategy crashed the load. A run coordinator and its plan stay;
        a strategy list that empties goes, as 1.20 never writes an empty one."""
        res = run(asave, "R20")["R20"]
        assert res.matched == 1 and res.extra == {"coordinators": [10], "war_plans": [20, 22], "strategy_lists": 2}
        g = asave.gamestate
        assert b"\t\t10={" not in g and b"\t\t20={" not in g and b"\t\t22={" not in g
        assert b"\t\t11={" in g and b"\t\t21={" in g
        assert b"war_plans={ 21 }" in g                                   # 20 dropped, 21 kept
        assert g.count(b"war_plans=") == 1                                # character 6's list emptied and removed
        assert g.count(b"budget_reserved=0") == 2                         # nothing else in the strategies touched

    def test_a_second_run_changes_nothing(self, asave):
        run(asave, "R20")
        before = asave.gamestate
        res = run(asave, "R20")["R20"]
        assert res.matched == 0 and res.edited == 0 and asave.gamestate == before


# --------------------------------------------------------------------------- R22
UNITS = (b"units={\n"
         b"\t1744830531={\n\t\ttype=army\n\t\tlocation=9542\n\t\tprev=9539\n\t\tpath={ 9541 }\n\t\ttotal_cost=4.5\n"
         b"\t\tmovement_progress=1.2\n\t\towner=5\n\t\tarmy=7\n\t}\n"
         b"\t2={\n\t\ttype=army\n\t\tlocation=9508\n\t\tprev=9507\n\t\towner=6\n\t\tarmy=8\n\t}\n"
         b"\t3={\n\t\ttype=army\n\t\tlocation=9600\n\t\tprev=9601\n\t\towner=6\n\t\tarmy=9\n\t}\n"
         b"}\n")
MAP = ("impassable_mountains = LIST { 10468 9542 }\nimpassable_seas = RANGE { 9600 9601 }\n"
       "sea_zones = RANGE { 632 641 }\n")


class TestR22:
    @pytest.fixture
    def usave(self, tmp_path):
        p = tmp_path / "units.ck3"
        p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY + UNITS))
        return sf.read_save(p)

    @pytest.fixture
    def game(self, tmp_path):
        g = make_game_dir(tmp_path / "g")
        (g / "map_data").mkdir(parents=True, exist_ok=True)
        (g / "map_data" / "default.map").write_text(MAP, encoding="utf-8")
        return g

    def test_moves_a_unit_off_an_impassable_province_to_where_it_came_from(self, usave, game):
        """2026-10-27: an army on province 9542, land in 1.8.1 and impassable mountains in 1.20, crashed the game
        when its owner was a landed ruler (989.1.1, ck3+0xb064e8). It goes back to its prev province, its
        unfinished path dropped; a unit on passable land stays; one whose prev is impassable too is reported."""
        res = R.run_rules(usave, R.select("R22"), R.RuleContext(game_dir=game))[0]
        assert res.extra["moved"] == [{"unit": 1744830531, "from": 9542, "to": 9539}]
        assert res.extra["left"] == [{"unit": 3, "location": 9600}]
        g = usave.gamestate
        unit = g[g.index(b"1744830531={"):g.index(b"\t2={")]
        assert b"location=9539" in unit and b"path=" not in unit and b"total_cost" not in unit
        assert b"movement_progress" not in unit and b"prev=9539" in unit and b"owner=5" in unit
        assert b"location=9508" in g                                      # passable: untouched

    def test_clears_the_old_holding_its_pools_regiments_and_siege(self, tmp_path, game):
        """2026-10-27: moving the army alone did not stop the 989.1.1 crash: the save kept 1.8.1's castle on 9542,
        with its levy and garrison pools, a regiment drawing on one, and a siege of it. A 1.20 game has an empty
        holding there. The holding becomes that, the fort goes, the pools go, a regiment drawing only on them goes
        and leaves its army's list, one drawing on others too loses just that chunk, and the siege goes."""
        prov = (b"provinces={\n\t9542={\n\t\tholding={\n\t\t\ttype=\"castle_holding\"\n\t\t\tbuildings={ {\n"
                b"\t\t\t\t\ttype=\"castle_01\"\n\t\t\t\t}\n }\n\t\t\tlevy=50\n\t\t\tgarrison=51\n\t\t\tincome=0.5\n"
                b"\t\t}\n\t\tfort_level=2\n\t\twinter_severity=0.2\n\t}\n"
                b"\t9539={\n\t\tholding={\n\t\t\ttype=\"church_holding\"\n\t\t\tlevy=60\n\t\t}\n\t\tfort_level=1\n\t}\n}\n")
        armies = (b"armies={\n\tregiments={\n\t\t50={\n\t\t\torigin=9542\n\t\t\tmax=174\n\t\t}\n"
                  b"\t\t51={\n\t\t\torigin=9542\n\t\t\tsize=250\n\t\t\tsource=garrison\n\t\t}\n"
                  b"\t\t60={\n\t\t\torigin=9539\n\t\t\tmax=100\n\t\t}\n\t}\n"
                  b"\tarmy_regiments={\n\t\t70={\n\t\t\tchunks={ {\n\t\t\t\t\tregiment=50\n\t\t\t\t}\n }\n"
                  b"\t\t\tarmy=80\n\t\t}\n"
                  b"\t\t71={\n\t\t\tchunks={ {\n\t\t\t\t\tregiment=50\n\t\t\t\t}\n {\n\t\t\t\t\tregiment=60\n"
                  b"\t\t\t\t}\n }\n\t\t\tarmy=80\n\t\t}\n\t}\n"
                  b"\tarmies={\n\t\t80={\n\t\t\tregiments={ 70 71 }\n\t\t\tunit=1744830531\n\t\t}\n\t}\n}\n")
        sieges = (b"sieges={\n\tsieges={\n\t\t90={\n\t\t\tprovince=9542\n\t\t\tprogress=188\n\t\t}\n"
                  b"\t\t91={\n\t\t\tprovince=9539\n\t\t\tprogress=3\n\t\t}\n\t}\n}\n")
        p = tmp_path / "prov.ck3"
        p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY + UNITS + prov + armies + sieges))
        s = sf.read_save(p)
        res = R.run_rules(s, R.select("R22"), R.RuleContext(game_dir=game))[0]
        ex = res.extra
        assert ex["holdings"] == [9542] and ex["pools"] == [50, 51] and ex["regiments"] == [70]
        assert ex["chunks"] == 1 and ex["sieges"] == [90]
        g = s.gamestate
        p9542 = g[g.index(b"\t9542={"):g.index(b"\t9539={")]
        assert b"type=" not in p9542 and b"levy=" not in p9542 and b"fort_level" not in p9542
        assert b"income=0\n" in p9542 and b"winter_severity=0.2" in p9542
        assert b"church_holding" in g and b"fort_level=1" in g                    # a passable province stays
        assert b"\t\t50={" not in g and b"\t\t51={" not in g and b"\t\t60={" in g
        assert b"\t\t70={" not in g and b"regiments={ 71 }" in g
        r71 = g[g.index(b"\t\t71={"):g.index(b"\tarmies={\n\t\t80")]
        assert b"regiment=50" not in r71 and b"regiment=60" in r71
        assert b"\t\t90={" not in g and b"\t\t91={" in g
        assert R.run_rules(s, R.select("R22"), R.RuleContext(game_dir=game))[0].edited == 0     # idempotent

    def test_aims_a_council_task_at_a_passable_barony_of_its_court_owner(self, tmp_path, game):
        """The 989.1.1 crash itself: 50350018's task_increase_control aimed at 9542; when the game appointed a
        councillor at New Year it filed the task under the province, whose title link was stale. The task is aimed
        at the province of the court owner's first barony that the map lets anyone stand on."""
        (game / "common" / "landed_titles").mkdir(parents=True, exist_ok=True)
        (game / "common" / "landed_titles" / "00_test.txt").write_text(
            "c_x = {\n\tb_gone = { province = 9542 }\n\tb_keep = { province = 9541 }\n}\n", encoding="utf-8")
        body = (b"landed_titles={\n\tlanded_titles={\n0={\n\tkey=b_gone\n\tholder=5\n}\n1={\n\tkey=b_keep\n"
                b"\tholder=5\n}\n\t}\n}\n"
                b"living={\n5={\n\tfirst_name=\"P5\"\n\tlanded_data={\n\t\tdomain={ 0 1 }\n\t}\n}\n}\n"
                b"council_task_manager={\n\tactive={\n\t\t83888785={\n\t\t\ttype=\"task_increase_control\"\n"
                b"\t\t\tcourt_owner=5\n\t\t\ttarget={\n\t\t\t\ttype=prov\n\t\t\t\tidentity=9542\n\t\t\t}\n\t\t}\n"
                b"\t\t7={\n\t\t\ttype=\"task_collect_taxes\"\n\t\t\tcourt_owner=5\n\t\t}\n\t}\n}\n")
        p = tmp_path / "task.ck3"
        p.write_bytes(build_ck3(meta=RULES_META, body=body))
        s = sf.read_save(p)
        res = R.run_rules(s, R.select("R22"), R.RuleContext(game_dir=game))[0]
        assert res.extra["tasks"] == [{"task": 83888785, "from": 9542, "to": 9541}]
        assert b"identity=9541" in s.gamestate and b"identity=9542" not in s.gamestate

    def test_without_a_game_folder_it_changes_nothing(self, usave):
        before = usave.gamestate
        res = R.run_rules(usave, R.select("R22"), R.RuleContext())[0]
        assert res.edited == 0 and "skipped" in res.extra and usave.gamestate == before


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
        # (the Python rule reported extra["before"] == {"save_game_version": "8", "version": '"1.8.1"'}): the two
        # values it replaced, each found once and set
        meta = gs.find_section(DATA, "meta_data")
        old = {c.key.decode(): DATA[c.value_start:c.value_end].decode() for c in gs.iter_children(DATA, *meta.body)
               if c.key in (b"version", b"save_game_version")}
        assert old == {"save_game_version": "8", "version": '"1.8.1"'}
        rows = {r["edit"]: (r["found"], r["edits"]) for r in res.extra["edits"] if "skipped" not in r}
        assert rows == {1: (1, 1), 2: (1, 1)} and (res.matched, res.edited) == (2, 2)
        sf.write_save(save, tmp_path / "o.ck3")
        back = sf.read_save(tmp_path / "o.ck3")
        assert b'version="1.20.1.2"' in back.meta and b"save_game_version=18" in back.meta
        assert b"portraits_version=3" in back.meta
        assert back.gamestate.startswith(back.meta) and back.warnings == []

    def test_r7_never_sets_portraits_version(self, save):
        """R19 stamps the target's portraits_version with the faces it carries (S4 i); R7 no longer touches it."""
        run(save, "R7", R.RuleContext(portraits_version=5))
        assert b"portraits_version=3" in save.gamestate and b"portraits_version=5" not in save.gamestate

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
        assert [r.id for r in R.REGISTRY] == ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9",
                                              "R12", "R23", "R15", "R14", "R16", "R17", "R19", "R25", "R26", "R27", "R28", "R7"]

    def test_transplant_rules_are_opt_in_and_bring_the_write_step(self):
        assert "R14" not in [r.id for r in R.select("all")]
        assert [r.id for r in R.select("R14")] == ["R14", "R17"]
        assert [r.id for r in R.select("all", include_off=("new-titles",))][-8:] == ["R14", "R17", "R19", "R25", "R26", "R27", "R28", "R7"]

    def test_all_rules_compose(self, save, tmp_path):
        res = R.run_rules(save, R.select("all"), R.RuleContext(game_dir=make_game_dir(tmp_path / "g")))
        assert [r.id for r in res] == ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9", "R12",
                                       "R23", "R19", "R25", "R26", "R27", "R28", "R7"]
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
        assert [x["id"] for x in rep["rules"]] == ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9",
                                                   "R12", "R23", "R19", "R25", "R26", "R27", "R28", "R7"]
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
    # 142 scholar_perk, 11 teutonic_knights, 247 artifact scheme-power modifiers, 1 Hawk of Quarysh (2026-11-04, U4)
    # + HOLD answers (S1): 25 chu_ko_nu, 229 innovation_bombard, 49 medium_animal_hide, 5 artifact bonus steps
    # + item 6 (S2): 12 at +1, 1 at +3, 26 at +4 (the six at +2 wait on djdarcy's look)
    assert (res["R25"].matched, res["R25"].edited, res["R25"].extra["left"]) == (748, 748, {})
    assert (res["R1"].matched, res["R1"].edited) == (76433, 76433)
    assert (res["R2"].matched, res["R2"].edited, len(res["R2"].extra["left_unchanged"])) == (48357, 48357, 0)
    assert (res["R3"].matched, res["R3"].edited) == (12702, 12702 + 12702 + 3508 + 45 + 43)
    assert res["R4"].extra["blanks_removed"] == {"meta_data": 69, "top-level": 69}
    assert res["R5"].extra["by_parent"] == {"decision_cooldowns": 98, "interaction_cooldowns": 1}
    assert len(res["R6"].extra["dead"]) == 96
    assert res["R6"].extra["converted_by_game"] == {"d_knights_hospitaler": "d_knights_hospitaller"}
    assert res["R7"].edited == 2


# --------------------------------------------------------------------------- selection and prerequisites (S1)
def test_all_with_opt_ins_selects_the_defaults_plus_those_and_meets_every_prerequisite():
    """S1 (director 2026-10-26 00:45): ``all,R14,R15,R16`` is the defaults plus the transplant, in registry order,
    with the write step (R17) brought along; such a selection lacks no prerequisite."""
    ids = [r.id for r in R.select("all,R14,R15,R16")]
    assert ids == ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9", "R12", "R23", "R15", "R14",
                   "R16", "R17", "R19", "R25", "R26", "R27", "R28", "R7"]
    assert R.missing_prerequisites(R.select("all,R14,R15,R16")) == []


def test_a_selection_missing_prerequisites_names_them():
    assert R.missing_prerequisites(R.select("R15")) == [("R15", ["R14", "R16"])]
    assert R.missing_prerequisites(R.select("R9,R12")) == [("R9", ["R8", "R10"]), ("R12", ["R8"])]
    assert R.missing_prerequisites(R.select("all")) == []


def test_an_empty_selection_is_refused_and_none_selects_nothing():
    with pytest.raises(ValueError, match="empty rule selection"):
        R.select("  ")
    assert R.select(None) == []
