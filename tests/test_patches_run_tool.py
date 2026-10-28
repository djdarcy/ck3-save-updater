"""``tool = "<name>"`` in a run patch: the script ``<scripts folder>/<name>.py``, run by the same interpreter with
``args``, exactly as ``command = ["@@python@@", "<scripts folder>/<name>.py", *args]`` would run it. dazzlecmd-lib is
not involved. The scripts folder is the ``scripts_dir`` variable, else ``CK3SM_SCRIPTS_DIR``, else the source
checkout's ``tests/one-offs``; with none of them the patch is refused, naming the missing folder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator import tools
from ck3_save_migrator.patches import PatchError
from ck3_save_migrator.patches.model import load_patch
from tests.test_patches_run import EDIT_SCRIPT, a_save, run_rule

ARGS = ["@@input@@", "@@output@@"]


def tool_pack(root: Path, run_table: str) -> Path:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "edit_save.py").write_text(EDIT_SCRIPT, encoding="utf-8")
    pack = root / "pack"
    (pack / "Z1-run").mkdir(parents=True, exist_ok=True)
    (pack / "pack.toml").write_text('format = 1\nid = "p"\ntitle = "p"\norder = ["Z1"]\n', encoding="utf-8")
    (pack / "Z1-run" / "patch.toml").write_text(
        'format = 1\nid = "Z1"\nname = "run-edit"\ntitle = "edit x"\nsince = "1.20"\n\n[run]\n' + run_table,
        encoding="utf-8")
    return pack


TOOL = 'tool = "edit_save"\nargs = ["@@input@@", "@@output@@"]\n'


@pytest.fixture
def no_scripts_folder(monkeypatch):
    monkeypatch.delenv("CK3SM_SCRIPTS_DIR", raising=False)
    monkeypatch.setattr(tools, "checkout_scripts_dir", lambda: None)


def test_a_tool_run_patch_gives_the_same_bytes_as_running_the_script_by_hand(tmp_path, monkeypatch,
                                                                              no_scripts_folder):
    monkeypatch.chdir(tmp_path)
    pack = tool_pack(tmp_path, TOOL)
    src = a_save(tmp_path)
    by_hand = tmp_path / "by_hand.ck3"
    r = subprocess.run([sys.executable, str(tmp_path / "scripts" / "edit_save.py"), str(src), str(by_hand)])
    assert r.returncode == 0
    save = sf.read_save(src)
    res = run_rule(pack, save, {"scripts_dir": str(tmp_path / "scripts")})
    assert res.edited == 1 and res.extra["exit_code"] == 0
    assert save.gamestate == sf.read_save(by_hand).gamestate
    assert b"\tx=99\n" in save.gamestate


def test_the_scripts_folder_can_come_from_the_environment(tmp_path, monkeypatch, no_scripts_folder):
    pack = tool_pack(tmp_path, TOOL)
    monkeypatch.setenv("CK3SM_SCRIPTS_DIR", str(tmp_path / "scripts"))
    save = sf.read_save(a_save(tmp_path))
    assert run_rule(pack, save, {}).edited == 1 and b"\tx=99\n" in save.gamestate


def test_args_take_templates_and_list_variables(tmp_path, no_scripts_folder):
    out = tmp_path / "args.txt"
    pack = tool_pack(tmp_path, f'tool = "edit_save"\nargs = {json.dumps(ARGS + [str(out), "@@pairs@@"])}\n')
    run_rule(pack, sf.read_save(a_save(tmp_path)), {"scripts_dir": str(tmp_path / "scripts"), "pairs": ["a", "b c"]})
    assert out.read_text(encoding="utf-8").split("\n") == ["a", "b c"]


def test_with_no_scripts_folder_the_patch_is_refused_naming_it(tmp_path, no_scripts_folder):
    pack = tool_pack(tmp_path, TOOL)
    save = sf.read_save(a_save(tmp_path))
    before = save.gamestate
    with pytest.raises(PatchError, match="needs a scripts folder.*scripts_dir.*CK3SM_SCRIPTS_DIR"):
        run_rule(pack, save, {})
    assert save.gamestate == before


def test_a_tool_missing_from_the_scripts_folder_is_refused_naming_it(tmp_path, no_scripts_folder):
    pack = tool_pack(tmp_path, 'tool = "nope"\n')
    with pytest.raises(PatchError, match=r"run.tool 'nope'.*nope\.py"):
        run_rule(pack, sf.read_save(a_save(tmp_path)), {"scripts_dir": str(tmp_path / "scripts")})


def test_a_tool_run_patch_from_a_folder_needs_allow_run_and_runs_nothing_without_it(tmp_path, no_scripts_folder):
    marker = tmp_path / "ran.txt"
    pack = tool_pack(tmp_path, TOOL)
    (tmp_path / "scripts" / "edit_save.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\n", encoding="utf-8")
    with pytest.raises(PatchError, match="a run patch runs a program with your permissions; pass --allow-run"):
        run_rule(pack, sf.read_save(a_save(tmp_path)), {"scripts_dir": str(tmp_path / "scripts")}, allow_run=False)
    assert not marker.exists()


@pytest.mark.parametrize("table, message", [
    ('tool = "edit_save"\ncommand = ["x"]\n', "exactly one of 'command' or 'tool'"),
    ('needs = []\n', "exactly one of 'command' or 'tool'"),
    ('command = ["x"]\nargs = ["y"]\n', "'run.args' goes with 'run.tool'"),
    ('tool = "../edit_save"\n', "'run.tool' must be a script name"),
    ('tool = "edit_save"\nargs = "x"\n', "'run.args' must be a list of strings"),
])
def test_a_malformed_tool_table_is_refused(tmp_path, table, message):
    pack = tool_pack(tmp_path, table)
    with pytest.raises(PatchError, match=message):
        load_patch(pack / "Z1-run", from_disk=True, context_fields=set())
