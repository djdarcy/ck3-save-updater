"""Queued events (U13-U15): the ``events`` and ``event-show`` views list and show a character's queued
``triggered_event`` blocks and write nothing; ``event-remove`` takes one block out; ``event-reroll`` gives one a new
seed derived from the old (finding F16). An event is named by its number in the save's order."""

from __future__ import annotations

from pathlib import Path

import pytest

from ck3_save_migrator import cli
from ck3_save_migrator import edit as E
from ck3_save_migrator import events as EV
from ck3_save_migrator.savefile import read_save
from tests.fixtures.make_ck3 import DEFAULT_META, build_ck3
from tests.test_characters import BODY


def block(event: str, root: int, seed: int, date: str, targets: bytes = b"") -> bytes:
    """One queued event in the game's own layout, with the blank line it leaves after it."""
    return (b"triggered_event={\n\tevent=\"" + event.encode() + b"\"\n\tscope={\n\t\troot={\n\t\t\ttype=char\n"
            b"\t\t\tidentity=" + str(root).encode() + b"\n\t\t}\n\n\t\tseed=" + str(seed).encode() + b"\n"
            + targets + b"\t}\n\n\tdate=" + date.encode() + b"\n}\n\n")


TARGETS = (b"\t\tevent_targets={\n\t\t\tnew_holder={\n\t\t\t\ttype=char\n\t\t\t\tidentity=10\n\t\t\t}\n\n"
           b"\t\t\ttitle={\n\t\t\t\ttype=lt\n\t\t\t\tidentity=0\n\t\t\t}\n\n\t\t}\n\n")
E1 = block("on_action.1", 11, 333, "988.1.1")
E2 = block("child_personality.4000", 10, 111, "987.11.2")
E3 = block("title_event.9900", 12, 222, "987.10.28", TARGETS)
TAIL = b"played_character={\n\tcharacter=10\n}\n"
EVENTS_BODY = BODY + E1 + E2 + E3 + TAIL


@pytest.fixture(autouse=True)
def no_terminal(monkeypatch):
    monkeypatch.setattr(cli, "interactive", lambda: False)


@pytest.fixture
def save(tmp_path) -> Path:
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=EVENTS_BODY))
    return p


def others(save: Path) -> list[str]:
    return sorted(f.name for f in save.parent.iterdir() if f.name != save.name)


# --------------------------------------------------------------------------- reading
def test_queued_events_are_read_in_the_saves_order():
    found = EV.queued_events(DEFAULT_META + EVENTS_BODY)
    assert [(e.number, e.event, e.date, e.root, e.seed) for e in found] == [
        (1, "on_action.1", "988.1.1", 11, 333), (2, "child_personality.4000", "987.11.2", 10, 111),
        (3, "title_event.9900", "987.10.28", 12, 222)]
    g = DEFAULT_META + EVENTS_BODY
    assert [g[e.start:e.end] for e in found] == [E1[:-1], E2[:-1], E3[:-1]]       # each block, without the blank line
    assert g[found[1].seed_at[0]:found[1].seed_at[1]] == b"111"
    assert found[2].targets == (("new_holder", 10),)                             # characters only: the title is not


def test_crlf_saves_are_read_too():
    g = (DEFAULT_META + EVENTS_BODY).replace(b"\n", b"\r\n")
    found = EV.queued_events(g)
    assert [e.seed for e in found] == [333, 111, 222]
    assert g[found[0].start:found[0].end] == E1[:-1].replace(b"\n", b"\r\n")


# --------------------------------------------------------------------------- the views
def test_events_lists_a_characters_own_and_the_ones_naming_her_soonest_first(save, capsys):
    assert cli.main(["edit", str(save), "events", "Conchenn nic Bruide"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("10 Conchenn (F, age 7")
    assert [ln.split()[:3] for ln in lines[1:3]] == [["#3", "987.10.28", "title_event.9900"],
                                                    ["#2", "987.11.2", "child_personality.4000"]]
    assert lines[1].rstrip().endswith("(as new_holder)") and lines[2].rstrip().endswith("(root)")
    assert "seed 111" in lines[2] and lines[3].strip() == "2 of the save's 3 queued events"
    assert others(save) == []                                                    # a view writes nothing


def test_events_says_when_there_are_none(save, capsys):
    assert cli.main(["edit", str(save), "events", "20"]) == 0
    assert "no queued events" in capsys.readouterr().out


def test_event_show_prints_the_block(save, capsys):
    assert cli.main(["edit", str(save), "event-show", "2"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("#2 child_personality.4000 on 987.11.2 for 10 Conchenn")
    assert 'event="child_personality.4000"' in out and "seed=111" in out and "on_action.1" not in out
    assert others(save) == []


# --------------------------------------------------------------------------- the edits
def test_event_remove_takes_out_exactly_that_block(save):
    assert cli.main(["edit", str(save), "event-remove", "2"]) == 0
    got = read_save(save.with_name("Camp__event-remove.ck3")).gamestate
    assert got == DEFAULT_META + BODY + E1 + E3 + TAIL
    entry = E.read_ledger(save.with_name("Camp__event-remove.ck3"))["entries"][-1]
    assert entry["params"] == {"number": 2} and "remove #2 child_personality.4000 on 987.11.2 for 10 Conchenn" in entry["what"]


def test_event_remove_can_be_reverted(save):
    assert cli.main(["edit", str(save), "event-remove", "3"]) == 0
    out = save.with_name("Camp__event-remove.ck3")
    assert cli.main(["edit", str(out), "revert"]) == 0
    assert read_save(out.with_name("Camp__event-remove__revert.ck3")).gamestate == read_save(save).gamestate


def test_event_reroll_changes_only_the_seed_and_is_repeatable(save, capsys):
    assert cli.main(["edit", str(save), "event-reroll", "2"]) == 0
    assert "seed 111 -> 13122" in capsys.readouterr().out                        # (111 * 7 + 12345) % 2**31
    out = save.with_name("Camp__event-reroll.ck3")
    assert read_save(out).gamestate == (DEFAULT_META + EVENTS_BODY).replace(b"seed=111\n", b"seed=13122\n")
    assert cli.main(["edit", str(out), "event-reroll", "2"]) == 0                # again: another seed
    again = read_save(out.with_name("Camp__event-reroll__event-reroll.ck3")).gamestate
    assert b"seed=104199\n" in again and b"seed=13122\n" not in again


def test_a_new_seed_stays_in_the_games_range():
    assert EV.new_seed(2 ** 31 - 1) == ((2 ** 31 - 1) * 7 + 12345) % 2 ** 31 < 2 ** 31
    assert EV.new_seed(0) == 12345


@pytest.mark.parametrize("name", ["event-show", "event-remove", "event-reroll"])
def test_a_number_the_save_does_not_have_is_refused(save, name, capsys):
    for number in ("0", "4"):
        assert cli.main(["edit", str(save), name, number]) == 1
        assert "this save has 3 queued events, numbered from 1" in capsys.readouterr().err
    assert others(save) == []


def test_the_event_edits_are_listed_with_their_roles(capsys):
    assert cli.main(["help", "events"]) == 0
    assert "a view (ck3update edit shows it; nothing is written)" in capsys.readouterr().out
    roles = {e.name: e.role for e in E.builtin().values()}
    assert (roles["events"], roles["event-show"], roles["event-remove"], roles["event-reroll"]) == \
        ("view", "view", "edit", "edit")
