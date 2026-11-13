"""The ironman flag flip (U7; the front-door DWP 2026-11-06, addendum 2026-11-09 02:51): ``ironman-off`` sets
``ironman=no`` in a text save's ``meta_data`` block (and so in its plaintext copy) and in its ``ironman_manager``
block, and nothing else. The editor picks its reader by header kind, so a binary reader can plug in later; a binary
save is still refused."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import parse_save, read_save
from tests.fixtures.make_ck3 import DEFAULT_BODY, DEFAULT_META, build_ck3

MANAGER = (b"ironman_manager={\n\tironman=yes\n\tdate=987.10.27\n\tsave_game=\"Iron\"\n"
           b"\tsave_interval=three_months\n\tstorage=local\n}\n")
OTHER = b"some_block={\n\tironman=yes\n}\n"          # not a place the game keeps the flag: left as is

IRON_META = DEFAULT_META.replace(b"\tironman=no\n", b"\tironman=yes\n")


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


def save_with(tmp_path: Path, meta: bytes, body: bytes, name: str = "Iron.ck3") -> Path:
    p = tmp_path / name
    p.write_bytes(build_ck3(meta=meta, body=body))
    return p


def test_ironman_off_flips_meta_and_the_manager_and_nothing_else(tmp_path):
    p = save_with(tmp_path, IRON_META, DEFAULT_BODY + MANAGER + OTHER)
    assert cli.main(["edit", str(p), "ironman-off"]) == 0
    out = read_save(p.with_name("Iron__ironman-off.ck3"))
    g0 = read_save(p).gamestate
    assert b"\tironman=no\n" in out.meta and b"ironman=yes" not in out.meta      # the plaintext copy follows
    want = (IRON_META.replace(b"\tironman=yes", b"\tironman=no") + DEFAULT_BODY
            + MANAGER.replace(b"\tironman=yes", b"\tironman=no") + OTHER)
    assert g0 == IRON_META + DEFAULT_BODY + MANAGER + OTHER and out.gamestate == want


def test_crlf_line_endings_are_flipped_too(tmp_path):
    meta, body = IRON_META.replace(b"\n", b"\r\n"), (DEFAULT_BODY + MANAGER).replace(b"\n", b"\r\n")
    p = save_with(tmp_path, meta, body)
    changes, what = E.plan_ironman_off(read_save(p).gamestate, {})
    assert len(changes) == 2 and what == "ironman=yes -> no in meta_data and ironman_manager"


def test_a_save_with_ironman_off_is_left_alone(tmp_path, capsys):
    p = save_with(tmp_path, DEFAULT_META, DEFAULT_BODY + MANAGER.replace(b"=yes", b"=no", 1) + OTHER)
    assert cli.main(["edit", str(p), "ironman-off"]) == 1
    assert "ironman is already off" in capsys.readouterr().err
    assert not p.with_name("Iron__ironman-off.ck3").exists()


def test_the_flip_can_be_reverted(tmp_path):
    p = save_with(tmp_path, IRON_META, DEFAULT_BODY + MANAGER)
    assert cli.main(["edit", str(p), "ironman-off"]) == 0
    out = p.with_name("Iron__ironman-off.ck3")
    assert cli.main(["edit", str(out), "revert"]) == 0
    assert read_save(out.with_name("Iron__ironman-off__revert.ck3")).gamestate == read_save(p).gamestate


def test_a_binary_save_is_still_refused_with_its_kind(tmp_path, capsys):
    p = tmp_path / "Bin.ck3"
    p.write_bytes(build_ck3(kind=3))
    assert cli.main(["edit", str(p), "ironman-off"]) == 1
    err = capsys.readouterr().err
    assert "binary save" in err and "header kind 03" in err


def test_a_reader_registered_for_a_kind_is_used(tmp_path, monkeypatch):
    """The plug point a melter would use: a reader for kind 03 that returns a text save."""
    text = build_ck3(meta=IRON_META, body=DEFAULT_BODY + MANAGER)
    monkeypatch.setitem(E.READERS, 3, lambda path: parse_save(text, source=Path(path)))
    p = tmp_path / "Bin.ck3"
    p.write_bytes(build_ck3(kind=3))
    planned = E.plan_edit(p, "ironman-off", [])
    assert len(planned.changes) == 2


def test_ironman_off_is_listed():
    assert "ironman-off" in E.BUILTIN
