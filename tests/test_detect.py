"""U3: detectors (whether a built-in rule is needed, read only), the plan's needed/done lines, the re-check of a save
already on the game's version line, lint's converted-on-load families and the F7 candidate.

The kill-check of each detector: on a fixture its count is what its rule matches, and on the rule's own output it
finds nothing ("needed" on a save that already has the fix would be a false alarm)."""

from __future__ import annotations

import re

import pytest

from ck3_save_migrator import cli, detect as D
from ck3_save_migrator import lint as L
from ck3_save_migrator import record
from ck3_save_migrator import savefile as sf
from ck3_save_migrator._version import get_base_version
from ck3_save_migrator.rules import REGISTRY, RuleContext
from ck3_save_migrator.rules import to_1_20 as T
from tests import test_update as TU
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3
from tests.fixtures.religion import REF_BODY, REF_META
from tests.test_update import game, run

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment
RULE = {r.id: r for r in REGISTRY}

DEAD = (b"dead_unprunable={\n"
        b"10={\n\tfirst_name=\"A\"\n\tnickname=nick_the_victorious\n\tdead_data={\n\t\tliege=11\n\t\tliege_title=0\n\t}\n}\n"
        b"11={\n\tfirst_name=\"B\"\n\tdead_data={\n\t\tliege=10\n\t\tliege_title=0\n\t}\n}\n"
        b"12={\n\tfirst_name=\"C\"\n\tdead_data={\n\t\tliege=12\n\t}\n}\n"
        b"}\n")
BODY = RULES_BODY.replace(b'\tfirst_name="Knut"\n', b'\tfirst_name="Knut"\n\tnickname=nick_the_victorious\n') + DEAD


def localized_game(tmp_path, version="1.20.1.2"):
    g = game(tmp_path, version)
    loc = g / "localization" / "english" / "nicknames_l_english.yml"
    loc.parent.mkdir(parents=True, exist_ok=True)
    loc.write_bytes(b'\xef\xbb\xbfl_english:\n nick_the_victorious:0 "the Victorious"\n')
    return g


def fixture_save():
    return sf.parse_save(build_ck3(meta=RULES_META, body=BODY))


# --------------------------------------------------------------------------- 1. each detector against its rule
@pytest.mark.parametrize("rid,detector,counted", [
    ("R2", T.r2_detect, "edited"),            # R2's matched counts every flag; what it re-encodes is its edits
    ("R21", T.r21_detect, "matched"),
    ("R23", T.r23_detect, "matched"),
])
def test_a_detector_counts_what_its_rule_matches_and_nothing_on_its_output(tmp_path, rid, detector, counted):
    save = fixture_save()
    n, examples = detector(save.gamestate)
    res = RULE[rid].run(save, RuleContext(game_dir=localized_game(tmp_path)))
    assert n > 0 and n == getattr(res, counted) and len(examples) == min(n, 5)
    assert detector(save.gamestate) == (0, [])             # the kill-check: the fixed save is not "needed"


def test_the_r2_detector_counts_only_what_r2_can_re_encode():
    n, examples = T.r2_detect(fixture_save().gamestate)
    assert n == 2 and all("AAEAAA==" not in e and "Aw==" not in e for e in examples)  # high byte set; 1 byte


def test_the_r3_check_fires_on_inline_names_without_title_name_data_and_not_on_r3s_output():
    save = fixture_save()
    hits = L.inline_title_names(save.gamestate)
    rep = L.LintReport()
    L.check_references(save.gamestate, rep)
    found = next(f for f in rep.findings if f.check == "title names only inside title_name_data")
    res = RULE["R3"].run(save, RuleContext())
    assert len(hits) == found.count == res.matched == 3 and "no title_name_data" in found.examples[0]
    rep = L.LintReport()
    L.check_references(save.gamestate, rep)
    assert L.inline_title_names(save.gamestate) == []
    assert not [f for f in rep.findings if f.check == "title names only inside title_name_data"]
    assert D.detect("R3", save.gamestate, D.Env()).line() == "done: none found"


