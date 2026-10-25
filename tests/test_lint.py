"""Tests for the pre-launch lint (ck3_save_migrator/lint.py) and its CLI wiring.

The clean baseline is the religion fixture migrated with every rule (faith shape): a 1.20-layout save with
rites, faiths, organizations, holy sites and counties. Each breakage test edits exactly one reference in
that baseline and expects exactly the matching check to fire.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import gamestate as gs
from ck3_save_migrator import lint as L
from ck3_save_migrator import rules as R
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import build_ck3
from tests.fixtures.religion import OLD_BODY, OLD_META, REF_BODY, REF_META


@pytest.fixture
def paths(tmp_path):
    old, ref = tmp_path / "old.ck3", tmp_path / "ref.ck3"
    old.write_bytes(build_ck3(meta=OLD_META, body=OLD_BODY))
    ref.write_bytes(build_ck3(meta=REF_META, body=REF_BODY))
    return old, ref


@pytest.fixture
def migrated(paths) -> bytes:
    old, ref = paths
    save = sf.read_save(old)
    R.run_rules(save, R.select("all"), R.RuleContext(reference=ref, wos_shape="faith"))
    return save.gamestate


def sub1(g: bytes, pattern: bytes, repl: bytes) -> bytes:
    """Replace the first match of a regex; fail loudly if the anchor is gone (a stale anchor tests nothing)."""
    out, n = re.subn(pattern, repl, g, count=1)
    assert n == 1, f"anchor not found: {pattern!r}"
    return out


def checks(g: bytes, severity: str | None = None) -> dict[str, int]:
    rep = L.lint_gamestate(g, keys=False)
    return {f.check: f.count for f in rep.findings if severity is None or f.severity == severity}


# --------------------------------------------------------------------------- baseline
class TestBaseline:
    def test_migrated_fixture_is_clean(self, migrated):
        rep = L.lint_gamestate(migrated, keys=False)
        assert rep.findings == [] and rep.errors == 0
        assert rep.stats["characters"] == 7 and rep.stats["rites"] == 5 and rep.stats["faiths"] == 4

    def test_old_layout_skips_religion_checks(self, paths):
        g = sf.read_save(paths[0]).gamestate
        rep = L.lint_gamestate(g, keys=False)
        assert rep.errors == 0
        assert any("not a 1.20-layout save" in s for s in rep.skipped)

    def test_section_index_matches_locate(self, migrated):
        idx = L.SectionIndex(migrated)
        for path in ("living", "faiths/database", "rites/database", "county_manager/counties",
                     "landed_titles/landed_titles", "religion/holy_sites"):
            a, b = idx.block(path), gs.locate(migrated, path)
            assert (a.open, a.close) == (b.open, b.close), path
        assert idx.block("no_such_section") is None and idx.block("faiths/no_such_child") is None


# --------------------------------------------------------------------------- errors: one breakage, one check
ERROR_CASES = [
    ("extra closing brace", "braces balance", lambda g: g + b"}\n"),
    ("unclosed brace", "braces balance", lambda g: g + b"x={\n"),
    ("character without rite", "every character has a rite",
     lambda g: sub1(g, rb'(first_name="Ash"\n\tbirth=960\.1\.1\n)\trite=2\n', rb"\1")),
    ("character rite id missing", "character rite ids exist",
     lambda g: sub1(g, rb'(first_name="Ash"\n\tbirth=960\.1\.1\n\trite=)2', rb"\g<1>99")),
    # rite 1 (insular_celtic) is no faith's main rite, so only the rite check can fire
    ("rite points at a missing faith", "rites point at faiths, characters and rites that exist",
     lambda g: sub1(g, rb"(rite_type=insular_celtic\t+faith=)0", rb"\g<1>77")),
    ("rite founder is not a character", "rites point at faiths, characters and rites that exist",
     lambda g: sub1(g, rb"(\n\t\t4=\{\n\t\t\tfaith=3\n\t\t\tfounder=)21", rb"\g<1>777")),
    ("main rite belongs to another faith", "faiths point at religions, rites, organizations, holy sites and titles that exist",
     lambda g: sub1(g, rb"(\n\t\t\treligion=0\n\t\t\tmain_rite=)4", rb"\g<1>3")),
    ("faith religion missing", "faiths point at religions, rites, organizations, holy sites and titles that exist",
     lambda g: sub1(g, rb"(faith_type=sunni\t+religion=)1", rb"\g<1>9")),
    ("religious head is not a title", "faiths point at religions, rites, organizations, holy sites and titles that exist",
     lambda g: sub1(g, rb'(tag="catholic"\n\t\t\treligious_head=)4', rb"\g<1>99")),
    ("faith origin missing", "faiths point at religions, rites, organizations, holy sites and titles that exist",
     lambda g: sub1(g, rb"(\n\t\t\torigin=)0", rb"\g<1>55")),
    ("holy site or religion lists a missing faith",
     "religions, holy sites, organizations and holy orders point at faiths/rites/titles that exist",
     lambda g: sub1(g, rb"faiths=\{ 0 1 3 \}", b"faiths={ 0 1 3 9 }")),
    ("organization faith missing",
     "religions, holy sites, organizations and holy orders point at faiths/rites/titles that exist",
     lambda g: sub1(g, rb"(\n\t\t3=\{\n\t\t\tfaith=)3(\n\t\t\})", rb"\g<1>8\2")),
    ("holy order rite missing",
     "religions, holy sites, organizations and holy orders point at faiths/rites/titles that exist",
     lambda g: sub1(g, rb"(holy_orders=\{\n\tholy_orders=\{\n\t\t0=\{\n\t\t\trite=)\d+", rb"\g<1>99")),
    ("county rite missing", "every county has an existing rite",
     lambda g: sub1(g, rb"(c_test=\{[^}]*?\brite=)\d+", rb"\g<1>66")),
    ("script variable faith missing", "script variables point at faiths/religions that exist",
     lambda g: sub1(g, rb"(type=faith\n\t+identity=)1", rb"\g<1>42")),
    ("title name both inline and in title_name_data", "title names only inside title_name_data",
     lambda g: sub1(g, rb'(1=\{\n\tkey="x_x_599")',
                    rb'\1\n\tname="X"\n\tcoat_of_arms_id=5\n\ttitle_name_data={\n\t\tname="X"\n\t}')),
]


@pytest.mark.parametrize("label,check,breakage", ERROR_CASES, ids=[c[0] for c in ERROR_CASES])
def test_each_error_check_fires_alone(migrated, label, check, breakage):
    errors = checks(breakage(migrated), "error")
    assert check in errors, f"{label}: expected {check!r}, got {errors}"
    assert list(errors) == [check], f"{label}: other checks fired too: {errors}"


# --------------------------------------------------------------------------- warnings
WARN_CASES = [
    ("character culture missing", "character culture ids exist",
     lambda g: sub1(g, rb'(first_name="Ash"\n)', rb"\1\tculture=55\n")),
    ("spouse not in the save", "family links point at characters in the save",
     lambda g: sub1(g, rb'(first_name="Ash"\n)', rb"\1\tfamily_data={\n\t\tspouse=999\n\t}\n")),
    ("child not in the save", "family links point at characters in the save",
     lambda g: sub1(g, rb'(first_name="Ash"\n)', rb"\1\tfamily_data={\n\t\tchild={ 10 998 }\n\t}\n")),
    ("title holder not in the save", "title holders are characters in the save",
     lambda g: sub1(g, rb'(1=\{\n\tkey="x_x_599"\n\tholder=)10', rb"\g<1>777")),
    ("title_name_data not after coat_of_arms_id", "title_name_data follows coat_of_arms_id",
     lambda g: sub1(g, rb'(1=\{\n\tkey="x_x_599")', rb'\1\n\ttitle_name_data={\n\t\tname="X"\n\t}')),
    ("county culture missing", "county culture ids exist",
     lambda g: sub1(g, rb"(c_test=\{\n\t\t\tculture=)\d+", rb"\g<1>4294967295")),
]


@pytest.mark.parametrize("label,check,breakage", WARN_CASES, ids=[c[0] for c in WARN_CASES])
def test_each_warning_fires_without_errors(migrated, label, check, breakage):
    g = breakage(migrated)
    assert checks(g, "error") == {}, label
    assert check in checks(g, "warn"), label


def test_child_list_braces_are_not_counted_as_ids(migrated):
    g = sub1(migrated, rb'(first_name="Ash"\n)', rb"\1\tfamily_data={\n\t\tchild={ 10 11 }\n\t}\n")
    assert checks(g) == {}


def test_holy_order_titles_held_by_the_dead_are_fine(migrated):
    g = sub1(migrated, rb'(1=\{\n\tkey="x_x_599"\n\tholder=)10', rb"\g<1>20")    # 20 is in dead_unprunable
    assert checks(g) == {}


# --------------------------------------------------------------------------- key names
class TestKeys:
    def test_unknown_key_listed_known_keys_not(self, migrated):
        g = sub1(migrated, rb'(first_name="Ash"\n)', rb"\1\todd_key=yes\n\tmy_key=yes\n")
        words = {m.group(1) for m in L._KEY.finditer(migrated) if m.group(1)} | {b"my_key"}
        rep = L.lint_gamestate(g, known=(words, ["test words"]))
        info = next(f for f in rep.findings if f.severity == "info")
        assert info.examples == ["odd_key x1"] and "test words" in info.note and rep.errors == 0

    def test_known_words_from_game_binary_scripts_and_mods(self, tmp_path):
        game = tmp_path / "steamapps" / "common" / "CK3" / "game"
        (game / "common" / "x").mkdir(parents=True)
        (game / "common" / "x" / "a.txt").write_bytes(b"script_key = { c_yar-calli = yes }\n")
        (game.parent / "binaries").mkdir()
        (game.parent / "binaries" / "ck3.exe").write_bytes(b"\x00engine_key\x00")
        mod = tmp_path / "steamapps" / "workshop" / "content" / "1158310" / "123"
        mod.mkdir(parents=True)
        (mod / "m.txt").write_bytes(b"mod_key = yes\n")
        meta = b'mods={ "mod/ugc_123.mod" "mod/ugc_999.mod" "mod/local.mod" }'
        assert L.workshop_mod_dirs(meta, game) == [mod]                  # not installed: skipped
        assert L.listed_workshop_mods(meta, game) == ([mod], ["999"])     # ...and named
        words, sources = L.known_words(game, b"ref_key=yes\n", [mod])
        assert {b"script_key", b"c_yar-calli", b"engine_key", b"mod_key", b"ref_key"} <= words
        assert sources == ["reference save", "game binary (ck3.exe)", "game script files", "mod 123"]

    def test_no_sources_skips(self, migrated):
        rep = L.lint_gamestate(migrated)
        assert any("no reference save, game folder or mods" in s for s in rep.skipped)


# --------------------------------------------------------------------------- reject families
def _fake_game(root: Path) -> Path:
    """A game folder with one definition of each kind; the modifiers file starts with a byte-order mark,
    as most real game files do, so its first definition is the one a careless reader would miss."""
    game = root / "game"
    files = {
        "common/modifiers/00_mods.txt": b"\xef\xbb\xbfgood_modifier = {\n}\nother_modifier = {\n}\n",
        "common/culture/innovations/00_inno.txt": b"innovation_ok = {\n}\n",
        "common/game_rules/00_rules.txt": b"my_rule = {\n\topt_a = {\n\t}\n}\n",
        "common/on_action/00_on.txt": b"good_pulse = {\n}\n",
        "common/dynasties/00_dyn.txt": b"1 = {\n\tname = dynn_one\n}\n",
        "common/culture/cultures/00_cul.txt": b"cul_a = {\n}\ncul_b = {\n}\ncul_c = {\n}\n",
        "common/landed_titles/00_titles.txt": b"e_x = {\n\tk_y = {\n\t\tc_w = {\n\t\t\tb_v = {\n\t\t\t}\n\t\t}\n\t}\n}\n",
        "common/landed_titles/title_conversion.lookup": b"b_old = b_v\n",
        # cul_a is asked for too, but the save has it: only cul_b may be reported
        "events/00_ev.txt": b"e = { trigger = { culture = culture:cul_b } }\nf = { t = { culture = culture:cul_a } }\n",
    }
    for rel, data in files.items():
        p = game / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return game


FAMILY_SAVE = (
    b"living={\n"
    b"1={\n\tfirst_name=\"A\"\n\tdna=\"ABCDEF\"\n"
    b"\talive_data={\n\t\tmodifier={\n\t\t\tmodifier=\"good_modifier\"\n\t\t}\n"
    b"\t\tmodifier={\n\t\t\tmodifier=\"bad_modifier\"\n\t\t}\n"
    b"\t\tmodifier={\n\t\t\tmodifier=\"6200_beast_modifier\"\n\t\t}\n\t\tlevel=5\n\t}\n}\n"
    b"2={\n\tfirst_name=\"B\"\n\tdna=\"GHIJKL\"\n\towner_influence=3\n}\n"
    b"3={\n\tfirst_name=\"C\"\n\tdna=\"MNOP\"\n}\n"
    b"}\n"
    b"opinions={\n\tactive_opinions={ {\n\t\t\tmodifier=bad_opinion\n\t\t}\n }\n}\n"
    b"schemes={\n\tactive={\n\t\t0={\n\t\t\towner_influence=11\n\t\t\tready=yes\n\t\t}\n"
    b"\t\t1={\n\t\t\towner_influence=12\n\t\t}\n\t}\n}\n"
    b"culture_manager={\n\tcultures={\n\t\t0={\n\t\t\tculture_template=\"cul_a\"\n\t\t\texposure_type=realm\n"
    b"\t\t\tculture_innovation={ {\n\t\t\t\t\ttype=\"innovation_ok\"\n\t\t\t\t}\n {\n\t\t\t\t\ttype=\"innovation_gone\"\n"
    b"\t\t\t\t}\n }\n\t\t}\n\t}\n}\n"
    b"artifacts={\n\tartifacts={\n1={\n\tmodifiers={ good_modifier gone_artifact_mod }\n\ttype=prisoner_of_war\n}\n\t}\n}\n"
    b"game_rules={\n\tsettings={ opt_a opt_gone }\n}\n"
    b"pending={\n\ta={\n\t\ton_action=good_pulse\n\t}\n\tb={\n\t\ton_action=VIET_pulse\n\t}\n"
    b"\tc={\n\t\ton_action=VIET_pulse\n\t}\n}\n"
    b"dynasties={\n\tdynasties={\n0={\n\tkey=\"1\"\n}\n1={\n\tkey=\"999\"\n}\n\t}\n}\n"
    b"landed_titles={\n\tlanded_titles={\n"
    b"0={\n\tkey=\"e_x\"\n}\n1={\n\tkey=\"b_gone\"\n}\n2={\n\tkey=\"c_gone2\"\n}\n3={\n\tkey=\"x_x_7\"\n}\n"
    b"4={\n\tkey=\"b_old\"\n\trenamed=yes\n}\n"
    b"\t}\n}\n"
)


@pytest.fixture
def fam(tmp_path):
    data = L.load_game_data(_fake_game(tmp_path), b'x={\n\tdna="ABCD"\n\ttype="ref_only_type"\n}\n', [])
    rep = L.lint_gamestate(FAMILY_SAVE, known=data)
    return {f.check: f for f in rep.findings if f.severity == "reject"}, rep, data


class TestFamilies:
    def test_byte_order_mark_does_not_hide_the_first_definition(self, fam):
        _, _, data = fam
        assert b"good_modifier" in data.defined and b"other_modifier" in data.defined

    def test_dna_length_learned_from_the_reference(self, fam):
        f = fam[0]["Unexpected DNA string length"]
        assert f.count == 2 and "4-character" in f.note           # ABCDEF, GHIJKL; MNOP has the right length

    def test_dna_skipped_without_a_reference(self, tmp_path):
        rep = L.lint_gamestate(FAMILY_SAVE, known=L.load_game_data(_fake_game(tmp_path), None, []))
        assert any("DNA length" in s for s in rep.skipped)

    def test_rejected_tokens_counted_only_in_their_section(self, fam):
        found = fam[0]
        assert found["Unexpected token: owner_influence (in schemes)"].count == 2     # not the one in living
        assert found["Unexpected token: ready (in schemes)"].count == 1
        assert found["Unexpected token: exposure_type (in culture_manager)"].count == 1
        assert found["Unexpected token: renamed (in landed_titles)"].count == 1

    def test_key_references(self, fam):
        f = fam[0]["Failed to read key reference"]
        names = {e.split(" x")[0] for e in f.examples}
        assert names == {"bad_modifier", "6200_beast_modifier", "innovation_gone", "gone_artifact_mod", "opt_gone"}
        assert f.count == 5
        # known good, known exclusions: good_modifier, innovation_ok, opt_a; level=5 (a number);
        # bad_opinion (opinions are not logged); bare type=prisoner_of_war (documented miss)

    def test_on_actions(self, fam):
        f = fam[0]["Unknown on action"]
        assert f.count == 2 and f.examples == ["VIET_pulse x2"]

    def test_dynasty_templates(self, fam):
        assert fam[0]["Unknown dynasty template"].examples == ["dynasty template 999"]

    def test_every_family_has_a_plain_gloss_and_keeps_the_log_wording(self, fam):
        for check, f in fam[0].items():
            assert f.gloss and f.gloss != check, check          # the check itself stays the game's log text
        assert fam[0]["Unexpected DNA string length"].check == "Unexpected DNA string length"

    def test_game_data_names_what_was_read(self, fam):
        _, rep, data = fam
        paths = rep.stats["game_data"]
        assert any(p.startswith("game folder: ") and p.endswith("game") for p in paths)
        assert any(p.startswith("reference save: ") for p in paths)

    def test_dead_titles_and_duplicate_names(self, fam):
        found = fam[0]
        assert found["is not a valid title template"].examples == ["b_gone", "c_gone2"]   # x_ and converted skipped
        assert found["Duplicate landed title name"].count == 1

    def test_cultures_the_scripts_want(self, fam):
        f = fam[0]["Failed to fetch a valid culture"]
        assert f.examples == ["cul_b"]               # cul_a is asked for but in the save; cul_c is never asked for

    def test_no_game_folder_skips_the_families_that_need_one(self):
        rep = L.lint_gamestate(FAMILY_SAVE, known=L.GameData(words={b"x"}, sources=["x"]))
        assert any("no game folder" in s for s in rep.skipped)
        rejects = {f.check for f in rep.findings if f.severity == "reject"}
        assert rejects and all(c.startswith("Unexpected token:") for c in rejects)   # the table needs no game data


# --------------------------------------------------------------------------- real save (opt-in)
RUNS = Path(__file__).resolve().parents[1] / "private" / "data" / "runs"
REAL = [("faith", RUNS / "2026-10-24__22-57-35__A6c-987-r1-r12-wos-faith" / "logs" / "error.log"),
        ("rite", RUNS / "2026-10-24__22-58-52__A6c-987-r1-r12-wos-rite" / "logs" / "error.log")]


@pytest.mark.skipif(os.environ.get("CK3_REAL_SAVES") != "1" or not all(p.exists() for _, p in REAL),
                    reason="set CK3_REAL_SAVES=1 (needs private/data, the A6c run logs and the game install; ~90 s)")
@pytest.mark.parametrize("shape,log", REAL, ids=[s for s, _ in REAL])
def test_real_families_within_5_percent_of_the_games_log(shape, log, monkeypatch):
    monkeypatch.delenv("CK3_GAME_DIR")
    root = Path(__file__).resolve().parents[1] / "private" / "data"
    save = sf.read_save(root / "migrated" / f"987_10_27__r1-r12__wos-{shape}.migrated.ck3")
    ref = sf.read_save(root / "originals" / "reference-1.20" / "ref_1_20_987_10_27.ck3").gamestate
    data = L.load_game_data(cli.find_game_dir(None), ref, [])        # the A6c launches ran with no mods
    found = {f.check: f.count for f in L.lint_gamestate(save.gamestate, known=data).findings if f.severity == "reject"}
    text = log.read_text(encoding="utf-8", errors="replace")
    for prefix, pattern in (("Unexpected DNA string length", "Unexpected DNA string length"),
                            ("Unexpected token: owner_influence", "Unexpected token: owner_influence"),
                            ("Unexpected token: exposure_type", "Unexpected token: exposure_type"),
                            ("Failed to read key reference", "Failed to read key reference"),
                            ("Unknown on action", "Unknown on action"),
                            ("Unknown dynasty template", "Unknown dynasty template"),
                            ("is not a valid title template", "is not a valid title template"),
                            ("Duplicate landed title name", "Duplicate landed title name")):
        predicted = sum(n for c, n in found.items() if c.startswith(prefix))
        observed = text.count(pattern)
        assert abs(predicted - observed) <= 0.05 * observed, f"{prefix}: predicted {predicted}, logged {observed}"


# --------------------------------------------------------------------------- CLI
@pytest.fixture
def no_lint_allowed(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("lint ran although --no-lint was given")
    monkeypatch.setattr(cli, "lint_gamestate", boom)


class TestCLI:
    def migrate(self, paths, out, *extra):
        old, ref = paths
        return cli.main(["migrate", str(old), "--rules", "all", "--reference", str(ref), "--wos-shape", "faith",
                         "-o", str(out), "--report", str(out.with_suffix(".json")), *extra])

    def test_migrate_lints_by_default(self, paths, tmp_path, capsys):
        assert self.migrate(paths, tmp_path / "o.ck3") == 0
        assert "lint          : 0 error(s)" in capsys.readouterr().out
        rep = json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))
        assert rep["lint"]["errors"] == 0 and rep["lint"]["stats"]["rites"] == 5
        beside = json.loads((tmp_path / "o.lint.json").read_text(encoding="utf-8"))   # written next to the output
        assert beside == rep["lint"]

    def test_dry_run_writes_no_lint_file(self, paths, tmp_path):
        assert self.migrate(paths, tmp_path / "o.ck3", "--dry-run") == 0
        assert not (tmp_path / "o.lint.json").exists() and not (tmp_path / "o.ck3").exists()

    def test_no_lint_skips(self, paths, tmp_path, no_lint_allowed):
        assert self.migrate(paths, tmp_path / "o.ck3", "--no-lint") == 0
        assert json.loads((tmp_path / "o.json").read_text(encoding="utf-8"))["lint"] is None
        assert not (tmp_path / "o.lint.json").exists()

    def test_lint_error_exits_4_and_still_writes(self, paths, tmp_path, monkeypatch, capsys):
        def broken(g, **k):
            rep = L.LintReport()
            rep.add("braces balance", "error", ["simulated"])
            return rep
        monkeypatch.setattr(cli, "lint_gamestate", broken)
        assert self.migrate(paths, tmp_path / "o.ck3") == 4
        assert (tmp_path / "o.ck3").exists() and "lint found 1 error" in capsys.readouterr().err

    @pytest.mark.parametrize("flag,expect_calls", [((), 1), (("--mods", "none"), 0)])
    def test_lint_command_mods_choice(self, paths, tmp_path, monkeypatch, flag, expect_calls):
        good = tmp_path / "good.ck3"
        assert self.migrate(paths, good, "--no-lint") == 0
        calls = []
        monkeypatch.setattr(cli, "listed_workshop_mods", lambda meta, gd: calls.append(1) or ([], []))
        assert cli.main(["lint", str(good), *flag]) == 0
        assert len(calls) == expect_calls

    @pytest.mark.parametrize("flag,expect_calls", [((), 1), (("--lint-mods", "none"), 0)])
    def test_migrate_lint_mods_choice(self, paths, tmp_path, monkeypatch, flag, expect_calls):
        calls = []
        monkeypatch.setattr(cli, "listed_workshop_mods", lambda meta, gd: calls.append(1) or ([], []))
        assert self.migrate(paths, tmp_path / "o.ck3", *flag) == 0
        assert len(calls) == expect_calls

    def test_mods_not_installed_are_named(self, paths, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(cli, "listed_workshop_mods", lambda meta, gd: ([], ["2218867072", "2507220129"]))
        assert self.migrate(paths, tmp_path / "o.ck3") == 0
        out = capsys.readouterr().out
        assert "2 mod(s) the save lists are not installed" in out and "2507220129" in out
        rep = json.loads((tmp_path / "o.lint.json").read_text(encoding="utf-8"))
        assert rep["stats"]["mods_not_installed"] == ["2218867072", "2507220129"]

    def test_reject_lines_show_gloss_then_game_log_text(self, paths, tmp_path, capsys):
        game = _fake_game(tmp_path)
        assert self.migrate(paths, tmp_path / "o.ck3", "--game-dir", str(game)) == 0
        out = capsys.readouterr().out
        # each reject line is the plain gloss, and the next line the game's own log wording
        pairs = re.findall(r"REJECT +([^\n]+): [\d,]+\n +game log: ([^\n]+)", out)
        assert pairs, out
        assert all(gloss != log for gloss, log in pairs)

    def test_lint_command(self, paths, tmp_path, capsys):
        good = tmp_path / "good.ck3"
        assert self.migrate(paths, good, "--no-lint") == 0
        assert cli.main(["lint", str(good), "--json", str(tmp_path / "l.json")]) == 0
        assert json.loads((tmp_path / "l.json").read_text(encoding="utf-8"))["errors"] == 0
        save = sf.read_save(good)
        save.set_gamestate(save.gamestate + b"}\n")
        bad = tmp_path / "bad.ck3"
        sf.write_save(save, bad)
        assert cli.main(["lint", str(bad)]) == 4
        assert re.search(r"ERROR +braces balance", capsys.readouterr().out)


class TestDiscoveryNone:
    def test_game_dir_none_from_env_explicit_wins(self, tmp_path, monkeypatch):
        from tests.fixtures.make_ck3 import make_game_dir
        game = make_game_dir(tmp_path / "game")
        monkeypatch.setenv("CK3_GAME_DIR", "none")
        assert cli.find_game_dir(None) is None
        assert cli.find_game_dir(str(game)) == game
        assert cli.find_game_dir("none") is None

    @pytest.mark.parametrize("via", ["flag", "env"])
    def test_named_folder_that_is_not_a_game_folder_is_refused(self, tmp_path, monkeypatch, via):
        bad = tmp_path / "not_a_game"
        bad.mkdir()
        if via == "env":
            monkeypatch.setenv("CK3_GAME_DIR", str(bad))
        with pytest.raises(FileNotFoundError, match=r"not_a_game.*common.landed_titles"):
            cli.find_game_dir(str(bad) if via == "flag" else None)

    def test_lint_with_a_wrong_game_dir_exits_1(self, paths, tmp_path, capsys):
        assert cli.main(["lint", str(paths[0]), "--game-dir", str(tmp_path / "typo")]) == 1
        err = capsys.readouterr().err
        assert "typo" in err and "landed_titles" in err

    def test_reference_none_from_env_explicit_wins(self, paths, monkeypatch):
        monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")
        assert cli.find_reference(None) is None
        assert cli.find_reference(str(paths[1])) == paths[1]
        monkeypatch.setenv("CK3_REFERENCE_SAVE", str(paths[1]))
        assert cli.find_reference("none") is None and cli.find_reference(None) == paths[1]


# --------------------------------------------------------------------------- id spaces
def _ids_gs(living: str = "", dead: str = "", prunable: str = "") -> bytes:
    return (f"living={{\n{living}}}\ndead_unprunable={{\n{dead}}}\n"
            f"characters={{\n\tdead_prunable={{\n{prunable}\t}}\n}}\n").encode()


def _ids(g: bytes) -> dict:
    rep = L.LintReport()
    L.check_ids(g, rep)
    return {f.check: f for f in rep.findings}


def test_check_ids_clean_save_has_no_finding():
    assert _ids(_ids_gs(living="1={\n}\n16777218={\n}\n", dead="3={\n}\n")) == {}


def test_check_ids_same_id_in_two_character_sections():
    found = _ids(_ids_gs(living="5={\n}\n", dead="5={\n}\n"))
    assert found["entry ids are unique in each id space"].severity == "error"


def test_check_ids_byte_identical_repeat_is_how_1_20_writes():
    assert _ids(_ids_gs(dead="7={\n\tx=1\n}\n7={\n\tx=1\n}\n")) == {}
    assert "entry ids are unique in each id space" in _ids(_ids_gs(dead="7={\n\tx=1\n}\n7={\n\tx=2\n}\n"))


def test_lint_gamestate_runs_the_id_check():
    rep = L.lint_gamestate(_ids_gs(living="5={\n}\n", dead="5={\n}\n"), keys=False)
    assert "entry ids are unique in each id space" in {f.check for f in rep.findings}
    assert rep.errors >= 1


def test_check_ids_one_slot_under_two_generations():
    found = _ids(_ids_gs(living="5={\n}\n", prunable="16777221={\n}\n"))    # 0x01000005: slot 5, generation 1
    assert found["entry slots are unique in each id space"].count == 1


# --------------------------------------------------------------------------- the title tree, contracts
def _titles_gs(titles: str, contracts: str = "", living: str = "1={\n}\n2={\n}\n") -> bytes:
    return (f"living={{\n{living}}}\nlanded_titles={{\n\tlanded_titles={{\n{titles}\t}}\n}}\n"
            f"vassal_contracts={{\n\tactive={{\n{contracts}\t}}\n}}\n").encode()


def _checks(g: bytes) -> dict:
    rep = L.LintReport()
    L.check_titles(g, rep)
    L.check_contracts(g, rep)
    return {f.check: f for f in rep.findings}


TREE = ("0={\n\tkey=c_a\n}\n1={\n\tkey=b_a\n\tde_facto_liege=0\n\tde_jure_liege=0\n\tcapital_barony=yes\n}\n"
        "2={\n\tkey=c_b\n}\n")


def test_check_titles_quiet_on_a_sound_tree():
    assert _checks(_titles_gs(TREE)) == {}


def test_check_titles_the_loaders_rules():
    bad = TREE + ("3={\n\tkey=b_x\n\tde_facto_liege=2\n\tde_jure_liege=0\n}\n"          # de facto != de jure
                  "4={\n\tkey=b_cap\n\tde_jure_liege=0\n\tcapital_barony=yes\n}\n"     # capital without de facto
                  "5={\n\tkey=b_lone\n\tholder=1\n}\n"                                 # held orphan (warning)
                  "6={\n\tkey=c_a\n\tde_jure_liege=99\n}\n")                           # duplicate key, liege missing
    found = _checks(_titles_gs(bad))
    assert found["a barony's de facto liege is its de jure county"].count == 1
    assert found["capital baronies have a county"].examples == ["b_cap: no de facto liege"]
    assert found["held baronies have a county"].severity == "warn" and found["held baronies have a county"].count == 1
    assert found["title keys are unique"].examples == ["c_a x2"]
    assert found["title lieges point at titles that exist"].count == 1


def test_check_contracts_needs_both_parties():
    ok = "7={\n\t\tliege=1\n\t\tvassal=2\n\t}\n"
    assert _checks(_titles_gs(TREE, contracts=ok)) == {}
    found = _checks(_titles_gs(TREE, contracts="7={\n\t\tliege=1\n\t}\n8={\n\t\tliege=1\n\t\tvassal=9\n\t}\n"))
    assert found["vassal contracts name both parties"].count == 2


def test_localization_key_is_rejected_only_directly_in_a_title():
    g = ("landed_titles={\n\tlanded_titles={\n0={\n\tkey=k_a\n\tlocalization_key=K_A\n}\n"
         "1={\n\tkey=k_b\n\ttitle_name_data={\n\t\tlocalization_key=K_B\n\t}\n}\n\t}\n}\n").encode()
    rep = L.LintReport()
    L.check_families(g, rep, L.GameData(), L.SectionIndex(g))
    f = {x.check: x for x in rep.findings}
    assert f["Unexpected token: localization_key (in landed_titles)"].count == 1
