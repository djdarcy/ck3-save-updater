"""The player's own packs (userpacks.py): the standard folder, pack_dirs, code packs trusted once, the new commands.

The safety test comes first. An untrusted code pack in the folder must not run, and the test makes running it
impossible to miss: the two ways a pack's code runs (the script importer and the run-patch executor) are replaced
by functions that fail the test if called, then a whole update runs.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from ck3_save_migrator import cli, config
from ck3_save_migrator import userpacks as U
from ck3_save_migrator.patches import pack as P
from ck3_save_migrator.patches import read_pack
from ck3_save_migrator.patches.model import load_patch
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS
from tests.fixtures.make_ck3 import RULES_BODY, RULES_META, build_ck3

COPY_PY = """import shutil, sys
from pathlib import Path
shutil.copyfile(sys.argv[1], sys.argv[2])
Path(sys.argv[3]).write_text("ran", encoding="utf-8")
"""


# --------------------------------------------------------------------------- building packs
def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def decl_pack(folder: Path, pack_id: str, patch_id: str, *, default: bool = True) -> Path:
    """A pack of edits: one insert of <patch_id>_flag=yes into meta_data, done when the key is there."""
    write(folder / "pack.toml", f'format = 1\nid = "{pack_id}"\ntitle = "test"\norder = ["{patch_id}"]\n')
    write(folder / f"{patch_id}-flag" / "patch.toml",
          f'format = 1\nid = "{patch_id}"\nname = "{patch_id.lower()}-flag"\ntitle = "add a flag"\n'
          f'since = "1.20"\ndefault = {"true" if default else "false"}\n'
          f'done = {{ path = "meta_data", key = "{patch_id}_flag" }}\n\n'
          f'[[edit]]\npath = "meta_data"\nop = "insert"\nposition = "end"\npayload = "\\t{patch_id}_flag=yes\\n"\n')
    return folder


def code_pack(folder: Path, pack_id: str = "mycode", tools: Path | None = None, p: str = "C") -> Path:
    """A pack with code: a script patch (<p>1) and a run patch (<p>2) that copies the save and writes @@mark@@."""
    write(folder / "pack.toml", f'format = 1\nid = "{pack_id}"\ntitle = "code"\norder = ["{p}1", "{p}2"]\n')
    write(folder / "C1-script" / "patch.toml",
          f'format = 1\nid = "{p}1"\nname = "{p.lower()}1-script"\ntitle = "a script"\nsince = "1.20"\n'
          'script = "fix.py:apply"\n')
    write(folder / "C1-script" / "fix.py",
          "def apply(save, ctx, rule):\n    return rule.result(matched=1, edited=0)\n")
    write(folder / "C2-run" / "patch.toml",
          f'format = 1\nid = "{p}2"\nname = "{p.lower()}2-run"\ntitle = "a program"\nsince = "1.20"\n\n[run]\n'
          'command = ["@@python@@", "-I", "@@tools@@/copy.py", "@@input@@", "@@output@@", "@@mark@@"]\n'
          'needs = ["tools", "mark"]\n')
    if tools is not None:
        write(tools / "copy.py", COPY_PY)
    return folder


@pytest.fixture
def save(tmp_path) -> Path:
    s = tmp_path / "old.ck3"
    s.write_bytes(build_ck3(meta=RULES_META, body=RULES_BODY))
    return s


def migrate(tmp_path, save, capsys, *extra, name="out"):
    out, rep = tmp_path / f"{name}.ck3", tmp_path / f"{name}.json"
    code = cli.main(["migrate", str(save), "--reference", "none", "--no-lint", "-o", str(out), "--report", str(rep),
                     *extra])
    o, e = capsys.readouterr()
    report = json.loads(rep.read_text(encoding="utf-8")) if rep.is_file() else None
    return code, o, e, report


def ran(report) -> list[str]:
    return [r["id"] for r in report["rules"]]


@pytest.fixture
def code_not_reachable(monkeypatch):
    """The script importer and the run-patch executor fail the test if anything calls them."""
    def boom(*a, **k):
        pytest.fail("a pack's code was reached")
    monkeypatch.setattr(P, "_function", boom)
    monkeypatch.setattr(P, "run_patch", boom)


# --------------------------------------------------------------------------- safety
def test_an_untrusted_code_pack_in_the_folder_never_runs(tmp_path, save, capsys, code_not_reachable):
    code_pack(U.packs_dir() / "mycode")
    code, _, err, report = migrate(tmp_path, save, capsys)
    assert code == 0 and report is not None                         # the update completed; the skip changes nothing
    assert "your pack mycode" in err and "found, not trusted: run 'ck3update trust mycode' to let it run" in err
    assert "C1" not in ran(report) and "C2" not in ran(report)
    assert [(p["id"], p["kind"], p["state"]) for p in report["user_packs"]] == [("mycode", "code", "not trusted")]


def test_a_trusted_pack_edited_after_trusting_does_not_run(tmp_path, save, capsys, code_not_reachable):
    folder = code_pack(U.packs_dir() / "mycode")
    U.ensure_packs_dir()
    assert cli.main(["trust", "mycode"]) == 0
    (folder / "C1-script" / "fix.py").write_text("raise SystemExit('edited')\n", encoding="utf-8")
    code, _, err, report = migrate(tmp_path, save, capsys)
    assert code == 0 and "trust is for an earlier version of this pack (its files changed)" in err
    assert "C1" not in ran(report) and report["user_packs"][0]["state"] == "changed since trusted"


# --------------------------------------------------------------------------- the standard folder
def test_the_first_run_creates_the_folder_and_a_second_run_changes_nothing(tmp_path, save, capsys):
    folder = U.packs_dir()
    assert not folder.exists()
    assert cli.main(["rules"]) == 0
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    assert files == ["README.md", "_example-pack/X1-load-screen-name/patch.toml", "_example-pack/_X2-run-a-script/patch.toml",
                     "_example-pack/pack.toml", "_example-pack/vars.toml"]
    assert (folder / "README.md").read_text(encoding="utf-8").startswith("# ADD RULES HERE")
    stamps = {p: p.stat().st_mtime_ns for p in folder.rglob("*")}
    time.sleep(0.01)
    capsys.readouterr()
    assert migrate(tmp_path, save, capsys)[0] == 0
    assert {p: p.stat().st_mtime_ns for p in folder.rglob("*")} == stamps


def test_an_existing_folder_is_never_written_into(capsys):
    folder = U.packs_dir()
    write(folder / "README.md", "mine")
    assert cli.main(["packs"]) == 0
    assert (folder / "README.md").read_text(encoding="utf-8") == "mine"
    assert sorted(p.name for p in folder.iterdir()) == ["README.md"]


def test_the_example_pack_is_complete_and_valid():
    U.ensure_packs_dir()
    ex = U.packs_dir() / "_example-pack"
    pack = read_pack(ex)
    assert pack.id == "example" and [p.id for p in pack.ordered()] == ["X1"]
    run = load_patch(ex / "_X2-run-a-script", from_disk=True, context_fields=CONTEXT_FIELDS)
    assert run.kind == "run" and "@@tools_dir@@/my_fix.py" in " ".join(run.run["command"])
    assert U.read_vars_file(ex / "vars.toml", "vars.toml") == {}


# --------------------------------------------------------------------------- loading
def test_a_pack_of_edits_runs_in_the_same_call_from_either_folder_and_underscore_is_skipped(tmp_path, save, capsys):
    decl_pack(U.packs_dir() / "a", "a_pack", "A1")
    extra = tmp_path / "more packs"
    decl_pack(extra / "b", "b_pack", "B1")
    decl_pack(extra / "_off", "off_pack", "O1")
    config.write_config({"pack_dirs": [str(extra)]})
    code, _, _, report = migrate(tmp_path, save, capsys)
    assert code == 0 and ran(report)[-2:] == ["A1", "B1"] and "O1" not in ran(report)
    from ck3_save_migrator.savefile import read_save
    meta = read_save(tmp_path / "out.ck3").meta
    assert b"A1_flag=yes" in meta and b"B1_flag=yes" in meta and b"O1_flag" not in meta


def test_a_pack_folder_reached_twice_loads_once(tmp_path, save, capsys):
    decl_pack(U.packs_dir() / "a", "a_pack", "A1")
    config.write_config({"pack_dirs": [str(U.packs_dir())]})              # the standard folder named again
    code, _, _, report = migrate(tmp_path, save, capsys)
    assert code == 0 and ran(report).count("A1") == 1


def test_trust_lets_a_code_pack_run_without_allow_run_and_untrust_takes_it_back(tmp_path, save, capsys):
    tools, mark = tmp_path / "tools", tmp_path / "mark.txt"
    folder = code_pack(U.packs_dir() / "mycode", tools=tools)
    write(folder / "vars.toml", f'tools = "{tools.as_posix()}"\nmark = "{mark.as_posix()}"\n')
    U.ensure_packs_dir()
    assert cli.main(["trust", "mycode"]) == 0
    said = capsys.readouterr().out
    assert "C1 c1-script: runs Python code, fix.py:apply" in said and "C2 c2-run: runs the program" in said
    code, _, err, report = migrate(tmp_path, save, capsys)
    assert code == 0, err
    assert ran(report)[-2:] == ["C1", "C2"] and mark.read_text(encoding="utf-8") == "ran"
    assert report["user_packs"][0]["state"] == "runs" and report["user_packs"][0]["hash"] == U.pack_hash(folder)
    assert cli.main(["untrust", "mycode"]) == 0
    mark.unlink()
    code, _, err, report = migrate(tmp_path, save, capsys, name="again")
    assert code == 0 and "not trusted" in err and not mark.exists() and "C2" not in ran(report)


def test_allow_run_lets_an_untrusted_code_pack_run(tmp_path, save, capsys):
    tools, mark = tmp_path / "tools", tmp_path / "mark.txt"
    folder = code_pack(U.packs_dir() / "mycode", tools=tools)
    write(folder / "vars.toml", f'tools = "{tools.as_posix()}"\nmark = "{mark.as_posix()}"\n')
    code, _, _, report = migrate(tmp_path, save, capsys, "--allow-run")
    assert code == 0 and ran(report)[-2:] == ["C1", "C2"] and mark.is_file()


def test_a_packs_vars_toml_is_used_and_the_command_line_wins(tmp_path, save, capsys):
    tools, mark, other = tmp_path / "tools", tmp_path / "mark.txt", tmp_path / "other.txt"
    folder = code_pack(U.packs_dir() / "mycode", tools=tools)
    write(folder / "vars.toml", f'tools = "{tools.as_posix()}"\nmark = "{mark.as_posix()}"\n')
    code, _, err, _ = migrate(tmp_path, save, capsys, "--allow-run", "--var", f"mark={other.as_posix()}")
    assert code == 0, err
    assert other.is_file() and not mark.exists()


# --------------------------------------------------------------------------- refusals
def test_a_user_patch_with_a_built_in_id_is_refused(tmp_path, save, capsys):
    decl_pack(U.packs_dir() / "a", "a_pack", "R1")
    code, _, err, _ = migrate(tmp_path, save, capsys)
    assert code == 1 and "'R1', the id of a built-in rule" in err and str(U.packs_dir() / "a") in err


def test_two_packs_with_one_id_or_one_patch_id_are_refused(tmp_path, save, capsys):
    decl_pack(U.packs_dir() / "a", "same", "A1")
    decl_pack(U.packs_dir() / "b", "same", "B1")
    code, _, err, _ = migrate(tmp_path, save, capsys)
    assert code == 1 and "two of your packs have the id 'same'" in err
    assert str(U.packs_dir() / "a") in err and str(U.packs_dir() / "b") in err
    shutil.rmtree(U.packs_dir() / "b")
    decl_pack(U.packs_dir() / "b", "other", "A1")
    code, _, err, _ = migrate(tmp_path, save, capsys)
    assert code == 1 and "patch id 'A1' is in two of your packs" in err


# --------------------------------------------------------------------------- commands
def test_packs_lists_each_pack_with_its_state(tmp_path, capsys):
    decl_pack(U.packs_dir() / "a", "edits", "A1")
    code_pack(U.packs_dir() / "b", "fresh", p="F")
    changed = code_pack(U.packs_dir() / "c", "changed", p="G")
    decl_pack(U.packs_dir() / "d", "off", "D1")
    (U.packs_dir() / "e").mkdir()
    U.ensure_packs_dir()
    config.write_config({"disabled": ["D1"], "trusted": {"changed": U.pack_hash(changed)}})
    (changed / "new.txt").write_text("x", encoding="utf-8")
    assert cli.main(["packs"]) == 0
    out = capsys.readouterr().out
    lines = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ") and "not a pack" not in ln}
    assert "declarative" in lines["edits"] and "runs" in lines["edits"]
    assert "code" in lines["fresh"] and "not trusted" in lines["fresh"]
    assert "changed since trusted" in lines["changed"]
    assert "turned off" in lines["off"]
    assert f"(not a pack: no pack.toml)  {U.packs_dir() / 'e'}" in out
    assert f"folder: {U.packs_dir()}  (the standard folder)" in out


def test_rules_lists_your_packs_patches_with_their_pack(capsys):
    decl_pack(U.packs_dir() / "a", "edits", "A1")
    assert cli.main(["rules"]) == 0
    line = capsys.readouterr().out.splitlines()[-1]
    assert line.startswith("A1  a1-flag") and line.endswith("(your pack edits: runs)")


def test_disable_turns_off_a_user_patch_and_enable_turns_it_back_on(tmp_path, save, capsys):
    decl_pack(U.packs_dir() / "a", "edits", "A1")
    U.ensure_packs_dir()
    assert cli.main(["disable", "A1"]) == 0
    code, out, _, report = migrate(tmp_path, save, capsys)
    assert code == 0 and "A1" not in ran(report) and "skipped by your config: A1" in out
    assert cli.main(["disabled"]) == 0 and "A1   a1-flag" in capsys.readouterr().out
    assert cli.main(["enable", "a1-flag"]) == 0                    # by its name too
    assert "A1" in ran(migrate(tmp_path, save, capsys, name="again")[3])


def test_check_reads_your_packs_without_running_their_code(tmp_path, save, capsys, code_not_reachable):
    decl_pack(U.packs_dir() / "a", "edits", "A1")
    code_pack(U.packs_dir() / "b", "mycode")
    assert cli.main(["check", str(save)]) == 0
    out = capsys.readouterr().out
    rows = {ln.split()[0]: ln for ln in out.splitlines() if ln.startswith("  ")}
    assert "needed" in rows["A1"] and "unknown" in rows["C1"] and "unknown" in rows["C2"]


def test_trust_refuses_an_unknown_pack_and_keeps_the_other_settings(capsys):
    decl_pack(U.packs_dir() / "a", "edits", "A1")
    U.ensure_packs_dir()
    assert cli.main(["disable", "R21"]) == 0
    assert cli.main(["trust", "nope"]) == 1 and "no pack of yours has the id 'nope'" in capsys.readouterr().err
    assert cli.main(["trust", "edits"]) == 0 and "runs no code" in capsys.readouterr().out
    assert config.disabled_ids() == ["R21"] and set(config.trusted_packs()) == {"edits"}
    assert cli.main(["disable", "R20"]) == 0
    assert set(config.trusted_packs()) == {"edits"}                    # disable keeps the trust


# --------------------------------------------------------------------------- the hash
def test_the_hash_changes_with_any_edit_added_or_removed_file_but_not_pycache(tmp_path):
    folder = code_pack(tmp_path / "p")
    h0 = U.pack_hash(folder)
    (folder / "C1-script" / "__pycache__").mkdir()
    (folder / "C1-script" / "__pycache__" / "fix.cpython-313.pyc").write_bytes(b"x")
    assert U.pack_hash(folder) == h0
    (folder / "C1-script" / "fix.py").write_text("# edited\n", encoding="utf-8")
    h1 = U.pack_hash(folder)
    assert h1 != h0
    (folder / "extra.txt").write_text("", encoding="utf-8")
    h2 = U.pack_hash(folder)
    assert h2 != h1
    os.remove(folder / "extra.txt")
    assert U.pack_hash(folder) == h1