def test_detect_lines(tmp_path):
    g = fixture_save().gamestate
    env = D.Env(game_dir=None)
    assert D.detect("R23", g, env).line() == "needed: 2 nicknames without text"
    assert D.detect("R22", g, env).line() == "unknown: needs the game folder (the target map)"
    assert D.detect("R14", g, env).state == "unknown"                       # needs a reference
    assert D.detect("R8", g, env).line().startswith("needed: the save has no rites/faiths database")
    assert D.detect("R99", g, env).line().startswith("unknown: a Python rule with no detector")


def test_check_uses_the_detectors(tmp_path, capsys):
    s = tmp_path / "f.ck3"
    s.write_bytes(build_ck3(meta=RULES_META, body=BODY))
    assert cli.main(["check", str(s), "--game-dir", str(localized_game(tmp_path))]) == 0
    out = capsys.readouterr().out
    row = next(ln for ln in out.splitlines() if ln.strip().startswith("R23"))
    assert "needed" in row and "2 nicknames without text" in row
    assert "only running it would tell" not in next(ln for ln in out.splitlines() if ln.strip().startswith("R21"))


# --------------------------------------------------------------------------- 4. the plan's needed and done lines
def test_the_plan_shows_needed_and_done_and_unknown_without_a_detector(tmp_path, saves, capsys, monkeypatch):
    s = saves / "Old.ck3"
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED))
    monkeypatch.delitem(D.DETECTORS, "R20")                        # as a rule with no detector
    before = sorted(p.name for p in saves.iterdir())
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path)), "--reference", "none")
    assert code == 0
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  R")}
    assert "done: none found" in lines["R23"] and "needed:" in lines["R7"]
    assert "unknown: a Python rule with no detector" in lines["R20"]
    assert "detectors judged each built-in step: read the whole gamestate" in out and " s\n" in out
    assert sorted(p.name for p in saves.iterdir()) == before                 # status still writes nothing


def test_no_detect_reads_only_the_first_megabyte(tmp_path, saves, capsys, monkeypatch):
    s = saves / "Old.ck3"
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED))
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read"))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path)), "--reference", "none",
                       "--no-detect")
    assert code == 0 and "detectors not run (the plan read only the first megabyte)" in out


# --------------------------------------------------------------------------- 5. the re-check of a current save
def current_save(saves, name="Current.ck3"):
    """A 1.20.1.2 save (the built-in pack's span does not select it) with a nickname and no nickname_text."""
    s = saves / name
    s.write_bytes(build_ck3(meta=REF_META, body=REF_BODY.replace(
        b'\tfirst_name="Saint"\n', b'\tfirst_name="Saint"\n\tnickname=nick_the_victorious\n') + b"random_seed=222\n"))
    return s


def test_a_current_save_missing_r23s_fix_is_re_checked(tmp_path, saves, capsys):
    s, g = current_save(saves), localized_game(tmp_path)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 0 and out.startswith("ALREADY CURRENT")
    assert "needed: R23 (1 nicknames without text); run `ck3update update Current.ck3 --rules R23`" in out
    r23 = next(ln for ln in out.splitlines() if ln.startswith("  R23"))
    assert "re-check: needed: 1 nicknames without text" in r23
    before = sorted(p.name for p in saves.iterdir())
    code, out, _ = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")
    assert code == 0 and "already current: nothing written" in out                    # never runs unless named
    assert sorted(p.name for p in saves.iterdir()) == before
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint", "--rules", "R23")
    assert code == 0, err
    written = sf.read_save(saves / "Current__updated__1.20.1.2.ck3").gamestate
    assert b'\tnickname_text="the Victorious"\n' in written
    assert [x for x in cli.LAST_PLAN["ran"]] == ["R23"]


