"""A player's own edits (U11): an edit in a pack of theirs is offered by ``ck3update edit`` beside the built-in ones,
and ``update`` never runs it. A declarative edit runs as it is; one that runs code needs its pack trusted. A pack's
``[applies] save`` span refuses a save outside it unless ``--dangerous``.

The safety test comes first. An untrusted code edit must not run, and the test makes running it impossible to
miss: the importer of a pack's code is replaced by a function that fails the test if called."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator import userpacks as U
from ck3_save_migrator.patches import pack as P
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import build_ck3
from tests.test_characters import BODY

# character 10 gains the 1.20 layout of gold (alive_data={ gold={ value=N } }); 11 has none
GOLD_BODY = BODY.replace(b'10={\n\tfirst_name="Conchenn"\n\tbirth=980.8.16\n\tfemale=yes\n\tdynasty_house=7\n}\n',
                         b'10={\n\tfirst_name="Conchenn"\n\tbirth=980.8.16\n\tfemale=yes\n\tdynasty_house=7\n'
                         b'\talive_data={\n\t\tgold={\n\t\t\tvalue=100\n\t\t}\n\t}\n}\n')
assert GOLD_BODY != BODY

SET_GOLD = """format = 2
id = "G1"
name = "set-gold"
title = "set a character's gold"
kind = "edit"
help = "Sets the gold a character holds."

[params.who]
type = "character"

[params.amount]
type = "number"

[[edit]]
path = "living/@@who@@/alive_data/gold"
op = "set"
key = "value"
value = "@@amount@@"
expect = 1
"""

FIX = """format = 2
id = "F1"
name = "a-fix"
title = "a fix"
since = "1.8"

[[edit]]
path = "meta_data"
op = "delete_key"
key = "no_such_key"
"""

CODE_EDIT = """format = 2
id = "K1"
name = "nick"
title = "give a nickname"
kind = "edit"
script = "nick.py:plan"

[params.who]
type = "character"
"""

NICK_PY = """from pathlib import Path
from ck3_save_migrator.characters import index_for
from ck3_save_migrator.edit import Change

Path(__file__).with_name("imported.txt").write_text("imported", encoding="utf-8")


def plan(gamestate, params):
    c = index_for(gamestate).character(params["who"])
    return [Change(c.open + 1, b"\\n", b'\\n\\tnickname="x"\\n')], f"character {c.id}"
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def gold_pack(applies: str = "", name: str = "set-gold") -> Path:
    """A pack of the player's holding a fix (F1) and a declarative edit (G1)."""
    folder = U.packs_dir() / "mine"
    write(folder / "pack.toml", 'format = 2\nid = "mine"\ntitle = "mine"\norder = ["F1", "G1"]\n' + applies)
    write(folder / "F1-fix" / "patch.toml", FIX)
    write(folder / "G1-gold" / "patch.toml", SET_GOLD.replace('name = "set-gold"', f'name = "{name}"'))
    return folder


def code_pack() -> Path:
    folder = U.packs_dir() / "mycode"
    write(folder / "pack.toml", 'format = 2\nid = "mycode"\ntitle = "code"\norder = ["K1"]\n')
    write(folder / "K1-nick" / "patch.toml", CODE_EDIT)
    write(folder / "K1-nick" / "nick.py", NICK_PY)
    return folder


def rows() -> dict[str, tuple]:
    return {r[1]: r for r in E.listing()}


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=GOLD_BODY))
    return p


def written(save: Path) -> list[str]:
    return sorted(f.name for f in save.parent.iterdir() if f.name != save.name)


# --------------------------------------------------------------------------- safety first
def test_an_untrusted_code_edit_never_runs(save, monkeypatch, capsys):
    folder = code_pack()
    real = P._function

    def forbidden(patch):                              # the shipped edits' own functions may load; a pack's may not
        if patch.from_disk:
            pytest.fail(f"an untrusted pack's code was loaded: {patch.source}")
        return real(patch)
    monkeypatch.setattr(P, "_function", forbidden)
    assert rows()["nick"][2:4] == ("mycode", "not trusted")
    assert cli.main(["edit", str(save), "nick", "10"]) == 1
    err = capsys.readouterr().err
    assert "is not trusted" in err and "ck3update trust mycode" in err
    assert cli.main(["help", "nick"]) == 0                                       # reading about it runs nothing
    assert written(save) == [] and not (folder / "K1-nick" / "imported.txt").exists()


def test_a_trusted_code_edit_runs_and_a_changed_pack_is_refused_again(save, capsys):
    folder = code_pack()
    assert cli.main(["trust", "mycode"]) == 0
    assert rows()["nick"][3] == "ready"
    assert cli.main(["edit", str(save), "nick", "Conchenn nic Bruide"]) == 0
    assert b'10={\n\tnickname="x"\n' in read_save(save.with_name("Camp__nick.ck3")).gamestate
    write(folder / "K1-nick" / "nick.py", NICK_PY + "\n# changed\n")
    assert rows()["nick"][3] == "changed since trusted"
    capsys.readouterr()
    assert cli.main(["edit", str(save), "nick", "10", "--force"]) == 1
    assert "changed since trusted" in capsys.readouterr().err


