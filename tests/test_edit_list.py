"""``edit --list`` and ``help <edit>`` (U10): the door lists each edit with its id, name, pack and state, with or
without a save; ``help`` says what an edit takes and does, by name or by id; the ledger names the edit's pack."""

from __future__ import annotations

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from tests.fixtures.make_ck3 import build_ck3
from tests.test_characters import BODY


def rows(out: str) -> dict[str, list[str]]:
    """The listing's rows by edit name: [id, name, pack, state, title words...]."""
    return {ln.split()[1]: ln.split() for ln in out.splitlines() if ln.startswith("  ")}


def test_list_needs_no_save_and_says_set_sex_is_ready(capsys):
    assert cli.main(["edit", "--list"]) == 0
    out = capsys.readouterr().out
    r = rows(out)
    assert r["set-sex"][:4] == ["E1", "set-sex", "edits", "ready"]
    assert r["ironman-off"][:4] == ["E2", "ironman-off", "edits", "ready"]
    assert r["revert"][:4] == ["-", "revert", "builtin", "ready"]
    assert "make a living character male or female" in out and "ck3update help <name>" in out


def test_a_save_without_an_edit_lists_too_and_writes_nothing(tmp_path, capsys):
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    assert cli.main(["edit", str(p)]) == 0
    assert "set-sex" in rows(capsys.readouterr().out) and sorted(tmp_path.iterdir()) == [p]
    assert cli.main(["edit", str(p), "set-sex", "10", "male", "--list"]) == 0          # --list wins; nothing runs
    assert sorted(tmp_path.iterdir()) == [p]


@pytest.mark.parametrize("name", ["set-sex", "E1", "e1", "SET-SEX"])
def test_help_explains_an_edit_by_name_or_id(name, capsys):
    assert cli.main(["help", name]) == 0
    out = capsys.readouterr().out
    assert out.startswith("E1 set-sex: make a living character male or female")
    assert "usage     : ck3update edit <save> set-sex <who> <sex>" in out
    assert "value     : who (character) -- the character" in out and "value     : sex (text) -- male or female" in out
    assert "Only the character's own sex flag changes." in out


def test_help_explains_revert_and_still_refuses_an_unknown_name(capsys):
    assert cli.main(["help", "revert"]) == 0
    assert "usage     : ck3update edit <save> revert <to>" in capsys.readouterr().out
    assert cli.main(["help", "set-sx"]) == 1
    assert "did you mean: set-sex" in capsys.readouterr().err


def test_an_edit_runs_by_its_id_and_the_ledger_names_its_pack(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    assert cli.main(["edit", str(p), "E1", "10", "male"]) == 0
    out = p.with_name("Camp__set-sex.ck3")                                       # named after the edit, not the id
    assert E.read_ledger(out)["entries"][-1]["pack"] == "edits"