def test_a_record_naming_this_tool_version_skips_the_re_check(tmp_path, saves, capsys, monkeypatch):
    s = current_save(saves)
    record.append_update("222", "Current", {"date": "d", "tool": f"ck3-save-updater {get_base_version()}"})
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read"))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    assert code == 0 and "re-check skipped: the record of Current says this tool" in out
    assert "needed: R23" not in out


def test_a_record_naming_an_older_version_re_checks(tmp_path, saves, capsys):
    s = current_save(saves)
    record.append_update("222", "Current", {"date": "d", "tool": "ck3-save-updater 0.0.1"})
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    assert code == 0 and "needed: R23 (1 nicknames without text)" in out


def test_rules_naming_a_rule_outside_the_line_still_refuses_another_line(tmp_path, saves, capsys):
    """Named --rules select a rule despite the span only on the pack's own game line."""
    s = current_save(saves)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path, "1.21.0")),
                       "--rules", "R23")
    assert "named in --rules" not in out


# --------------------------------------------------------------------------- 6. what the game converts on load
CONVERTED = (b"schemes={\n\tactive={\n\t\t0={\n\t\t\towner_influence=11\n\t\t\tready=yes\n\t\t}\n\t}\n}\n"
             b"culture_manager={\n\tcultures={\n\t\t0={\n\t\t\texposure_type=x\n\t\t\texposure_marker=y\n\t\t}\n\t}\n}\n"
             b"landed_titles={\n\tlanded_titles={\n0={\n\tkey=\"k_x\"\n\tlocalization_key=\"k\"\n\trenamed=yes\n"
             b"\tcoat_of_arms_id=1\n\ttitle_name_data={\n\t\tname=\"X\"\n\t}\n}\n\t}\n}\n")


def test_the_six_converted_families_are_info():
    rep = L.lint_gamestate(CONVERTED, known=L.GameData(words={b"x"}, sources=["x"]))
    tokens = {f.check: f for f in rep.findings if f.check.startswith("Unexpected token:")}
    assert len(tokens) == 6 and all(f.severity == "info" and f.gloss == L.CONVERTED_GLOSS for f in tokens.values())
    assert rep.count("reject") == 0 and rep.errors == 0


def test_lint_exits_0_on_a_save_with_only_converted_families(tmp_path):
    s = tmp_path / "c.ck3"
    s.write_bytes(build_ck3(meta=REF_META, body=CONVERTED))
    assert cli.main(["lint", str(s), "--reference", "none"]) == 0


def test_the_mod_dependent_rows_stay_rejects(tmp_path):
    from tests.test_lint import FAMILY_SAVE, _fake_game
    rep = L.lint_gamestate(FAMILY_SAVE, known=L.load_game_data(_fake_game(tmp_path), None, []))
    sev = {f.check: f.severity for f in rep.findings}
    for check in ("Failed to read key reference", "Unknown on action", "Unknown dynasty template"):
        assert sev[check] == "reject"


# --------------------------------------------------------------------------- 8. F7, a candidate
def test_a_company_title_keyed_for_another_company_is_a_warning():
    g = (b"landed_titles={\n\tlanded_titles={\n5={\n\tkey=\"x_mc_8\"\n\tmercenary=7\n}\n6={\n\tkey=\"x_mc_8\"\n}\n\t}\n"
         b"\tdynamic_templates={ { key=\"x_mc_8\" } }\n}\n"
         b"mercenary_company_manager={\n\tmercenary_companies={\n7={\n\ttitle=5\n}\n8={\n\ttitle=6\n}\n\t}\n}\n")
    rep = L.LintReport()
    L.check_companies(g, rep)
    f = next(f for f in rep.findings if f.check == "a mercenary company's title key is x_mc_<company id>")
    assert f.severity == "warn" and f.examples == ["company 7: its title key is x_mc_8"]
    assert not re.search(r"\bR\d+\b", f.check + f.gloss + " ".join(f.examples))     # it names no rule
