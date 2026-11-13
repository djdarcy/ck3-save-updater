"""``--in-place`` and the ``backup`` key (U5): edit and update replace the save under its own name; the original is kept
as ``<name>.bak.ck3`` unless ``--no-bak`` or ``backup = false`` (djdarcy 2026-11-08: on by default); the ledger follows
the edited file, and the backup keeps the original's."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests import test_update as TU
from tests.fixtures.make_ck3 import build_ck3
from tests.test_record import update
from tests.test_update import game, old_save

saves = TU.saves


def rename_plan(g: bytes, params: dict):
    m = re.search(rb'first_name="Beidh"', g)
    return [E.Change(m.start(), m.group(0), f'first_name="{params["name"]}"'.encode())], "character 1"


@pytest.fixture
def toy(monkeypatch, tmp_path):
    monkeypatch.setitem(E.BUILTIN, "rename", E.EditDef("rename", "rename", (("name", "text", ""),), rename_plan))
    monkeypatch.setattr(cli, "interactive", lambda: False)
    monkeypatch.setenv("CK3SM_CONFIG", str(tmp_path / "cfg" / "config.toml"))


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3())
    return p


def config(tmp_path: Path, text: str) -> None:
    (tmp_path / "cfg").mkdir(exist_ok=True)
    (tmp_path / "cfg" / "config.toml").write_text(text, encoding="utf-8")


def test_edit_in_place_keeps_a_backup_and_moves_the_ledger_to_the_save(toy, save):
    original = save.read_bytes()
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place"]) == 0
    assert b'first_name="Brigid"' in read_save(save).gamestate
    assert save.with_name("Camp.bak.ck3").read_bytes() == original
    led = json.loads(save.with_name("Camp.edits.json").read_text(encoding="utf-8"))
    assert led["save"] == "Camp.ck3" and led["entries"][-1]["sha256"] == E.hashlib.sha256(save.read_bytes()).hexdigest()
    assert not list(save.parent.glob("*ck3update-tmp*"))


def test_edit_in_place_no_bak_keeps_no_backup(toy, save, capsys):
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place", "--no-bak"]) == 0
    assert not save.with_name("Camp.bak.ck3").exists()
    assert "the original is gone" in capsys.readouterr().out


def test_the_config_key_turns_backups_off_and_bak_turns_one_on(toy, save, tmp_path):
    config(tmp_path, "backup = false\n")
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place"]) == 0
    assert not save.with_name("Camp.bak.ck3").exists()
    # a fresh save, the key off, --bak on: the backup is kept
    s2 = tmp_path / "Two.ck3"
    s2.write_bytes(build_ck3())
    assert cli.main(["edit", str(s2), "rename", "Aoife", "--in-place", "--bak"]) == 0
    assert s2.with_name("Two.bak.ck3").exists()


def test_an_existing_backup_is_refused_without_force(toy, save):
    save.with_name("Camp.bak.ck3").write_bytes(b"older")
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place"]) != 0
    assert save.with_name("Camp.bak.ck3").read_bytes() == b"older"
    assert b'first_name="Beidh"' in read_save(save).gamestate


def test_revert_after_an_in_place_edit_works_on_the_save(toy, save):
    original_gs = read_save(save).gamestate
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place"]) == 0
    assert cli.main(["edit", str(save), "revert"]) == 0
    assert read_save(save.with_name("Camp__revert.ck3")).gamestate == original_gs


def test_a_bad_backup_value_in_the_config_is_refused(toy, save, tmp_path, capsys):
    config(tmp_path, 'backup = "yes"\n')
    assert cli.main(["edit", str(save), "rename", "Brigid", "--in-place"]) != 0
    assert "'backup' must be true or false" in capsys.readouterr().err


def test_rewriting_the_config_keeps_the_backup_choice(toy, tmp_path):
    # `ck3update disable` rewrites the config file; the player's backup = false must survive it
    config(tmp_path, "disabled = []\nbackup = false\n")
    assert cli.main(["disable", "R21"]) == 0
    from ck3_save_migrator.config import backup_on
    assert backup_on() is False


def test_update_in_place_no_bak_keeps_no_backup(tmp_path, saves, capsys):
    g = game(tmp_path)
    b = old_save(saves, "B.ck3")
    code, said, err = update(capsys, b, g, "--in-place", "--no-record", "--no-bak")
    assert code == 0, err
    assert not (saves / "B.bak.ck3").exists() and "the original is gone" in said
