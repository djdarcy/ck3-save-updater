"""A pack folder runs no code of its own without --allow-run.

A script patch (``script = "<file>.py:<function>"``) runs Python from the pack folder, so it is gated like a run
patch: refused without ``allow_run``, and nothing of the pack is imported before that check. The
``<module>:<function>`` form is for the shipped pack only: from a folder it could import any module on ``sys.path``
(the current folder, under ``python -m``). A script file must sit inside its patch folder. Each test's script writes
a marker file when it is imported, so "nothing ran" is checked, not assumed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import PatchError, rules_from_pack
from ck3_save_migrator.rules import RuleContext
from tests.fixtures.make_ck3 import build_ck3

HEAD = 'format = 1\nid = "{id}"\nname = "n{id}"\ntitle = "t"\nsince = "1.20"\n'
FIX = """from pathlib import Path
Path({marker!r}).write_text("imported", encoding="utf-8")

def fix(save, ctx, rule):
    save.set_gamestate(save.gamestate.replace(b"\\tx=1\\n", b"\\tx=5\\n"))
    return rule.result(matched=1, edited=1)
"""


def pack_with(root: Path, patches: dict[str, str], files: dict[str, str] | None = None) -> Path:
    """``patches``: id -> the lines after the header; ``files``: path inside the pack -> text."""
    pack = root / "pack"
    for pid, body in patches.items():
        (pack / f"{pid}-x").mkdir(parents=True, exist_ok=True)
        (pack / f"{pid}-x" / "patch.toml").write_text(HEAD.format(id=pid) + body, encoding="utf-8")
    order = ", ".join(f'"{p}"' for p in patches)
    (pack / "pack.toml").write_text(f'format = 1\nid = "p"\ntitle = "p"\norder = [{order}]\n', encoding="utf-8")
    for rel, text in (files or {}).items():
        (pack / rel).parent.mkdir(parents=True, exist_ok=True)
        (pack / rel).write_text(text, encoding="utf-8")
    return pack


def script_pack(tmp_path: Path) -> tuple[Path, Path]:
    marker = tmp_path / "imported.txt"
    pack = pack_with(tmp_path, {"S1": 'script = "fix.py:fix"\n'}, {"S1-x/fix.py": FIX.format(marker=str(marker))})
    return pack, marker


def test_a_script_patch_from_a_folder_is_refused_without_allow_run_and_nothing_is_imported(tmp_path):
    pack, marker = script_pack(tmp_path)
    with pytest.raises(PatchError, match=r"S1-x/patch.toml: a script patch runs Python code .*--allow-run"):
        rules_from_pack(pack)
    assert not marker.exists()


def test_with_allow_run_the_script_is_imported_and_runs(tmp_path):
    pack, marker = script_pack(tmp_path)
    (rule,) = rules_from_pack(pack, allow_run=True)
    assert marker.read_text(encoding="utf-8") == "imported"
    save = sf.parse_save(build_ck3(meta=b"meta_data={\n\tversion=1\n}\n", body=b"s={\n\tx=1\n}\n"))
    assert rule.run(save, RuleContext()).edited == 1 and b"\tx=5\n" in save.gamestate


def test_the_whole_pack_is_checked_before_any_of_it_is_imported(tmp_path):
    marker = tmp_path / "imported.txt"
    pack = pack_with(tmp_path, {"S1": 'script = "fix.py:fix"\n', "Z1": '[run]\ncommand = ["x"]\n'},
                     {"S1-x/fix.py": FIX.format(marker=str(marker))})
    with pytest.raises(PatchError, match="--allow-run"):
        rules_from_pack(pack)
    assert not marker.exists()


def test_migrate_without_allow_run_refuses_a_script_pack_and_imports_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CK3_GAME_DIR", "none")
    monkeypatch.setenv("CK3_REFERENCE_SAVE", "none")
    pack, marker = script_pack(tmp_path)
    src = tmp_path / "My_Old_Campaign.ck3"
    src.write_bytes(build_ck3(meta=b'meta_data={\n\tsave_game_version=8\n\tversion="1.8.1"\n}\n',
                              body=b"s={\n\tx=1\n}\n"))
    args = ["migrate", str(src), "--rules", "R7", "--pack", str(pack), "--no-lint", "-o", str(tmp_path / "o.ck3")]
    assert cli.main(args) == 1
    assert "--allow-run" in capsys.readouterr().err and not marker.exists() and not (tmp_path / "o.ck3").exists()
    assert cli.main(args + ["--allow-run"]) == 0
    assert marker.exists() and b"\tx=5\n" in sf.read_save(tmp_path / "o.ck3").gamestate


def test_the_module_form_is_refused_from_a_folder_even_with_allow_run(tmp_path, monkeypatch):
    marker = tmp_path / "imported.txt"
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "planted_mod.py").write_text(FIX.format(marker=str(marker)), encoding="utf-8")
    monkeypatch.syspath_prepend(str(lib))                   # importable, as the current folder is under python -m
    pack = pack_with(tmp_path, {"S1": 'script = "planted_mod:fix"\n'})
    for allow in (False, True):
        with pytest.raises(PatchError, match=r"'<module>:<function>' is for the shipped pack"):
            rules_from_pack(pack, allow_run=allow)
    assert not marker.exists()


@pytest.mark.parametrize("script", ["../fix.py:fix", "sub/../../fix.py:fix", "/tmp/fix.py:fix"])
def test_a_script_path_that_leaves_the_patch_folder_is_refused(tmp_path, script):
    marker = tmp_path / "imported.txt"
    pack = pack_with(tmp_path, {"S1": f'script = "{script}"\n'}, {"fix.py": FIX.format(marker=str(marker))})
    with pytest.raises(PatchError, match="must be inside the patch folder"):
        rules_from_pack(pack, allow_run=True)
    assert not marker.exists()


def test_a_link_out_of_the_patch_folder_is_refused(tmp_path):
    marker = tmp_path / "imported.txt"
    outside = tmp_path / "outside.py"
    outside.write_text(FIX.format(marker=str(marker)), encoding="utf-8")
    pack = pack_with(tmp_path, {"S1": 'script = "fix.py:fix"\n'})
    try:
        os.symlink(outside, pack / "S1-x" / "fix.py")
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links cannot be made here")
    with pytest.raises(PatchError, match="outside the patch folder"):
        rules_from_pack(pack, allow_run=True)
    assert not marker.exists()


def test_a_script_with_a_dataclass_and_future_annotations_loads(tmp_path):
    text = ("from __future__ import annotations\nfrom dataclasses import dataclass\n\n@dataclass\nclass Seen:\n"
            "    n: int = 0\n\ndef fix(save, ctx, rule):\n    return rule.result(matched=Seen(3).n)\n")
    pack = pack_with(tmp_path, {"S1": 'script = "fix.py:fix"\n'}, {"S1-x/fix.py": text})
    (rule,) = rules_from_pack(pack, allow_run=True)
    save = sf.parse_save(build_ck3(meta=b"meta_data={\n}\n", body=b""))
    assert rule.run(save, RuleContext()).matched == 3


def test_a_script_that_fails_to_load_is_refused_naming_the_file(tmp_path):
    pack = pack_with(tmp_path, {"S1": 'script = "fix.py:fix"\n'}, {"S1-x/fix.py": "raise RuntimeError('broken')\n"})
    with pytest.raises(PatchError, match=r"S1-x/patch.toml: field 'script': fix.py failed to load "
                                         r"\(RuntimeError: broken\)"):
        rules_from_pack(pack, allow_run=True)
