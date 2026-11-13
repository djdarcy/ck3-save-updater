"""The door reshaped (U12b, after the refactor-advisor's table of 2026-11-13): three defects it found, each with the
test that fails before its fix, then the new shapes: an edit's function takes a context, a view shows and writes
nothing, and built-in and player edits load through one loader.

Defects: the ledger's input hash was taken from the file at write time, not from the save as read; a pack for one
save game (``[applies] campaign``) was offered on every save; a failed in-place swap left the save without its
ledger."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator import userpacks as U
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
from tests.test_characters import BODY
from tests.test_edit_player_packs import GOLD_BODY, SET_GOLD, write

SEED_BODY = b"random_seed=4942029\n" + GOLD_BODY


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=SEED_BODY))
    return p


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gold_pack(applies: str = "") -> None:
    folder = U.packs_dir() / "mine"
    write(folder / "pack.toml", 'format = 2\nid = "mine"\ntitle = "mine"\norder = ["G1"]\n' + applies)
    write(folder / "G1-gold" / "patch.toml", SET_GOLD)


# --------------------------------------------------------------------------- the three defects
def test_the_ledger_records_the_hash_of_the_save_as_read(save):
    """The game may save over the file while the player is at the question: the changes were planned on the bytes
    read, so that is the input the ledger names."""
    before = save.read_bytes()
    planned = E.plan_edit(save, "set-sex", ["10", "male"])
    save.write_bytes(build_ck3(body=SEED_BODY + b"later=yes\n"))               # the game saved meanwhile
    E.write_planned(planned)
    entry = E.read_ledger(save.with_name("Camp__set-sex.ck3"))["entries"][-1]
    assert entry["input_sha256"] == sha(before)


def test_in_place_is_refused_when_the_save_changed_since_it_was_read(save, monkeypatch, capsys):
    real = E.plan_edit

    def plan_then_the_game_saves(*a, **kw):
        p = real(*a, **kw)
        save.write_bytes(build_ck3(body=SEED_BODY + b"later=yes\n"))
        return p
    monkeypatch.setattr(E, "plan_edit", plan_then_the_game_saves)
    newer = build_ck3(body=SEED_BODY + b"later=yes\n")
    assert cli.main(["edit", str(save), "set-sex", "10", "male", "--in-place"]) == 1
    assert "changed since it was read" in capsys.readouterr().err
    assert save.read_bytes() == newer and not save.with_name("Camp.bak.ck3").exists()   # the newer save is kept


def test_a_pack_for_another_save_game_is_refused(save, capsys):
    gold_pack('\n[applies]\ncampaign = { name = "Other", seed = 111 }\n')
    assert cli.main(["edit", str(save), "set-gold", "10", "5000"]) == 1
    err = capsys.readouterr().err
    assert "Other" in err and "--dangerous" in err and not save.with_name("Camp__set-gold.ck3").exists()
    assert cli.main(["edit", str(save), "--list"]) == 0
    assert "for another save game" in capsys.readouterr().out
    assert cli.main(["edit", str(save), "set-gold", "10", "5000", "--dangerous"]) == 0


def test_a_pack_for_this_save_game_runs(save):
    gold_pack('\n[applies]\ncampaign = { name = "Mine", seed = 4942029 }\n')
    assert cli.main(["edit", str(save), "set-gold", "10", "5000"]) == 0
    assert "dangerous" not in E.read_ledger(save.with_name("Camp__set-gold.ck3"))["entries"][-1]


def test_a_failed_in_place_swap_leaves_the_save_its_ledger(save, monkeypatch):
    assert cli.main(["edit", str(save), "set-sex", "10", "male", "--in-place"]) == 0     # now Camp has a ledger
    ledger = E.ledger_path(save)
    first = ledger.read_bytes()
    edited = save.read_bytes()
    save.with_name("Camp.bak.ck3").unlink()
    E.ledger_path(save.with_name("Camp.bak.ck3")).unlink(missing_ok=True)
    monkeypatch.setattr(cli, "swap_in_place", lambda *a, **kw: 1)                        # the swap fails
    assert cli.main(["edit", str(save), "set-sex", "11", "female", "--in-place"]) == 1
    assert save.read_bytes() == edited and ledger.is_file() and ledger.read_bytes() == first
    assert E.plan_revert(save, []).what.startswith("undo 1 set-sex")                     # revert still works


# --------------------------------------------------------------------------- the new shapes
VIEW = """format = 2
id = "V1"
name = "who-is"
title = "show one character"
kind = "view"
script = "view.py:show"

