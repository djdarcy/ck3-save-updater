"""Artifacts (U16; findings F14, F17, F21): the ``artifacts`` view lists what a character holds and writes nothing;
``give-artifact`` copies an artifact the save holds under the next free id (the slot after the highest, generation
0), with the receiver as its owner, and adds the id to the receiver's inventory. The original is untouched."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import artifacts as A
from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
from tests.test_characters import BODY


def inventory(owner: int, ids: bytes) -> bytes:
    return (b"\talive_data={\n\t\tinventory={\n\t\t\towner=" + str(owner).encode() + b"\n\t\t\tequipped={\n"
            b"\t\t\t\thelmet=1\n\t\t\t}\n\t\t\tartifacts={" + ids + b"}\n\t\t}\n\t}\n")


C11 = b'11={\n\tfirst_name="Conchenn"\n\tbirth=984.9.22\n\tdynasty_house=7\n'
C12 = b'12={\n\tfirst_name="Conchenn"\n\tbirth=950.11.1\n\tdynasty_house=8\n'
assert C11 + b"}\n" in BODY and C12 + b"}\n" in BODY
CROWN = (b'\t\t1={\n\t\t\tname="Crown"\n\t\t\ttype="helmet"\n\t\t\thistory={\n\t\t\t\tentries={ {\n'
         b"\t\t\t\t\t\ttype=created\n\t\t\t\t\t\tactor=12\n\t\t\t\t\t\towner=12\n\t\t\t\t\t}\n }\n\t\t\t}\n"
         b"\t\t\towner=12\n\t\t}")
LANTERN = b'\t\t16777218={\n\t\t\tname="Lantern"\n\t\t\towner=12\n\t\t}'       # generation 1, slot 2; no type
DB = b"artifacts={\n\tartifacts={\n" + CROWN + b"\n" + LANTERN + b"\n\t}\n}\n"
ART_BODY = (BODY.replace(C11 + b"}\n", C11 + inventory(11, b" ") + b"}\n")
            .replace(C12 + b"}\n", C12 + inventory(12, b" 1 16777218 ") + b"}\n")) + DB
G = DEFAULT_META + ART_BODY


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=ART_BODY))
    return p


def others(save: Path) -> list[str]:
    return sorted(f.name for f in save.parent.iterdir() if f.is_file() and f.name != save.name)


def test_the_artifacts_of_a_save_are_read_with_owner_name_and_type():
    arts = A.artifacts(G)
    assert {i: (a.name, a.type, a.owner) for i, a in arts.items()} == {1: ("Crown", "helmet", 12),
                                                                    16777218: ("Lantern", "", 12)}
    assert G[arts[1].start:arts[1].end] == CROWN and G[arts[16777218].start:arts[16777218].end] == LANTERN
    assert G[arts[1].owner_at[0]:arts[1].owner_at[1]] == b"12"
    assert G[arts[1].owner_at[0] - 9:arts[1].owner_at[0]] == b"\t\t\towner="       # the entry's own, not history's
    assert A.next_id(arts) == 3 and A.next_id({}) == 0                            # the slot after the highest


def test_the_view_lists_what_a_character_holds_and_writes_nothing(save, capsys):
    assert cli.main(["edit", str(save), "artifacts", "12"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("12 Conchenn (M, age 36")
    assert lines[1].split() == ["1", "helmet", "Crown"] and lines[2].split() == ["16777218", "-", "Lantern"]
    assert lines[3].strip() == "2 artifacts, of the save's 2"
    assert cli.main(["edit", str(save), "artifacts", "11"]) == 0
    assert "holds no artifacts" in capsys.readouterr().out and others(save) == []


def test_give_artifact_copies_the_entry_and_lists_it_for_the_receiver(save):
    assert cli.main(["edit", str(save), "give-artifact", "11", "1"]) == 0
    got = read_save(save.with_name("Camp__give-artifact.ck3")).gamestate
    copy = CROWN.replace(b"\t\t1={", b"\t\t3={", 1).replace(b"\n\t\t\towner=12\n\t\t}", b"\n\t\t\towner=11\n\t\t}")
    want = (DEFAULT_META + ART_BODY).replace(CROWN + b"\n", CROWN + b"\n" + copy + b"\n") \
        .replace(inventory(11, b" "), inventory(11, b" 3 "))
    assert got == want
    assert b"\t\t\t\t\t\towner=12\n" in copy                                      # history's own owner= is kept
    arts = A.artifacts(got)
    assert (arts[3].name, arts[3].owner) == ("Crown", 11) and arts[1].owner == 12  # the original is untouched
    c = E.EditContext(read_save(save.with_name("Camp__give-artifact.ck3"))).characters
    assert A.held_by(got, c.character(11).open, c.character(11).close) == [3]
    assert A.held_by(got, c.character(12).open, c.character(12).close) == [1, 16777218]


def test_a_second_copy_takes_the_next_id_and_a_revert_restores(save):
    assert cli.main(["edit", str(save), "give-artifact", "11", "1"]) == 0
    first = save.with_name("Camp__give-artifact.ck3")
    assert cli.main(["edit", str(first), "give-artifact", "12", "16777218"]) == 0
    second = first.with_name("Camp__give-artifact__give-artifact.ck3")
    arts = A.artifacts(read_save(second).gamestate)
    assert sorted(arts) == [1, 3, 4, 16777218] and (arts[4].name, arts[4].owner) == ("Lantern", 12)
    assert cli.main(["edit", str(second), "revert", "all"]) == 0
    back = second.with_name("Camp__give-artifact__give-artifact__revert.ck3")
    assert read_save(back).gamestate == read_save(save).gamestate


def test_refusals_write_nothing(save, capsys):
    assert cli.main(["edit", str(save), "give-artifact", "11", "99"]) == 1
    assert "the save has no artifact 99" in capsys.readouterr().err
    assert cli.main(["edit", str(save), "give-artifact", "10", "1"]) == 1          # 10 has no inventory block
    assert "has no inventory in this save" in capsys.readouterr().err
    assert cli.main(["edit", str(save), "give-artifact", "30", "1"]) == 1          # dead
    assert "no living character has the id 30" in capsys.readouterr().err
    assert others(save) == []


def test_crlf_saves_get_crlf_lines(tmp_path):
    p = tmp_path / "Crlf.ck3"
    p.write_bytes(build_ck3(body=ART_BODY.replace(b"\n", b"\r\n")))
    planned = E.plan_edit(p, "give-artifact", ["11", "1"])
    entry = max(planned.changes, key=lambda c: len(c.after)).after
    assert entry.startswith(b"\r\n\t\t3={\r\n") and b"\n" not in entry.replace(b"\r\n", b"")
