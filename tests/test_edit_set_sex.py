"""set-sex (U9; finding F13): a living character's sex is ``female=yes`` present or absent at depth 1 of their entry.
The edit removes or adds that one line and nothing else; the character is named by id or by name pieces; a name
several answer to, a sex that is neither, and a character already of that sex are refused and nothing is written."""

from __future__ import annotations

import difflib
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.patches.model import load_pack
from ck3_save_migrator.patches.pack import shipped_pack_folder
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import build_ck3
from tests.test_characters import BODY


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    return p


def line_diff(a: bytes, b: bytes) -> list[str]:
    """The lines that differ, as '-old' / '+new'."""
    d = difflib.unified_diff(a.decode().splitlines(), b.decode().splitlines(), lineterm="", n=0)
    return [ln for ln in d if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]


def test_to_male_removes_exactly_the_female_line(save):
    assert cli.main(["edit", str(save), "set-sex", "10", "male"]) == 0
    g0, g1 = read_save(save).gamestate, read_save(save.with_name("Camp__set-sex.ck3")).gamestate
    assert line_diff(g0, g1) == ["-\tfemale=yes"]
    assert g1 == g0.replace(b'birth=980.8.16\n\tfemale=yes\n', b'birth=980.8.16\n', 1)      # hers, not Nuala's


def test_to_female_adds_the_line_after_birth(save):
    assert cli.main(["edit", str(save), "set-sex", "11", "female"]) == 0
    g0, g1 = read_save(save).gamestate, read_save(save.with_name("Camp__set-sex.ck3")).gamestate
    assert line_diff(g0, g1) == ["+\tfemale=yes"]
    assert b'11={\n\tfirst_name="Conchenn"\n\tbirth=984.9.22\n\tfemale=yes\n\tdynasty_house=7\n}' in g1


def test_there_and_back_gives_the_original_gamestate(save):
    assert cli.main(["edit", str(save), "set-sex", "10", "m"]) == 0
    male = save.with_name("Camp__set-sex.ck3")
    assert cli.main(["edit", str(male), "set-sex", "10", "f"]) == 0
    assert read_save(male.with_name("Camp__set-sex__set-sex.ck3")).gamestate == read_save(save).gamestate


def test_a_name_resolves_and_the_plan_names_the_character(save, capsys):
    assert cli.main(["edit", str(save), "set-sex", "Conchenn nic Bruide", "male", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "10 Conchenn (F, age 7, born 980.8.16)" in out and "father 30 Bruide" in out
    assert "dry run: nothing written" in out and not save.with_name("Camp__set-sex.ck3").exists()


def test_a_shared_name_is_refused_with_the_candidates(save, capsys):
    assert cli.main(["edit", str(save), "set-sex", "Conchenn", "male"]) == 1
    err = capsys.readouterr().err
    assert "matches 3 living characters" in err and not save.with_name("Camp__set-sex.ck3").exists()


def test_already_that_sex_is_refused(save, capsys):
    assert cli.main(["edit", str(save), "set-sex", "10", "female"]) == 1
    assert "10 Conchenn is already female" in capsys.readouterr().err
    assert cli.main(["edit", str(save), "set-sex", "11", "male"]) == 1
    assert "11 Conchenn is already male" in capsys.readouterr().err


def test_a_sex_that_is_neither_is_refused(save, capsys):
    assert cli.main(["edit", str(save), "set-sex", "10", "dragon"]) == 1
    assert "the sex is male or female, not 'dragon'" in capsys.readouterr().err


def test_crlf_saves_get_a_crlf_line(tmp_path):
    p = tmp_path / "Crlf.ck3"
    p.write_bytes(build_ck3(body=BODY.replace(b"\n", b"\r\n")))
    planned = E.plan_edit(p, "set-sex", ["11", "female"])
    assert [(c.before, c.after) for c in planned.changes] == [(b"", b"\tfemale=yes\r\n")]
    planned = E.plan_edit(p, "set-sex", ["10", "male"])
    assert [(c.before, c.after) for c in planned.changes] == [(b"\tfemale=yes\r\n", b"")]


def test_the_ledger_holds_the_resolved_id_and_a_revert_restores_her(save):
    assert cli.main(["edit", str(save), "set-sex", "Conchenn nic Bruide", "male"]) == 0
    out = save.with_name("Camp__set-sex.ck3")
    entry = E.read_ledger(out)["entries"][-1]
    assert entry["edit"] == "set-sex" and entry["params"] == {"who": 10, "sex": "male"}
    assert cli.main(["edit", str(out), "revert"]) == 0
    assert read_save(out.with_name("Camp__set-sex__revert.ck3")).gamestate == read_save(save).gamestate


def test_the_shipped_edits_pack_holds_only_edits_with_help():
    pack = load_pack(shipped_pack_folder("edits"), from_disk=False, context_fields=set())
    assert [p.name for p in pack.edits()][:2] == ["set-sex", "ironman-off"] and pack.ordered() == []
    assert all(p.help for p in pack.edits())
    assert {"set-sex", "ironman-off"} <= set(E.builtin())
    assert [n for n, _, _ in E.builtin()["set-sex"].params] == ["who", "sex"]