[params.who]
type = "character"
"""

VIEW_PY = """def show(ctx, params):
    c = ctx.characters.character(params["who"])
    return [f"{c.id} {c.first_name}", f"save {ctx.version} on {ctx.date}, seed {ctx.seed}, file {ctx.path.name}",
            f"input {ctx.input_sha256}"]
"""


def view_pack() -> None:
    folder = U.packs_dir() / "views"
    write(folder / "pack.toml", 'format = 2\nid = "views"\ntitle = "views"\norder = ["V1"]\n')
    write(folder / "V1-who" / "patch.toml", VIEW)
    write(folder / "V1-who" / "view.py", VIEW_PY)
    assert cli.main(["trust", "views"]) == 0


def test_a_view_shows_and_writes_nothing(save, capsys):
    view_pack()
    before = sorted(save.parent.iterdir())
    capsys.readouterr()
    assert cli.main(["edit", str(save), "who-is", "Conchenn nic Bruide"]) == 0
    out = capsys.readouterr().out
    assert "10 Conchenn" in out
    assert sorted(save.parent.iterdir()) == before                               # no output, no ledger
    assert cli.main(["help", "who-is"]) == 0
    assert "a view (ck3update edit shows it; nothing is written)" in capsys.readouterr().out


def test_the_context_gives_the_save_as_read(save, capsys):
    view_pack()
    capsys.readouterr()
    assert cli.main(["edit", str(save), "who-is", "10"]) == 0
    out = capsys.readouterr().out
    assert "save 1.8.1 on (987, 10, 27), seed 4942029, file Camp.ck3" in out
    assert f"input {sha(save.read_bytes())}" in out


def test_a_view_is_not_planned_as_an_edit_and_must_be_code(save, tmp_path):
    view_pack()
    with pytest.raises(E.EditError, match="is a view"):
        E.plan_edit(save, "who-is", ["10"])
    with pytest.raises(E.EditError, match="is an edit, not a view"):
        E.run_view(save, "set-sex", ["10", "male"])
    from ck3_save_migrator.patches import PatchError, load_patch
    d = tmp_path / "bad" / "V2-x"
    write(d / "patch.toml", SET_GOLD.replace('kind = "edit"', 'kind = "view"'))
    with pytest.raises(PatchError, match="a view is code"):
        load_patch(d, from_disk=True, context_fields=set())


def test_one_loader_serves_built_in_and_player_packs(save):
    """A declarative edit is offered from any pack the loader is given, the shipped one included."""
    gold_pack()
    pack = U.find_user_packs().packs[0].pack
    (e,) = E.edits_from_pack(pack)
    assert (e.name, e.role, e.state, e.pack) == ("set-gold", "edit", "ready", "mine")
    changes, what = e.plan(E.open_context(save), {"who": 10, "amount": 7})
    assert [(c.before, c.after) for c in changes] == [(b"100", b"7")]
    assert all(x.role == "edit" and x.state == "ready" for x in E.builtin().values())


def test_listing_with_a_save_does_not_read_the_whole_save(save, monkeypatch, capsys):
    gold_pack('\n[applies]\nsave = ">=1.20"\n')

    def forbidden(path):
        pytest.fail("the whole save was read for a listing")
    monkeypatch.setattr(E, "open_context", forbidden)
    assert cli.main(["edit", str(save), "--list"]) == 0
    assert "outside this save's version" in capsys.readouterr().out


def test_an_unknown_name_lists_the_players_edits_too(save, capsys):
    gold_pack()
    assert cli.main(["edit", str(save), "set-glod", "10", "5"]) == 1
    err = capsys.readouterr().err
    assert "set-gold" in err and "set-sex" in err


def test_a_span_is_not_held_against_an_edit_when_the_version_is_unknown():
    e = E.EditDef("x", "x", applies={"save": ">=1.20"})
    assert E.outside(e, None, None) is None
    assert E.outside(e, "1.8.1", None)[0] == "outside this save's version"
    assert E.outside(e, "1.20.1", None) is None
