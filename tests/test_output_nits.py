"""S3 (a): the plan's output nits, one test per item (the wording djdarcy approves is listed in the PR).

1. a save one hotfix behind the game is ALREADY CURRENT "on the game's version line", not "at the game's version";
2. verbs agree with their list ("which is skipped" / "which are skipped", "name it" / "name them");
3. RECORD's pre-filled rows: one per input, a long value on its own lines under the value column, the record named
   once at the end;
4. R23's detector counts only what R23 can fix with the listed mods; the rest is reported apart;
5. a run patch whose done_command status ran says so on its row;
6. `help` for a patch whose pack is not installed says so.
"""

from __future__ import annotations

import pytest

from ck3_save_migrator import cli, config, detect as D
from ck3_save_migrator import plan as PL
from ck3_save_migrator import record
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3
from tests.test_detect import localized_game
from tests.test_requirements import done_pack
from tests.test_update import game, run

saves = TU.saves
no_reference_from_the_environment = TU.no_reference_from_the_environment


def current_save(saves, name="Current.ck3", body_extra: bytes = b"", seed: bytes = b"random_seed=5\n"):
    s = saves / name
    s.write_bytes(build_ck3(meta=TU.REF_META, body=TU.REF_BODY.replace(b'\tfirst_name="Saint"\n',
                                                                       b'\tfirst_name="Saint"\n' + body_extra)
                            + seed))
    return s


# --------------------------------------------------------------------------- 1. the hotfix verdict
def test_a_save_one_hotfix_behind_is_on_the_games_version_line(tmp_path, saves, capsys):
    s = current_save(saves)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path, "1.20.1.3")), "--plain")
    assert code == 0
    assert out.splitlines()[0].startswith("ALREADY CURRENT  the save is on the game's version line (1.20); no pack is "
                                          "selected for it; nothing to do")
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(game(tmp_path, "1.20.1.2", "Same")), "--plain")
    assert out.splitlines()[0].startswith("ALREADY CURRENT  the save is at the game's version and no pack is "
                                          "selected for it; nothing to do")


# --------------------------------------------------------------------------- 2. verbs that agree with their list
def test_skipped_needs_agrees_with_its_list():
    assert PL.skipped_needs(["R14"]) == "needs R14, which is skipped"
    assert PL.skipped_needs(["R14", "R16"]) == "needs R14, R16, which are skipped"


def test_a_step_whose_prerequisites_are_skipped_says_is_or_are(tmp_path, saves):
    """The plan's site, both forms: P0 and P1 are skipped (an unmet need); P2 needs P1 alone, P3 both."""
    from tests.test_requirements import run_pack
    run = '\n[run]\ncommand = ["@@python@@", "x.py", "@@input@@", "@@output@@", "@@w@@"]\nneeds = ["w"]\n'
    run_pack("chain", {"P0": run, "P1": run, "P2": 'requires = ["P1"]\n' + run,
                       "P3": 'requires = ["P0", "P1"]\n' + run})
    steps = {x.id: x for x in PL.plan_update(TU.ref_save(saves, "A.ck3"), game_dir=str(game(tmp_path)),
                                             allow_run=True, variables={"P2.w": "x", "P3.w": "y"}).steps}
    assert steps["P1"].reason.startswith("needs --var w")
    assert steps["P2"].reason == "needs P1, which is skipped"
    assert steps["P3"].reason == "needs P0, P1, which are skipped"


@pytest.mark.parametrize("ids,word", [(["R21"], "name it in --rules to run it anyway"),
                                       (["R20", "R21"], "name them in --rules to run them anyway")])
def test_skipped_by_config_agrees_with_its_list(tmp_path, capsys, ids, word):
    assert word in cli.skipped_by_config(ids)
    config.write_disabled(ids)
    s = tmp_path / "a.ck3"
    s.write_bytes(build_ck3(meta=TU.OLD_META, body=TU.OLD_BODY + TU.SEED))
    cli.main(["check", str(s)])
    assert word in capsys.readouterr().out


