"""The save editor's front door (U2): ``ck3update edit <save> <edit> [values]`` plans, shows, asks at a terminal,
and writes ``<save stem>__<edit>.ck3`` beside the original; a dry run and a "no" write nothing; binary saves refused."""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import build_ck3


def toy_plan(ctx, params: dict):
    g = ctx.gamestate
    """Rename character 1: first_name="Beidh" -> the given name. One change, at the name's bytes."""
    m = re.search(rb'first_name="Beidh"', g)
    return [E.Change(m.start(), m.group(0), f'first_name="{params["name"]}"'.encode())], "character 1 (Beidh)"


@pytest.fixture
def toy(monkeypatch):
    monkeypatch.setitem(E.BUILTIN, "rename", E.EditDef("rename", "rename character 1", (("name", "text", ""),),
                                                       toy_plan))


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3())
    return p


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_the_edit_is_written_beside_the_original_and_changes_only_its_bytes(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)
    before = sha(save)
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    out = save.with_name("Camp__rename.ck3")
    assert out.exists() and sha(save) == before                       # the original is untouched
    g0, g1 = read_save(save).gamestate, read_save(out).gamestate
    assert g1 == g0.replace(b'first_name="Beidh"', b'first_name="Brigid"')


def test_a_dry_run_writes_nothing(toy, save, capsys):
    listing = sorted(save.parent.iterdir())
    assert cli.main(["edit", str(save), "rename", "Brigid", "--dry-run"]) == 0
    assert sorted(save.parent.iterdir()) == listing
    out = capsys.readouterr().out
    assert "dry run: nothing written" in out and "character 1 (Beidh)" in out and "Camp__rename.ck3" in out


def test_at_a_terminal_it_asks_and_a_no_writes_nothing(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: True)
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 1
    assert not save.with_name("Camp__rename.ck3").exists()


def test_at_a_terminal_a_yes_writes(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: True)
    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    assert save.with_name("Camp__rename.ck3").exists()


def test_yes_skips_the_question(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: True)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))                   # nothing to read: a question would say no
    assert cli.main(["edit", str(save), "rename", "Brigid", "--yes"]) == 0
    assert save.with_name("Camp__rename.ck3").exists()


def test_values_can_be_named(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)
    assert cli.main(["edit", str(save), "rename", "--name", "Aoife"]) == 0
    assert b'first_name="Aoife"' in read_save(save.with_name("Camp__rename.ck3")).gamestate


def test_an_unknown_edit_and_a_missing_value_are_refused(toy, save, capsys):
    assert cli.main(["edit", str(save), "nosuch"]) == 1
    assert "no edit named 'nosuch'" in capsys.readouterr().err
    assert cli.main(["edit", str(save), "rename"]) == 1
    assert "rename needs name" in capsys.readouterr().err


def test_an_existing_output_is_refused_without_force(toy, save, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    assert cli.main(["edit", str(save), "rename", "Aoife"]) != 0
    assert b'first_name="Brigid"' in read_save(save.with_name("Camp__rename.ck3")).gamestate
    assert cli.main(["edit", str(save), "rename", "Aoife", "--force"]) == 0


def test_a_binary_save_is_refused_with_the_reason(toy, tmp_path, capsys):
    p = tmp_path / "Iron.ck3"
    p.write_bytes(build_ck3(kind=1))
    assert cli.main(["edit", str(p), "rename", "Brigid"]) == 1
    assert "binary save" in capsys.readouterr().err
