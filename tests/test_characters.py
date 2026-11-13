"""The character resolver (U8): an id, or a first name narrowed by a parent's first name, the house's name or a held
title; parents come from the parents' ``child={ }`` lists, the dead's included; several or no matches are refused
with what to do (finding 2026-11-09__01-52-22: 30 living Conchenns, 78307 the one whose father is Bruide)."""

from __future__ import annotations

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.characters import CharacterError, CharacterIndex, resolve_character
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3

BODY = (
    b"date=987.10.27\n"
    b"living={\n"
    b"10={\n\tfirst_name=\"Conchenn\"\n\tbirth=980.8.16\n\tfemale=yes\n\tdynasty_house=7\n}\n"
    b"11={\n\tfirst_name=\"Conchenn\"\n\tbirth=984.9.22\n\tdynasty_house=7\n}\n"
    b"12={\n\tfirst_name=\"Conchenn\"\n\tbirth=950.11.1\n\tdynasty_house=8\n}\n"
    b"20={\n\tfirst_name=\"Modron\"\n\tbirth=955.1.1\n\tdynasty_house=7\n"
    b"\tfamily_data={\n\t\tspouse=21\n\t\tchild={ 11 }\n\t}\n}\n"
    b"21={\n\tfirst_name=\"Nuala\"\n\tbirth=957.1.1\n\tfemale=yes\n"
    b"\tfamily_data={\n\t\tchild={ 10 11 }\n\t}\n}\n"
    b"}\n"
    b"dead_unprunable={\n"
    b"30={\n\tfirst_name=\"Bruide\"\n\tbirth=940.1.1\n\tdynasty_house=7\n"
    b"\tfamily_data={\n\t\tchild={ 10 }\n\t}\n}\n"
    b"}\n"
    b"dynasties={\n\tdynasty_house={\n"
    b"7={\n\tname=\"dynn_Ui_Neill\"\n}\n"
    b"8={\n\tkey=\"house_osraige\"\n}\n"
    b"\t}\n}\n"
    b"landed_titles={\n\tlanded_titles={\n"
    b"0={\n\tkey=c_tara\n\thistory={ 900.1.1={\n\t\t\tholder=11\n\t\t}\n}\n\tholder=12\n}\n"
    b"\t}\n}\n"
)


@pytest.fixture
def g() -> bytes:
    return DEFAULT_META + BODY


def test_an_id_is_first_class(g):
    c = resolve_character(g, "10")
    assert (c.id, c.first_name, c.female, c.age) == (10, "Conchenn", True, 7)
    assert resolve_character(g, "12").age == 36            # born 950.11.1: not yet 37 on 987.10.27


def test_parents_come_from_child_lists_the_deads_included(g):
    ix = CharacterIndex(g)
    assert (ix.character(10).father, ix.character(10).mother) == (30, 21)      # father dead, mother living
    assert (ix.character(11).father, ix.character(11).mother) == (20, 21)


def test_a_first_name_shared_is_refused_with_every_candidate(g):
    with pytest.raises(CharacterError) as exc:
        resolve_character(g, "Conchenn")
    text = str(exc.value)
    assert "matches 3 living characters" in text
    assert all(f"{i}  Conchenn" in text for i in (10, 11, 12))
    assert "father 30 Bruide" in text and "mother 21 Nuala" in text and "titles c_tara" in text


def test_a_parents_name_narrows_and_particles_are_ignored(g):
    assert resolve_character(g, "Conchenn nic Bruide").id == 10
    assert resolve_character(g, "conchenn mac modron").id == 11


def test_a_house_or_a_title_narrows(g):
    assert resolve_character(g, "Conchenn Osraige").id == 12
    assert resolve_character(g, "Conchenn tara").id == 12                       # the current holder, not history's
    with pytest.raises(CharacterError, match="matches 2"):
        resolve_character(g, "Conchenn Ui_Neill")


def test_no_match_is_refused(g):
    with pytest.raises(CharacterError, match="no living character answers"):
        resolve_character(g, "Conchenn Nobody")
    with pytest.raises(CharacterError, match="no living character has the id 30"):
        resolve_character(g, "30")                                            # dead: not editable


def test_the_editor_resolves_a_character_param(g, tmp_path, monkeypatch, capsys):
    def plan(gs: bytes, params: dict):
        c = CharacterIndex(gs).character(params["who"])
        return [E.Change(c.open + 1, b"\n", b"\n\tnickname=\"x\"\n")], f"character {c.id}"
    monkeypatch.setitem(E.BUILTIN, "nick", E.EditDef("nick", "nick", (("who", "character", ""),), plan))
    monkeypatch.setattr(cli, "interactive", lambda: False)
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY))
    assert cli.main(["edit", str(p), "nick", "Conchenn"]) == 1
    assert "matches 3 living characters" in capsys.readouterr().err
    assert cli.main(["edit", str(p), "nick", "Conchenn nic Bruide"]) == 0
    out = read_save(p.with_name("Camp__nick.ck3")).gamestate
    assert b'10={\n\tnickname="x"\n\tfirst_name="Conchenn"' in out


def test_a_number_param_must_be_whole():
    d = E.EditDef("n", "n", (("amount", "number", ""),))
    assert E.resolve_params(d, {"amount": "5000"}, b"")["amount"] == 5000
    with pytest.raises(E.EditError, match="whole number"):
        E.resolve_params(d, {"amount": "lots"}, b"")