# --------------------------------------------------------------------------- a declarative edit
def test_a_declarative_edit_from_a_pack_runs_without_trust(save):
    gold_pack()
    assert rows()["set-gold"][:4] == ("G1", "set-gold", "mine", "ready")
    assert cli.main(["edit", str(save), "set-gold", "--who", "10", "--amount", "5000"]) == 0
    out = save.with_name("Camp__set-gold.ck3")
    assert read_save(out).gamestate == read_save(save).gamestate.replace(b"\t\t\tvalue=100\n", b"\t\t\tvalue=5000\n")
    entries = E.read_ledger(out)["entries"]
    assert len(entries) == 1 and len(entries[0]["changes"]) == 1                 # one entry with one offset
    assert (entries[0]["edit"], entries[0]["pack"], entries[0]["params"]) == ("set-gold", "mine",
                                                                              {"who": 10, "amount": 5000})


def test_the_plan_names_the_character_and_the_value(save, capsys):
    gold_pack()
    assert cli.main(["edit", str(save), "set-gold", "Conchenn nic Bruide", "5000", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "10 Conchenn (F, age 7" in out and "amount=5000" in out and written(save) == []


def test_refusals_of_a_declarative_edit(save, capsys):
    gold_pack()
    assert cli.main(["edit", str(save), "set-gold", "11", "5000"]) == 1          # 11 has no gold block
    assert "expected 1, found 0" in capsys.readouterr().err
    assert cli.main(["edit", str(save), "set-gold", "10", "100"]) == 1           # already 100
    err = capsys.readouterr().err
    assert "nothing to change" in err and "already so" in err
    assert cli.main(["edit", str(save), "set-gold", "10", "lots"]) == 1
    assert "whole number" in capsys.readouterr().err
    assert written(save) == []


def test_update_never_sees_the_edit_and_the_door_never_sees_the_fix(save):
    gold_pack()
    rules, _, _ = U.user_rules(U.find_user_packs(), allow_run=False)
    assert [r.id for r in rules] == ["F1"]
    assert "a-fix" not in rows() and E.lookup("F1") is None and E.lookup("a-fix") is None


# --------------------------------------------------------------------------- states
def test_a_turned_off_edit_is_listed_so_and_refused(save, capsys):
    gold_pack()
    assert cli.main(["disable", "G1"]) == 0
    assert rows()["set-gold"][3] == "turned off"
    capsys.readouterr()
    assert cli.main(["edit", str(save), "set-gold", "10", "5000"]) == 1
    assert "ck3update enable G1" in capsys.readouterr().err and written(save) == []


def test_a_pack_for_other_save_versions_is_refused_unless_dangerous(save, capsys):
    gold_pack('\n[applies]\nsave = ">=1.20"\n')                                  # the fixture save is 1.8.1
    assert rows()["set-gold"][3] == "ready"                                      # no save given: nothing to compare
    assert cli.main(["edit", str(save), "--list"]) == 0
    assert "outside this save's version" in capsys.readouterr().out
    assert cli.main(["edit", str(save), "set-gold", "10", "5000"]) == 1
    err = capsys.readouterr().err
    assert "is for saves >=1.20, and this save is 1.8.1" in err and "--dangerous" in err and written(save) == []
    assert cli.main(["edit", str(save), "set-gold", "10", "5000", "--dangerous"]) == 0
    assert "runs outside its version span" in capsys.readouterr().out
    entry = E.read_ledger(save.with_name("Camp__set-gold.ck3"))["entries"][-1]
    assert entry["dangerous"] is True and "saves >=1.20; this save is 1.8.1" in entry["dangerous_note"]


def test_a_span_that_covers_the_save_runs_plainly(save):
    gold_pack('\n[applies]\nsave = ">=1.8"\n')
    assert cli.main(["edit", str(save), "set-gold", "10", "5000"]) == 0
    assert "dangerous" not in E.read_ledger(save.with_name("Camp__set-gold.ck3"))["entries"][-1]


def test_a_built_in_name_cannot_be_taken(save, capsys):
    gold_pack(name="set-sex")
    mine = [r for r in E.listing() if r[2] == "mine"]
    assert [r[3] for r in mine] == ["name taken by a built-in edit"]
    assert cli.main(["edit", str(save), "set-sex", "10", "male"]) == 0           # the built-in one ran
    assert b"value=100" in read_save(save.with_name("Camp__set-sex.ck3")).gamestate
    capsys.readouterr()
    assert cli.main(["edit", str(save), "G1", "10", "5000"]) == 1
    assert "name taken by a built-in edit" in capsys.readouterr().err
