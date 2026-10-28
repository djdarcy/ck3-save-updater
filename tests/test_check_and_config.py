"""``check`` (each selected patch's verdict on a save, read only) and ``disable`` / ``enable`` / ``disabled`` (rules
turned off in the player's config file).

The conftest points ``CK3SM_CONFIG`` at a fresh file for every test, so no test reads or writes a real config.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli, config
from ck3_save_migrator import savefile as sf
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3


def a_save(root: Path, name: str = "My_Old_Campaign.ck3") -> Path:
    p = root / name
    p.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    return p


def verdicts(out: str) -> dict:
    """{patch id: verdict} from check's lines."""
    rows = {}
    for line in out.splitlines():
        parts = line.split()
        if line.startswith("  ") and len(parts) >= 3 and parts[2] in ("needed", "done", "unknown", "fails"):
            rows[parts[0]] = parts[2]
    return rows


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = cli.main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


# --------------------------------------------------------------------------- check
def test_check_says_needed_and_unknown_and_writes_nothing(tmp_path, capsys):
    src = a_save(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir()), src.read_bytes()
    code, out, _ = run(capsys, "check", str(src))
    v = verdicts(out)
    assert code == 0
    assert v["R1"] == v["R4"] == v["R5"] == v["R7"] == "needed"       # the fixture has what each one fixes
    assert v["R2"] == v["R21"] == "unknown"                           # Python rules with no declarative patch
    assert "patch(es):" in out.splitlines()[-1]
    assert (sorted(p.name for p in tmp_path.iterdir()), src.read_bytes()) == before


def test_after_migrate_check_says_done(tmp_path, capsys):
    out_save = tmp_path / "out.ck3"
    assert run(capsys, "migrate", str(a_save(tmp_path)), "--no-lint", "-o", str(out_save))[0] == 0
    code, out, _ = run(capsys, "check", str(out_save))
    v = verdicts(out)
    assert code == 0
    assert {v[i] for i in ("R1", "R4", "R5", "R7", "R11")} == {"done"}
    assert "0 needed" in out.splitlines()[-1]


