"""A patch that fails is never silent.

``migrate`` prints each failed patch with its message (an ``expect`` or ``need_path`` that did not hold, a run
command that failed or ran past its ``timeout``), writes nothing, and exits 5. A run command's output goes to files,
and only the tail of its stderr is reported.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import PatchError, apply_patch, load_patch, rules_from_pack, shipped_pack_folder
from ck3_save_migrator.patches.engine import plan
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS, context_values
from ck3_save_migrator.rules import RuleContext
from tests.fixtures.make_ck3 import build_ck3
from tests.test_patches_run import COMMAND, FAIL_SCRIPT, a_save, make_pack, run_rule

META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'


@pytest.fixture
def no_game(monkeypatch):
    monkeypatch.setenv("CK3_GAME_DIR", "none")
    monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")


def expect_pack(root: Path) -> Path:
    pack = root / "pack"
    (pack / "E1-x").mkdir(parents=True)
    (pack / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["E1"]\n', encoding="utf-8")
    (pack / "E1-x" / "patch.toml").write_text(
        'format = 1\nid = "E1"\nname = "must-find"\ntitle = "t"\nsince = "1.20"\n\n[[edit]]\npath = "stuff"\n'
        'op = "delete_key"\nkey = "not_there"\nexpect = 1\n', encoding="utf-8")
    return pack


def migrate(tmp_path: Path, *extra: str) -> int:
    return cli.main(["migrate", str(a_save(tmp_path)), "--rules", "R7", "--no-lint", "-o", str(tmp_path / "o.ck3"),
                     *extra])


def test_a_failed_expect_stops_migrate_naming_the_patch_and_writes_nothing(tmp_path, no_game, capsys):
    code = migrate(tmp_path, "--pack", str(expect_pack(tmp_path)))
    out, err = capsys.readouterr()
    assert code == 5 and not (tmp_path / "o.ck3").exists()
    assert "patch E1 (must-find) failed" in err and "expected 1, found 0" in err and "nothing written" in err
    assert "already migrated" not in out + err


def test_a_failed_command_stops_migrate_with_its_exit_code_and_stderr(tmp_path, no_game, capsys):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"], script=FAIL_SCRIPT)
    code = migrate(tmp_path, "--pack", str(pack), "--var", f"tools_dir={tmp_path / 'tools'}", "--allow-run")
    err = capsys.readouterr().err
    assert code == 5 and not (tmp_path / "o.ck3").exists()
    assert "patch Z1 (run-edit) failed" in err and "exit code 7" in err and "something broke" in err


def test_a_failure_writes_no_output_for_either_faith_shape(tmp_path, no_game, capsys, monkeypatch):
    # both shapes run before either is written: a failure after R10 leaves no file at all
    from ck3_save_migrator import cli as c
    monkeypatch.setattr(c, "custom_faith_names", lambda g: ["My Faith"])
    monkeypatch.setattr(c, "find_reference", lambda a: tmp_path / "ref.ck3")
    monkeypatch.setattr(c, "missing_prerequisites", lambda rules: [])     # R10 alone, without R8's reference work
    code = cli.main(["migrate", str(a_save(tmp_path)), "--rules", "R7,R10", "--pack", str(expect_pack(tmp_path)),
                     "--no-lint", "-o", str(tmp_path / "o.ck3")])
    assert code == 5 and not list(tmp_path.glob("o*.ck3"))


def test_a_command_past_its_timeout_is_stopped_and_fails(tmp_path):
    slow = "import time\ntime.sleep(60)\n"
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"], script=slow)
    toml = pack / "Z1-run" / "patch.toml"
    toml.write_text(toml.read_text(encoding="utf-8") + "timeout = 1\n", encoding="utf-8")
    save = sf.read_save(a_save(tmp_path))
    res = run_rule(pack, save, {"tools_dir": str(tmp_path / "tools")})
    assert res.edited == 0 and res.extra["exit_code"] is None
    assert "did not finish within 1 seconds" in res.extra["failed"]


@pytest.mark.parametrize("value", ["0", "-3", '"ten"', "true"])
def test_a_bad_timeout_is_refused(tmp_path, value):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"])
    toml = pack / "Z1-run" / "patch.toml"
    toml.write_text(toml.read_text(encoding="utf-8") + f"timeout = {value}\n", encoding="utf-8")
    with pytest.raises(PatchError, match="run.timeout"):
        rules_from_pack(pack, allow_run=True)


def test_a_flood_of_output_is_not_kept_and_only_the_stderr_tail_is_reported(tmp_path):
    flood = ("import sys\nsys.stdout.write('o' * 30_000_000)\n"
             "for i in range(200_000):\n    sys.stderr.write(f'line {i}\\n')\nsys.exit(2)\n")
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"], script=flood)
    res = run_rule(pack, sf.read_save(a_save(tmp_path)), {"tools_dir": str(tmp_path / "tools")})
    assert res.extra["exit_code"] == 2
    assert res.extra["stderr"] == [f"line {i}" for i in range(199_980, 200_000)]


def r7():
    return load_patch(shipped_pack_folder().joinpath("R7-version-bump"), from_disk=False,
                      context_fields=CONTEXT_FIELDS)


def test_the_r7_patch_fails_on_a_gamestate_without_meta_data():
    # (a whole save cannot be built without meta_data, so the plan is made on the gamestate alone)
    pl = plan(b"other={\n\tversion=1\n}\nstuff={\n}\n", r7(), context_values(RuleContext()))
    assert pl.failure and "need_path" in pl.failure and "R7-version-bump" in pl.failure and not pl.edits


def test_the_r7_patch_still_bumps_a_save_with_meta_data():
    save = sf.parse_save(build_ck3(meta=META, body=b""))
    pl = apply_patch(save, r7(), context_values(RuleContext()))
    assert pl.failure is None and b'version="1.20.1.2"' in save.gamestate
