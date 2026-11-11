"""``revert`` (U4): undo edits from the ledger, as an edit of its own -- a new file beside, a ledger entry, revertable;
refused when the save changed since its last edit. Compared by gamestate: a written save is re-deflated, so the
file's bytes can differ from the game's original compression while its content is exactly restored."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save, write_save
from tests.fixtures.make_ck3 import build_ck3


def name_plan(old: bytes):
    def plan(g: bytes, params: dict):
        m = re.search(rb'first_name="' + old + rb'"', g)
        return [E.Change(m.start(), m.group(0), f'first_name="{params["name"]}"'.encode())], old.decode()
    return plan


@pytest.fixture(autouse=True)
def toy(monkeypatch):
    monkeypatch.setitem(E.BUILTIN, "rename", E.EditDef("rename", "rename 1", (("name", "text", ""),),
                                                       name_plan(b"Beidh")))
    monkeypatch.setitem(E.BUILTIN, "rename2", E.EditDef("rename2", "rename 2", (("name", "text", ""),),
                                                        name_plan(b"Simin")))
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3())
    return p


def gs(p: Path) -> bytes:
    return read_save(p).gamestate


def ledger(p: Path) -> list:
    return json.loads(p.with_name(p.stem + ".edits.json").read_text(encoding="utf-8"))["entries"]


def test_revert_undoes_the_last_edit_into_a_new_file(save):
    assert cli.main(["edit", str(save), "rename", "Brigid-a-long-name"]) == 0
    edited = save.with_name("Camp__rename.ck3")
    assert cli.main(["edit", str(edited), "revert"]) == 0
    back = edited.with_name("Camp__rename__revert.ck3")
    assert gs(back) == gs(save) and edited.exists()                   # nothing renamed or deleted
    assert [e["edit"] for e in ledger(back)] == ["rename", "revert"]


def test_revert_undoes_an_edit_of_several_changes_of_different_lengths(save, monkeypatch):
    # the second change's place in the edited file moved by the first change's size difference: revert must use the
    # output offsets (red-green R2 survived without this test)
    def both(g, params):
        a = re.search(rb'first_name="Beidh"', g)
        b = re.search(rb'first_name="Simin"', g)
        return [E.Change(a.start(), a.group(0), b'first_name="Brigid-a-much-longer-name"'),
                E.Change(b.start(), b.group(0), b'first_name="S"')], "both"
    monkeypatch.setitem(E.BUILTIN, "both", E.EditDef("both", "rename both", (), both))
    assert cli.main(["edit", str(save), "both"]) == 0
    edited = save.with_name("Camp__both.ck3")
    assert cli.main(["edit", str(edited), "revert"]) == 0
    assert gs(edited.with_name("Camp__both__revert.ck3")) == gs(save)


def test_a_revert_can_itself_be_reverted(save):
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    edited = save.with_name("Camp__rename.ck3")
    assert cli.main(["edit", str(edited), "revert"]) == 0
    back = edited.with_name("Camp__rename__revert.ck3")
    assert cli.main(["edit", str(back), "revert", "-o", str(save.with_name("Again.ck3"))]) == 0
    assert gs(save.with_name("Again.ck3")) == gs(edited)


def test_revert_all_and_revert_to_an_entry(save):
    assert cli.main(["edit", str(save), "rename", "Brigid-long"]) == 0
    one = save.with_name("Camp__rename.ck3")
    assert cli.main(["edit", str(one), "rename2", "S"]) == 0
    two = one.with_name("Camp__rename__rename2.ck3")
    assert cli.main(["edit", str(two), "revert", "all", "-o", str(save.with_name("All.ck3"))]) == 0
    assert gs(save.with_name("All.ck3")) == gs(save)
    assert cli.main(["edit", str(two), "revert", "1", "-o", str(save.with_name("To1.ck3"))]) == 0
    assert gs(save.with_name("To1.ck3")) == gs(one)
    assert [e["edit"] for e in ledger(save.with_name("All.ck3"))] == ["rename", "rename2", "revert", "revert"]


def test_revert_is_refused_when_the_save_changed_since_its_last_edit(save, capsys):
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    edited = save.with_name("Camp__rename.ck3")
    s = read_save(edited)
    s.set_gamestate(s.gamestate.replace(b"date=987.10.27", b"date=988.1.1"))   # as if the game saved it
    other = save.with_name("Other.ck3")
    write_save(s, other)                              # write_save never writes over its own input
    edited.write_bytes(other.read_bytes())
    assert cli.main(["edit", str(edited), "revert"]) == 1
    assert "has changed since its last edit" in capsys.readouterr().err


def test_revert_without_a_ledger_is_refused(save, capsys):
    assert cli.main(["edit", str(save), "revert"]) == 1
    assert "has no ledger beside it" in capsys.readouterr().err


def test_a_bad_entry_number_is_refused(save, capsys):
    assert cli.main(["edit", str(save), "rename", "Brigid"]) == 0
    assert cli.main(["edit", str(save.with_name("Camp__rename.ck3")), "revert", "5"]) == 1
    assert "give an entry number from 0" in capsys.readouterr().err
