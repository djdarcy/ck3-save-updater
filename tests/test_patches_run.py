"""Run patches: a standalone script run over the save as it is, its own process.

The scripts these tests run are written into ``tmp_path``; they read their input and write their output there.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import PatchError, rules_from_pack
from ck3_save_migrator.rules import RuleContext
from tests.fixtures.make_ck3 import build_ck3

META = b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n'
BODY = b"stuff={\n\tx=1\n\ty=2\n}\n"

EDIT_SCRIPT = """import sys
from pathlib import Path
from ck3_save_migrator import savefile as sf
s = sf.read_save(sys.argv[1])
s.set_gamestate(s.gamestate.replace(b"\\tx=1\\n", b"\\tx=99\\n"))
sf.write_save(s, sys.argv[2])
if len(sys.argv) > 3:
    Path(sys.argv[3]).write_text("\\n".join(sys.argv[4:]), encoding="utf-8")
"""
# writes a valid output and still exits 7: the exit code alone must stop it being applied
FAIL_SCRIPT = EDIT_SCRIPT + "sys.stderr.write('first line\\nsomething broke\\n')\nsys.exit(7)\n"


def make_pack(root: Path, command: list[str], needs: list[str] = (), script: str = EDIT_SCRIPT) -> Path:
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools" / "edit_save.py").write_text(script, encoding="utf-8")
    pack = root / "pack"
    (pack / "Z1-run").mkdir(parents=True, exist_ok=True)
    (pack / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["Z1"]\n', encoding="utf-8")
    cmd = "[" + ", ".join('"' + c.replace("\\", "\\\\") + '"' for c in command) + "]"
    nd = "[" + ", ".join(f'"{n}"' for n in needs) + "]"
    (pack / "Z1-run" / "patch.toml").write_text(
        'format = 1\nid = "Z1"\nname = "run-edit"\ntitle = "edit x"\nsince = "1.20"\n\n[run]\n'
        f"command = {cmd}\nneeds = {nd}\n", encoding="utf-8")
    return pack


def a_save(root: Path) -> Path:
    p = root / "My_Old_Campaign.ck3"
    p.write_bytes(build_ck3(meta=META, body=BODY))
    return p


COMMAND = ["@@python@@", "-I", "@@tools_dir@@/edit_save.py", "@@input@@", "@@output@@"]


def run_rule(pack: Path, save, vars: dict, allow_run=True):
    (rule,) = rules_from_pack(pack, allow_run=allow_run)
    ctx = RuleContext()
    ctx.state["patch_vars"] = vars
    return rule.run(save, ctx)


def test_a_run_patch_gives_the_same_bytes_as_running_the_script_by_hand(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"])
    src = a_save(tmp_path)
    by_hand = tmp_path / "by_hand.ck3"
    r = subprocess.run([sys.executable, "-I", str(tmp_path / "tools" / "edit_save.py"), str(src), str(by_hand)])
    assert r.returncode == 0
    save = sf.read_save(src)
    res = run_rule(pack, save, {"tools_dir": str(tmp_path / "tools")})
    assert res.edited == 1 and res.extra["exit_code"] == 0
    assert save.gamestate == sf.read_save(by_hand).gamestate
    assert b"\tx=99\n" in save.gamestate


def test_a_missing_needed_variable_is_refused_naming_it(tmp_path):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir", "witness"])
    with pytest.raises(PatchError, match="run.needs witness"):
        run_rule(pack, sf.read_save(a_save(tmp_path)), {"tools_dir": str(tmp_path / "tools")})


def test_an_unknown_variable_in_the_command_is_refused_naming_it(tmp_path):
    pack = make_pack(tmp_path, COMMAND + ["@@nowhere@@"], ["tools_dir"])
    with pytest.raises(PatchError, match="@@nowhere@@"):
        run_rule(pack, sf.read_save(a_save(tmp_path)), {"tools_dir": str(tmp_path / "tools")})


def test_a_failing_script_fails_closed_with_its_exit_code_and_stderr(tmp_path):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"], script=FAIL_SCRIPT)
    save = sf.read_save(a_save(tmp_path))
    before = save.gamestate
    res = run_rule(pack, save, {"tools_dir": str(tmp_path / "tools")})
    assert save.gamestate == before and res.edited == 0
    assert res.extra["exit_code"] == 7 and res.extra["stderr"][-1] == "something broke"
    assert "exit code 7" in res.extra["failed"] and "nothing applied" in res.extra["failed"]


def test_a_script_that_writes_no_output_fails_closed(tmp_path):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"], script="import sys\n")
    save = sf.read_save(a_save(tmp_path))
    res = run_rule(pack, save, {"tools_dir": str(tmp_path / "tools")})
    assert res.edited == 0 and "no output file" in res.extra["failed"]


def test_a_list_variable_written_as_a_whole_element_becomes_several_arguments(tmp_path):
    out = tmp_path / "args.txt"
    pack = make_pack(tmp_path, COMMAND + [str(out), "@@pairs@@", "tail"], ["tools_dir"])
    run_rule(pack, sf.read_save(a_save(tmp_path)), {"tools_dir": str(tmp_path / "tools"),
                                                    "pairs": ["a=1", "b c", "d"]})
    assert out.read_text(encoding="utf-8").split("\n") == ["a=1", "b c", "d", "tail"]


def test_a_run_patch_from_a_folder_needs_allow_run(tmp_path):
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"])
    with pytest.raises(PatchError, match="--allow-run"):
        rules_from_pack(pack)
    assert len(rules_from_pack(pack, allow_run=True)) == 1


def test_migrate_runs_a_pack_with_var_and_allow_run_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CK3_GAME_DIR", "none")
    monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")
    monkeypatch.chdir(tmp_path)
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"])
    src = a_save(tmp_path)
    args = ["migrate", str(src), "--rules", "R7", "--pack", str(pack), "--var", f"tools_dir={tmp_path / 'tools'}",
            "--no-lint", "-o", str(tmp_path / "out.ck3")]
    assert cli.main(args) == 1                                     # refused without --allow-run
    assert "--allow-run" in capsys.readouterr().err and not (tmp_path / "out.ck3").exists()
    assert cli.main(args + ["--allow-run"]) == 0
    g = sf.read_save(tmp_path / "out.ck3").gamestate
    assert b"\tx=99\n" in g and b'version="1.20.1.2"' in g     # R7, then the pack's run patch


def test_migrate_reads_variables_from_a_toml_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CK3_GAME_DIR", "none")
    monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")
    pack = make_pack(tmp_path, COMMAND, ["tools_dir"])
    tools = (tmp_path / "tools").as_posix()
    (tmp_path / "vars.toml").write_text(f'tools_dir = "{tools}"\n', encoding="utf-8")
    assert cli.main(["migrate", str(a_save(tmp_path)), "--rules", "R7", "--pack", str(pack), "--vars",
                     str(tmp_path / "vars.toml"), "--allow-run", "--no-lint", "-o", str(tmp_path / "o.ck3")]) == 0
    assert b"\tx=99\n" in sf.read_save(tmp_path / "o.ck3").gamestate


def test_the_migrate_help_shows_the_pack_options():
    r = subprocess.run([sys.executable, "-m", "ck3_save_migrator", "migrate", "--help"], capture_output=True, text=True)
    for opt in ("--pack", "--var", "--vars", "--allow-run"):
        assert re.search(re.escape(opt) + r"(?![\w-])", r.stdout), opt
