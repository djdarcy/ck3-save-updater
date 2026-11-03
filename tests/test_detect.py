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
from tests.test_update import game, run, steps_of

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
])
def test_a_detector_counts_what_its_rule_matches_and_nothing_on_its_output(tmp_path, rid, detector, counted):
    save = fixture_save()
    n, examples = detector(save.gamestate)
    res = RULE[rid].run(save, RuleContext(game_dir=localized_game(tmp_path)))
    assert n > 0 and n == getattr(res, counted) and len(examples) == min(n, 5)
    assert detector(save.gamestate) == (0, [])             # the kill-check: the fixed save is not "needed"


def test_the_r23_detector_counts_what_r23_writes_and_nothing_on_its_output(tmp_path):
    save, g = fixture_save(), localized_game(tmp_path)
    n, examples, left = T.r23_detect(save.gamestate, g, [])
    res = RULE["R23"].run(save, RuleContext(game_dir=g))
    assert n == res.edited == 2 and len(examples) == 2 and not left
    assert T.r23_detect(save.gamestate, g, [])[:2] == (0, [])     # the kill-check


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
    assert D.detect("R23", g, env).line() == "unknown: needs the game folder (its localization)"
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
    lines = steps_of(out)
    assert "done: none found" in lines["R23"] and "needed:" in lines["R7"]
    assert "unknown: a Python rule with no detector" in lines["R20"]
    assert re.search(r"(?m)^DETECTORS +did: judged each built-in step$", out)
    assert re.search(r"(?m)^ +read: the whole gamestate, [\d.]+ MB, in [\d.]+ s$", out)
    judged = re.search(r"(?m)^ +judged: (\d+) step\(s\) in [\d.]+ s; slowest (\w+) [\d.]+ s", out)
    assert judged and int(judged[1]) == len(cli.LAST_PLAN["status"].detect_timings) and judged[2] in lines
    assert sorted(p.name for p in saves.iterdir()) == before                 # status still writes nothing


def test_no_detect_reads_only_the_first_megabyte(tmp_path, saves, capsys, monkeypatch):
    s = saves / "Old.ck3"
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED))
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read"))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path)), "--reference", "none",
                       "--no-detect")
    assert code == 0 and re.search(r"(?m)^DETECTORS +did: not run \(the plan read only the first megabyte\)$", out)


# --------------------------------------------------------------------------- 5. the re-check of a current save
def current_save(saves, name="Current.ck3"):
    """A 1.20.1.2 save (the built-in pack's span does not select it) with a nickname and no nickname_text."""
    s = saves / name
    s.write_bytes(build_ck3(meta=REF_META, body=REF_BODY.replace(
        b'\tfirst_name="Saint"\n', b'\tfirst_name="Saint"\n\tnickname=nick_the_victorious\n') + b"random_seed=222\n"))
    return s


def test_a_current_save_missing_r23s_fix_runs_r23_alone(tmp_path, saves, capsys):
    """djdarcy (2026-11-01): an updated save skips what it already has and gets what is left, by default."""
    s, g = current_save(saves), localized_game(tmp_path)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g))
    assert code == 0 and out.startswith("READY") and "1 patch(es) run" in out
    st = steps_of(out)
    assert "runs" in st["R23"] and "needed: 1 nickname without text" in st["R23"]
    assert "done: none found" in st["R21"]
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint")
    assert code == 0, err
    assert cli.LAST_PLAN["ran"] == ["R23"]                                    # no other rule ran
    written = sf.read_save(saves / "Current__updated__1.20.1.2.ck3").gamestate
    assert b'\tnickname_text="the Victorious"\n' in written


def test_a_rule_the_record_shows_applied_is_skipped(tmp_path, saves, capsys):
    s = current_save(saves)
    record.append_update("222", "Current", {"date": "2026-10-31T10:00:00+00:00", "input": str(s),
                                            "tool": "ck3-save-updater 0.0.1",
                                            "patches": [{"id": "R23", "pack": "to_1_20"}]})
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    assert code == 0 and out.startswith("ALREADY CURRENT")
    assert "already applied (record: 2026-10-31 10:00)" in steps_of(out)["R23"]


def test_a_rule_with_no_detector_and_no_record_does_not_run(tmp_path, saves, capsys, monkeypatch):
    s = current_save(saves)
    monkeypatch.delitem(D.DETECTORS, "R10")                        # as a rule with no detector
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    r10 = steps_of(out)["R10"]
    assert "skipped" in r10 and "unknown: not in the record and no detector; name it with --rules to run it" in r10