# --------------------------------------------------------------------------- 3. long pre-fill lines
def test_a_long_pre_fill_goes_under_its_column_and_names_the_record_once(tmp_path, saves, capsys, monkeypatch):
    long = tmp_path / ("a_folder_with_a_long_name_" * 4) / "tools"
    long.mkdir(parents=True)
    s = current_save(saves, seed=b"random_seed=7\n")
    record.append_update("7", "Current", {"date": "d", "tool": "ck3-save-updater 0.0.1", "inputs": {
        "vars": {"tools_dir": long.as_posix(), "witness": "W1"}, "transplant": "off"}})
    monkeypatch.setenv("COLUMNS", "100")
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)), "--plain")
    lines = out.splitlines()
    head = next(i for i, ln in enumerate(lines) if "pre-filled: --var tools_dir" in ln)
    col = lines[head].index("--var tools_dir")
    assert long.as_posix() not in lines[head]                                     # the value is below it ...
    assert lines[head + 1].index(long.as_posix()[:20]) == col                     # ... under the value column
    assert any(ln.endswith("pre-filled: --var witness=W1") for ln in lines)       # a short one stays on its row
    assert any("pre-filled: --transplant off" in ln for ln in lines)
    assert out.count("from the record of Current") == 1 and "(from the record of Current)" in out


# --------------------------------------------------------------------------- 4. R23 counts what it can fix
UNLISTED = b"\tnickname=VIET_nick_crow_lady\n"            # play6: a nickname whose mod the save does not list
LISTED = b"\tnickname=nick_the_victorious\n"


def test_r23_counts_only_what_the_listed_mods_can_fix(tmp_path, saves, capsys):
    other = saves / "Other.ck3"
    other.write_bytes(build_ck3(meta=TU.REF_META, body=TU.REF_BODY
                                .replace(b'\tfirst_name="Saint"\n', b'\tfirst_name="Saint"\n' + LISTED)
                                .replace(b'\tfirst_name="Head"\n', b'\tfirst_name="Head"\n' + UNLISTED)
                                + b"random_seed=6\n"))
    g = localized_game(tmp_path)
    code, out, _ = run(capsys, "status", str(other), "--game-dir", str(g), "--plain")
    assert code == 0 and out.startswith("READY")
    assert ("needed: 1 nickname without text; not fixable: 1 nickname whose text no listed mod has"
            in " ".join(out.split()))


def test_a_save_whose_only_finding_is_unfixable_is_already_current(tmp_path, saves, capsys):
    s = current_save(saves, body_extra=UNLISTED)
    code, out, _ = run(capsys, "status", str(s), "--game-dir", str(localized_game(tmp_path)), "--plain")
    assert code == 0 and out.startswith("ALREADY CURRENT")
    flat = " ".join(out.split())
    assert "done: nothing it can fix; not fixable: 1 nickname whose text no listed mod has" in flat
    assert "R23: 1 nickname whose text no listed mod has; it stays as it is" in flat
    from ck3_save_migrator import savefile as sf
    d = D.detect("R23", sf.read_save(s).gamestate, D.Env(game_dir=tmp_path / "CK3" / "game"))
    assert d.state == "done" and d.left == ["1 nickname whose text no listed mod has"]


# --------------------------------------------------------------------------- 5. done_command during status
def test_a_done_command_status_runs_says_so_on_its_row(tmp_path, saves):
    done_pack(tmp_path)
    s = TU.ref_save(saves, "A.ck3")
    q1 = next(x for x in PL.plan_update(s, game_dir=str(game(tmp_path)), allow_run=True).steps if x.id == "Q1")
    assert "; runs `@@python@@ " in q1.reason and q1.reason.endswith("` to check")
    q1 = next(x for x in PL.plan_update(s, game_dir=str(game(tmp_path)), allow_run=False).steps if x.id == "Q1")
    assert "to check" not in q1.reason                       # not trusted: nothing ran, so nothing is said to


# --------------------------------------------------------------------------- 6. help for an absent pack's patch
def test_help_for_a_patch_whose_pack_is_not_installed(capsys):
    assert cli.main(["help", "G1"]) == 1
    err = capsys.readouterr().err
    assert "no pack found holds patch G1; `ck3update packs` lists the packs found" in err
    assert cli.main(["help", "not-a-thing"]) == 1
    assert "no rule, patch or pack named 'not-a-thing'" in capsys.readouterr().err
