"""Tests for the religion rules R8-R12 (and R11) on synthetic old/reference saves (tests/fixtures/religion.py)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.religion import OLD_BODY, OLD_META, REF_BODY, REF_META

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def paths(tmp_path):
    old = tmp_path / "old.ck3"
    ref = tmp_path / "ref.ck3"
    old.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    ref.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
    return old, ref


def run(paths, ids, shape="faith"):
    old, ref = paths
    save = sf.read_save(old)
    ctx = R.RuleContext(reference=ref, wos_shape=shape)
    res = {r.id: r for r in R.run_rules(save, R.select(ids), ctx)}
    return save, res, ctx


def entry(g, path, key):
    return next(e for e in gs.iter_entries(g, *gs.locate(g, path).body) if e.key == key)


def val(g, block, key):
    h = gs.find_keys(g, block, key)
    return g[h[0].value_start:h[0].value_end].decode() if h else None


# --------------------------------------------------------------------------- R11
class TestR11:
    def test_counts_and_targets(self, paths):
        save, res, _ = run(paths, "R11")
        # (the Python rule reported extra["by_kind"] == {"modifier blocks": 1, "modifiers list entries": 1, "type": 1};
        # the patch's three edits are those three kinds, in that order)
        assert [(r["edit"], r["edits"]) for r in res["R11"].extra["edits"]] == [(1, 1), (2, 1), (3, 1)]
        assert (res["R11"].matched, res["R11"].edited) == (3, 3)
        g = save.gamestate
        assert b'modifier=""' not in g and b'type=""' not in g
        assert b'modifier="real_modifier"' in g                      # the named one stays
        assert b"modifiers={ artifact_monthly_prestige }" in g

    def test_rest_untouched(self, paths):
        save, _, _ = run(paths, "R11")
        exp = OLD_META + OLD_BODY
        exp = exp.replace(b"\t\tmodifier={\n\t\t\tmodifier=\"\"\n\t\t\texpiration_date=9999.1.1\n\t\t}\n", b"", 1)
        exp = exp.replace(b"\t\t\ttype=\"\"\n", b"", 1).replace(b'modifiers={ "" artifact', b"modifiers={ artifact", 1)
        assert save.gamestate == exp


# --------------------------------------------------------------------------- R8
class TestR8:
    def test_layout_replaced(self, paths):
        save, res, ctx = run(paths, "R8")
        g = save.gamestate
        rel = gs.find_section(g, "religion")
        assert not gs.find_keys(g, rel, "faiths")                    # old database gone
        for sec in ("faiths", "rites", "organization_manager"):
            assert len(list(gs.find_sections(g, sec))) == 1
        assert set(ctx.state["old_faiths"]) == {"0", "1", "2", "3", "4"}   # 4 = insular_celtic (option B)

    def test_titles_remapped_by_key(self, paths):
        save, res, _ = run(paths, "R8")
        g = save.gamestate
        assert val(g, entry(g, "faiths/database", b"2"), "religious_head") == "0"   # d_sunni: ref 50 -> ours 0
        assert val(g, entry(g, "religion/holy_sites", b"0"), "barony") == "2"       # b_jerusalem: 51 -> 2
        assert res["R8"].extra["faith_heads"] == {"sunni": "d_sunni"}

    def test_missing_barony_dropped_inactive_and_typed_lost(self, paths):
        save, res, _ = run(paths, "R8")
        g = save.gamestate
        hs = entry(g, "religion/holy_sites", b"1")
        assert val(g, hs, "barony") is None and val(g, hs, "is_active") == "no"
        lost = res["R8"].extra["lost"]
        assert {"what": "holy_site_barony", "index": "1", "type": "samarkand", "barony": "b_samarkand"} in lost
        assert any(l["what"] == "great_holy_war" for l in lost)

    def test_reference_world_ids_cleared(self, paths):
        save, res, _ = run(paths, "R8")
        g = save.gamestate
        hs0 = entry(g, "religion/holy_sites", b"0")
        body = g[hs0.open:hs0.end]
        assert b"equipped" not in body and b"total_artifact_rarity" not in body and b"artifacts={ }" in body
        assert val(g, entry(g, "rites/database", b"0"), "head_of_rite") == "4294967295"
        f0 = entry(g, "faiths/database", b"0")
        assert val(g, f0, "saints") is None
        assert g[f0.open:f0.end].count(b"inactive_clerical_electors={ }") == 1 or b"53" not in g[f0.open:f0.end]
        assert b"character=900" not in g                              # faiths/saints emptied
        assert b"coat_of_arms_id=3242" not in g

    def test_cultures_remapped_or_dropped(self, paths):
        save, res, _ = run(paths, "R8")
        g = save.gamestate
        r0 = entry(g, "rites/database", b"0")
        assert re.search(rb"cultures=\{\s*0\s*\}", g[r0.open:r0.end])          # greek 7 -> 0, trojan dropped
        assert res["R8"].extra["stats"]["rite cultures dropped"] == 1

    def test_skips_without_reference(self, paths):
        old, _ = paths
        save = sf.read_save(old)
        r = R.run_rules(save, R.select("R8"), R.RuleContext())[0]
        assert "skipped" in r.extra and save.gamestate == OLD_META + OLD_BODY

    def test_skips_when_already_1_20_layout(self, paths):
        _, ref = paths
        save = sf.read_save(ref)
        r = R.run_rules(save, R.select("R8"), R.RuleContext(reference=ref))[0]
        assert "already" in r.extra["skipped"]


# --------------------------------------------------------------------------- R10, faith shape
class TestR10Faith:
    def test_new_faith_rite_org_and_religion(self, paths):
        save, res, ctx = run(paths, "R8,R10", "faith")
        g = save.gamestate
        rec = res["R10"].extra["custom"]["2"]
        assert (rec["faith_id"], rec["rite_id"], rec["organization_id"], rec["religion_id"]) == (3, 4, 3, "0")
        f = entry(g, "faiths/database", b"3")
        assert val(g, f, "name") == '"Way of Scarcity"' and val(g, f, "historical") == "no"
        assert val(g, f, "main_rite") == "4" and val(g, f, "organization") == "3"
        assert val(g, f, "fervor") == "75.5"                        # carried from the save
        assert val(g, f, "religious_head") == "1"                    # x_x_599, our numbering, unchanged
        assert rec["religious_head"] == {"id": "1", "title": "x_x_599"}
        r = entry(g, "rites/database", b"4")
        assert val(g, r, "faith") == "3" and gs.find_keys(g, r, "rite_type") == []
        assert val(g, entry(g, "organization_manager/database", b"3"), "faith") == "3"
        rel = entry(g, "religion/religions", b"0")
        assert re.search(rb"faiths=\{ 0 1 3 \}", g[rel.open:rel.end])
        assert ctx.state["custom_rites"] == {"2": "4"}

    def test_doctrines_kept_and_dropped(self, paths):
        save, res, _ = run(paths, "R8,R10", "faith")
        g = save.gamestate
        f = entry(g, "faiths/database", b"3")
        body = g[f.open:f.end]
        assert b"tenet=tenet_gnosticism" in body and b"doctrine=doctrine_gender_equal" in body
        assert b"doctrine_bogus_gone" not in body
        assert res["R10"].extra["custom"]["2"]["dropped_doctrines"] == ["doctrine_bogus_gone"]

    def test_holy_sites_by_template(self, paths):
        save, res, _ = run(paths, "R8,R10", "faith")
        g = save.gamestate
        f = entry(g, "faiths/database", b"3")
        assert val(g, f, "holy_sites") == "{ 0 2 }"                   # jerusalem 0, iona 2; armagh lost
        assert re.search(rb"faiths=\{ 0 1 3 \}", g[entry(g, "religion/holy_sites", b"0").open:])
        iona = entry(g, "religion/holy_sites", b"2")
        assert b"faiths={ 3 }" in g[iona.open:iona.end]            # created: the reference had no list
        assert {"what": "holy_site_type", "faith": "Way of Scarcity", "template": "armagh",
                "why": "not a 1.20 holy site type"} in res["R10"].extra["lost"]

    def test_lineage_origin_changes_founder(self, paths):
        save, res, _ = run(paths, "R8,R10", "faith")
        g = save.gamestate
        f = entry(g, "faiths/database", b"3")
        assert val(g, f, "origin") == "0"                             # christian_faith: insular_celtic's faith
        ch = gs.find_keys(g, f, "changes")[0].block
        body = g[ch.open:ch.close + 1]
        assert body.count(b'="') == 2 and b"Mended the schism" in body and b"Omni Heresy } {x}" in body
        assert val(g, f, "historical") == "no"                       # the faith block still closes properly
        assert val(g, entry(g, "rites/database", b"4"), "founder") == "21"   # Kin, dead_unprunable
        rec = res["R10"].extra["custom"]["2"]
        assert rec["founder"] == {"id": "21", "kept": True, "found_in": "dead_unprunable"}
        assert rec["changes_entries"] == 2 and rec["origin_faith"] == "0"
        assert not [x for x in res["R10"].extra["lost"] if x["what"] in ("founder", "faith_changes")]

    @pytest.mark.parametrize("shape", ["faith", "rite"])
    def test_missing_founder_not_written(self, tmp_path, shape):
        old, ref = tmp_path / "old.ck3", tmp_path / "ref.ck3"
        old.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY.replace(b"founder=21", b"founder=99")))
        ref.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
        save, res, _ = run((old, ref), "R8,R10", shape)
        g = save.gamestate
        assert val(g, entry(g, "rites/database", b"4"), "founder") == "4294967295"
        assert res["R10"].extra["custom"]["2"]["founder"] == {"id": "99", "kept": False, "found_in": None}
        assert {"what": "founder", "faith": "Way of Scarcity", "character": "99",
                "why": "not in living or dead_unprunable"} in res["R10"].extra["lost"]


# --------------------------------------------------------------------------- R10, rite shape
class TestR10Rite:
    def test_new_rite_of_parent_faith(self, paths):
        save, res, ctx = run(paths, "R8,R10", "rite")
        g = save.gamestate
        rec = res["R10"].extra["custom"]["2"]
        assert (rec["rite_id"], rec["faith_id"], rec["origin_rite"]) == (4, "0", "1")
        r = entry(g, "rites/database", b"4")
        assert val(g, r, "faith") == "0" and val(g, r, "origin_rite") == "1"
        data = gs.find_keys(g, r, "data")[0].block
        assert val(g, data, "fervor") == "50" and val(g, data, "name") == '"Way of Scarcity"'
        assert ctx.state["custom_rites"] == {"2": "4"}

    def test_no_faith_no_org_no_holy_sites(self, paths):
        save, res, _ = run(paths, "R8,R10", "rite")
        g = save.gamestate
        assert len(list(gs.iter_entries(g, *gs.locate(g, "faiths/database").body))) == 3
        assert len(list(gs.iter_entries(g, *gs.locate(g, "organization_manager/database").body))) == 3
        assert b"faiths={ 0 1 }" in g
        assert [x["what"] for x in res["R10"].extra["lost"]] == ["faith_changes"]   # nothing else lost

    def test_founder_on_rite_history_reported_lost(self, paths):
        save, res, _ = run(paths, "R8,R10", "rite")
        g = save.gamestate
        assert val(g, entry(g, "rites/database", b"4"), "founder") == "21"
        assert gs.find_keys(g, entry(g, "rites/database", b"4"), "changes") == []
        assert {"what": "faith_changes", "faith": "Way of Scarcity", "entries": 2,
                "why": "1.20 rites keep no change history (the faith shape carries it)"} in res["R10"].extra["lost"]

    def test_bad_shape_refused(self, paths):
        with pytest.raises(ValueError, match="shape"):
            run(paths, "R8,R10", "nonsense")


# --------------------------------------------------------------------------- R9
class TestR9:
    @pytest.mark.parametrize("shape,wos_faith", [("faith", "3"), ("rite", "0")])
    def test_table(self, paths, shape, wos_faith):
        save, res, _ = run(paths, "R8,R10,R9", shape)
        t = res["R9"].extra["table"]
        # option B: old catholic -> 1.20's catholic faith (1) and its main rite (3), not christian_faith/roman_rite
        assert (t["0"]["how"], t["0"]["rite_id"], t["0"]["faith_type"]) == ("faith_type main_rite", "3", "catholic")
        assert (t["1"]["how"], t["1"]["rite_id"]) == ("rite_type", "1")
        assert (t["2"]["how"], t["2"]["rite_id"], t["2"]["faith_id"]) == ("custom (R10)", "4", wos_faith)
        assert (t["3"]["how"], t["3"]["rite_id"], t["3"]["faith_type"]) == ("override -> shafii", "2", "sunni")

    def test_swaps_everywhere(self, paths):
        save, res, _ = run(paths, "R8,R10,R9", "faith")
        g = save.gamestate
        assert val(g, entry(g, "living", b"10"), "rite") == "4"
        assert val(g, entry(g, "living", b"12"), "rite") == "2"
        assert val(g, entry(g, "dead_unprunable", b"20"), "rite") == "3"        # catholic main rite
        assert val(g, entry(g, "characters/dead_prunable", b"30"), "rite") == "1"
        assert val(g, entry(g, "county_manager/counties", b"c_test"), "rite") == "4"
        assert val(g, entry(g, "holy_orders/holy_orders", b"0"), "rite") == "3"
        assert res["R9"].extra["unresolved"] == {"counties:4294967295": 1}
        for sec in ("living", "dead_unprunable", "characters/dead_prunable"):   # rites/orgs keep their own faith=
            assert all(not gs.find_keys(g, e, "faith") for e in gs.iter_entries(g, *gs.locate(g, sec).body))

    def test_variables(self, paths):
        save, res, _ = run(paths, "R8,R10,R9", "faith")
        g = save.gamestate
        assert b"type=faith\n\t\t\t\t\t\tidentity=1" in g            # old catholic 0 -> 1.20 catholic faith 1
        assert b"type=religion\n\t\t\t\t\t\tidentity=1" in g         # old islam 1 -> islam 1
        assert res["R9"].extra["by_place"]["variable type=faith"] == 1

    def test_heads_carried_faith_shape(self, paths):
        save, res, _ = run(paths, "R8,R10,R9", "faith")
        g = save.gamestate
        x = res["R9"].extra
        assert val(g, entry(g, "faiths/database", b"1"), "religious_head") == "4"   # catholic <- k_papal_state
        assert val(g, entry(g, "faiths/database", b"0"), "religious_head") == "5"   # christian_faith <- d_celtic_seat
        assert x["heads_carried"]["catholic"] == {"title": "k_papal_state", "from_old_faith": "0"}
        assert x["faith_heads"]["dynamic_faith_3"] == "x_x_599"                   # WoS keeps Beidh's council
        assert x["faith_heads"]["sunni"] == "d_sunni" and x["head_conflicts"] == []

    def test_head_conflict_rite_shape(self, paths):
        save, res, _ = run(paths, "R8,R10,R9", "rite")
        g = save.gamestate
        x = res["R9"].extra
        assert val(g, entry(g, "faiths/database", b"0"), "religious_head") == "1"   # WoS (old 2) wins over old 4
        assert x["head_conflicts"] == [{"faith_id": "0", "kept": "x_x_599", "dropped": "d_celtic_seat",
                                        "dropped_from_old_faith": "4"}]

    def test_living_counts_for_a6c(self, paths):
        save, res, _ = run(paths, "R8,R10,R9,R12", "faith")
        assert res["R9"].extra["living_explicit_by_rite"] == {"4": 1, "2": 1}     # Beidh -> WoS, Ash -> shafii
        assert res["R12"].extra["living_inherited_by_rite"] == {"4": 1, "2": 1}  # Child -> WoS, Courtier -> shafii


# --------------------------------------------------------------------------- R12
class TestR12:
    def test_inheritance_chain_and_check(self, paths):
        save, res, _ = run(paths, "R8,R10,R9,R12", "faith")
        g = save.gamestate
        assert val(g, entry(g, "living", b"11"), "rite") == "4"       # house head 10
        assert val(g, entry(g, "dead_unprunable", b"21"), "rite") == "4"
        assert val(g, entry(g, "living", b"13"), "rite") == "2"       # no house -> employer 12
        assert val(g, entry(g, "county_manager/counties", b"c_none"), "rite") == "4"   # player
        x = res["R12"].extra
        assert x["took"] == {"house head (living)": 1, "house head (dead_unprunable)": 1, "employer (living)": 1,
                             "player (county)": 1}
        assert x["check"] == {"without_rite": 0, "dangling_rite_ids": 0}
        assert x["assumptions"]

    def test_rite_inserted_after_birth(self, paths):
        save, _, _ = run(paths, "R8,R10,R9,R12", "faith")
        assert b"\tbirth=970.1.1\n\trite=4\n" in save.gamestate


# --------------------------------------------------------------------------- CLI, both shapes
class TestCLIBoth:
    def test_no_custom_faith_one_plain_output(self, tmp_path):
        old, ref = tmp_path / "old.ck3", tmp_path / "ref.ck3"
        old.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY.replace(b'\t\t\tname="Way of Scarcity"\n', b"")))
        ref.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
        assert R.religion_1_20.custom_faith_names(sf.read_save(old).gamestate) == []
        rc = cli.main(["migrate", str(old), "--rules", "all", "--reference", str(ref),
                       "-o", str(tmp_path / "o.migrated.ck3"), "--report", str(tmp_path / "o.report.json")])
        assert rc == 0
        assert (tmp_path / "o.migrated.ck3").exists() and (tmp_path / "o.report.json").exists()
        assert not list(tmp_path.glob("*__wos-*"))

    def test_two_outputs_two_reports(self, paths, tmp_path):
        old, ref = paths
        r = subprocess.run([sys.executable, "-m", "ck3_save_migrator", "migrate", str(old), "--rules", "all",
                            "--reference", str(ref), "-o", str(tmp_path / "o.migrated.ck3"),
                            "--report", str(tmp_path / "o.report.json")], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, r.stderr
        for shape, n_faiths in (("faith", 4), ("rite", 3)):
            out = tmp_path / f"o__wos-{shape}.migrated.ck3"
            rep = json.loads((tmp_path / f"o__wos-{shape}.report.json").read_text(encoding="utf-8"))
            assert rep["wos_shape"] == shape
            g = sf.read_save(out).gamestate
            assert len(list(gs.iter_entries(g, *gs.locate(g, "faiths/database").body))) == n_faiths
            r12 = next(x for x in rep["rules"] if x["id"] == "R12")
            assert r12["extra"]["check"] == {"without_rite": 0, "dangling_rite_ids": 0}
        assert not (tmp_path / "o.migrated.ck3").exists()


# --------------------------------------------------------------------------- refusals happen before any rule runs
@pytest.fixture
def no_rules(monkeypatch):
    """A refusal that fails to fire must not be able to start a migration: running a rule raises."""
    def boom(*a, **k):
        raise AssertionError("a rule ran before the refusal")
    monkeypatch.setattr(cli, "run_rules", boom)


class TestUpFrontRefusals:
    def migrate(self, paths, out, *extra):
        old, ref = paths
        return cli.main(["migrate", str(old), "--rules", "all", "--reference", str(ref), "-o", str(out), *extra])

    def test_existing_output_refused_before_rules(self, paths, tmp_path, no_rules, capsys):
        (tmp_path / "o__wos-rite.migrated.ck3").write_bytes(b"keep me")
        assert self.migrate(paths, tmp_path / "o.migrated.ck3") == 2
        assert "already exists" in capsys.readouterr().err
        assert (tmp_path / "o__wos-rite.migrated.ck3").read_bytes() == b"keep me"

    def test_plain_output_name_not_refused_when_branching(self, paths, tmp_path):
        (tmp_path / "o.migrated.ck3").write_bytes(b"older single-shape run")   # not an output of this run
        assert self.migrate(paths, tmp_path / "o.migrated.ck3") == 0
        assert (tmp_path / "o.migrated.ck3").read_bytes() == b"older single-shape run"

    def test_in_place_refused_before_reading(self, paths, no_rules, monkeypatch):
        monkeypatch.setattr(cli, "read_save", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read the save")))
        old, ref = paths
        assert cli.main(["migrate", str(old), "--rules", "all", "--reference", "none", "-o", str(old)]) == 2

    def test_missing_output_folder_named(self, paths, tmp_path, no_rules, monkeypatch, capsys):
        monkeypatch.setattr(cli, "read_save", lambda *a, **k: (_ for _ in ()).throw(AssertionError("read the save")))
        missing = tmp_path / "no_such_dir"
        assert self.migrate(paths, missing / "o.migrated.ck3") == 1
        err = capsys.readouterr().err
        assert "output folder does not exist" in err and "no_such_dir" in err and ".tmp" not in err
        assert not missing.exists()

    def test_missing_report_folder_named(self, paths, tmp_path, no_rules, capsys):
        assert self.migrate(paths, tmp_path / "o.migrated.ck3", "--report", str(tmp_path / "nope" / "r.json")) == 1
        assert "output folder does not exist" in capsys.readouterr().err

    def test_force_still_overwrites(self, paths, tmp_path):
        (tmp_path / "o__wos-faith.migrated.ck3").write_bytes(b"old")
        assert self.migrate(paths, tmp_path / "o.migrated.ck3", "--force") == 0
        assert sf.read_save(tmp_path / "o__wos-faith.migrated.ck3").gamestate