def test_the_transplant_never_runs_on_a_current_save_without_rules(tmp_path, saves, capsys, monkeypatch):
    from ck3_save_migrator.rules import Rule
    real = Rule.run

    def guarded(self, save, ctx):
        if self.id in ("R14", "R15", "R16", "R17"):
            pytest.fail(f"the transplant ran ({self.id})")
        return real(self, save, ctx)
    monkeypatch.setattr(Rule, "run", guarded)
    s, g = current_save(saves), localized_game(tmp_path)
    ref = TU.ref_save(tmp_path, "Ref.ck3", seed=b"random_seed=333\n")     # a reference: only the guard stops it
    code, out, err = run(capsys, "update", str(s), "--game-dir", str(g), "--no-lint", "--reference", str(ref),
                         "--old-game-dir", str(g))
    assert code == 0, err
    assert not {"R14", "R15", "R16", "R17"} & set(cli.LAST_PLAN["ran"])
    assert "skipped" in steps_of(out)["R14"]


def test_rules_still_select_on_a_current_save(tmp_path, saves, capsys):
    s, g = current_save(saves), localized_game(tmp_path)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--rules", "all,-R23")
    assert code == 0 and out.startswith("ALREADY CURRENT") and "not selected" in steps_of(out)["R23"]
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(g), "--rules", "R21")
    assert " runs " in steps_of(out)["R21"] and "skipped" in steps_of(out)["R23"]     # only the named rule


def test_a_record_naming_this_tool_version_skips_the_re_check(tmp_path, saves, capsys, monkeypatch):
    s = current_save(saves)
    record.append_update("222", "Current", {"date": "d", "tool": f"ck3-save-updater {get_base_version()}"})
    monkeypatch.setattr(sf, "read_save", lambda *a, **k: pytest.fail("a full read"))
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    assert code == 0 and "re-check skipped: the record of Current says this tool" in out
    assert out.startswith("ALREADY CURRENT") and "needed:" not in out


def test_a_record_naming_an_older_version_re_checks(tmp_path, saves, capsys):
    s = current_save(saves)
    record.append_update("222", "Current", {"date": "d", "tool": "ck3-save-updater 0.0.1"})
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)))
    assert code == 0 and "needed: 1 nickname without text" in steps_of(out)["R23"]


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


# --------------------------------------------------------------------------- 9. the detector cache (S1 unit 1)
def counting(monkeypatch, rule_ids):
    """One counting detector standing in for the shared one behind ``rule_ids``; returns the call list."""
    calls = []
    real = D.DETECTORS[rule_ids[0]]

    def shared(g, env):
        calls.append(g)
        return real(g, env)
    for rid in rule_ids:
        monkeypatch.setitem(D.DETECTORS, rid, shared)
    return calls


def test_rules_that_share_a_detector_read_the_save_once(monkeypatch):
    calls = counting(monkeypatch, ["R8", "R9", "R10", "R12"])
    g, env = fixture_save().gamestate, D.Env()
    got = [D.detect(r, g, env) for r in ("R8", "R9", "R10", "R12")]
    assert len(calls) == 1
    assert all(x is got[0] for x in got) and got[0].state == "needed"


def test_another_gamestate_object_is_judged_again_even_with_the_same_bytes(monkeypatch):
    """Never keyed by content or path: a gamestate an edit replaced must be read afresh (a dry run and a real run
    on the same file never share a verdict)."""
    calls = counting(monkeypatch, ["R8", "R9"])
    g, env = fixture_save().gamestate, D.Env()
    twin = bytes(bytearray(g))
    assert twin == g and twin is not g
    D.detect("R8", g, env)
    D.detect("R9", twin, env)
    D.detect("R9", g, env)
    assert len(calls) == 3                       # the twin is read; returning to g reads again (one entry per detector)


def test_a_new_env_starts_empty(monkeypatch):
    calls = counting(monkeypatch, ["R8", "R9"])
    g = fixture_save().gamestate
    D.detect("R8", g, D.Env())
    D.detect("R9", g, D.Env())
    assert len(calls) == 2


def test_check_reads_a_shared_detector_once(tmp_path, capsys, monkeypatch):
    calls = counting(monkeypatch, ["R8", "R9", "R10", "R12"])
    s = tmp_path / "f.ck3"
    s.write_bytes(build_ck3(meta=RULES_META, body=BODY))
    assert cli.main(["check", str(s), "--game-dir", str(localized_game(tmp_path))]) == 0
    out = capsys.readouterr().out
    assert len(calls) == 1
    assert sum(1 for ln in out.splitlines() if "no rites/faiths database" in ln) == 4    # every rule still says it