def test_check_reports_a_failing_expect_naming_it_and_exits_5(tmp_path, capsys):
    pack = tmp_path / "pack"
    (pack / "E1-x").mkdir(parents=True)
    (pack / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["E1"]\n', encoding="utf-8")
    (pack / "E1-x" / "patch.toml").write_text(
        'format = 1\nid = "E1"\nname = "must-find"\ntitle = "t"\nsince = "1.20"\n\n[[edit]]\npath = "meta_data"\n'
        'op = "delete_key"\nkey = "not_there"\nexpect = 1\n', encoding="utf-8")
    code, out, err = run(capsys, "check", str(a_save(tmp_path)), "--rules", "R7", "--pack", str(pack))
    assert code == 5
    line = next(ln for ln in out.splitlines() if ln.split()[:1] == ["E1"])
    assert "fails" in line and "#1" in line and "meta_data" in line and "found 0" in line
    assert "1 fail(s)" in out and "would fail" in err


def test_check_never_runs_a_packs_code(tmp_path, capsys):
    marker = tmp_path / "ran.txt"
    pack = tmp_path / "pack"
    (pack / "S1-x").mkdir(parents=True)
    (pack / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["S1"]\n', encoding="utf-8")
    (pack / "S1-x" / "patch.toml").write_text(
        'format = 1\nid = "S1"\nname = "code"\ntitle = "t"\nsince = "1.20"\nscript = "fix.py:fix"\n',
        encoding="utf-8")
    (pack / "S1-x" / "fix.py").write_text(f"open({str(marker)!r}, 'w').write('x')\ndef fix(*a): pass\n",
                                          encoding="utf-8")
    code, out, _ = run(capsys, "check", str(a_save(tmp_path)), "--rules", "R7", "--pack", str(pack), "--allow-run")
    assert code == 0 and verdicts(out)["S1"] == "unknown" and not marker.exists()


# --------------------------------------------------------------------------- disable / enable
def test_disable_leaves_a_rule_out_of_all_and_says_so(tmp_path, capsys):
    assert run(capsys, "disable", "R21")[0] == 0
    code, out, _ = run(capsys, "migrate", str(a_save(tmp_path)), "--no-lint", "-o", str(tmp_path / "o.ck3"),
                       "--report", str(tmp_path / "r.json"))
    assert code == 0
    assert out.count("skipped by your config: R21") == 1
    ran = [ln.split()[0] for ln in out.splitlines() if ln.startswith("    R")]
    assert "R21" not in ran and "R1" in ran


def test_naming_a_disabled_rule_runs_it_anyway(tmp_path, capsys):
    run(capsys, "disable", "R21")
    code, out, _ = run(capsys, "migrate", str(a_save(tmp_path)), "--rules", "all,R21", "--no-lint",
                       "-o", str(tmp_path / "o.ck3"))
    assert code == 0 and "skipped by your config" not in out
    assert "R21" in [ln.split()[0] for ln in out.splitlines() if ln.startswith("    R")]


def test_enable_restores_it(tmp_path, capsys):
    run(capsys, "disable", "dead-liege-cycles")                      # by name: stored as its id
    assert config.disabled_ids() == ["R21"]
    assert run(capsys, "enable", "R21")[0] == 0 and config.disabled_ids() == []
    code, out, _ = run(capsys, "migrate", str(a_save(tmp_path)), "--no-lint", "-o", str(tmp_path / "o.ck3"))
    assert "skipped by your config" not in out
    assert "R21" in [ln.split()[0] for ln in out.splitlines() if ln.startswith("    R")]


def test_check_applies_the_config_too(tmp_path, capsys):
    run(capsys, "disable", "R5")
    code, out, _ = run(capsys, "check", str(a_save(tmp_path)))
    assert "skipped by your config: R5" in out and "R5" not in verdicts(out)
    assert "R5" in verdicts(run(capsys, "check", str(a_save(tmp_path)), "--rules", "all,R5")[1])


def test_disabled_lists_the_rules_turned_off(capsys):
    assert "no rules are turned off" in run(capsys, "disabled")[1]
    run(capsys, "disable", "R21")
    run(capsys, "disable", "R5")
    out = run(capsys, "disabled")[1]
    assert [ln.split()[:2] for ln in out.splitlines()[:2]] == [["R5", "empty-keys"], ["R21", "dead-liege-cycles"]]


@pytest.mark.parametrize("verb", ["disable", "enable"])
def test_an_unknown_id_is_refused_listing_the_known_ones(capsys, verb):
    code, _, err = run(capsys, verb, "R99")
    assert code == 1 and "unknown rule 'R99'" in err and "R21=dead-liege-cycles" in err
    assert not config.config_path().exists()


def test_the_config_lands_only_under_ck3sm_config(tmp_path, capsys, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for var in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    target = tmp_path / "elsewhere" / "my.toml"
    monkeypatch.setenv("CK3SM_CONFIG", str(target))
    run(capsys, "disable", "R21")
    assert target.read_text(encoding="utf-8").splitlines()[-1] == 'disabled = ["R21"]'
    assert not any(home.rglob("*"))


def test_the_default_config_path_per_system(tmp_path, monkeypatch):
    monkeypatch.delenv("CK3SM_CONFIG")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert config.config_path() == tmp_path / "Roaming" / "ck3-save-migrator" / "config.toml"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    assert config.config_path() == Path(os.path.expanduser("~")) / ".config" / "ck3-save-migrator" / "config.toml"


def test_a_broken_config_is_refused_naming_the_file(capsys):
    p = config.config_path()
    p.parent.mkdir(parents=True)
    p.write_text("disabled = R21\n", encoding="utf-8")
    code, _, err = run(capsys, "disabled")
    assert code == 1 and str(p) in err and "not valid TOML" in err
