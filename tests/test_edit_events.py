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
    """The files beside the save (a test's game folder lives there too, and is not one)."""
    return sorted(f.name for f in save.parent.iterdir() if f.is_file() and f.name != save.name)


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


ON_ACTION = (b"triggered_event={\n\ton_action=\"yearly_pulse\"\n\tscope={\n\t\troot={\n\t\t\ttype=char\n"
             b"\t\t\tidentity=10\n\t\t}\n\t\tseed=444\n\t}\n\tdate=987.10.28\n}\n")


def test_a_queued_on_action_is_read_and_named_as_one(tmp_path, capsys, monkeypatch):
    """Not every queued block is an event: some queue an on_action, named by on_action= (5,728 of play14's
    12,825). They are numbered and listed with the events, and say what they are."""
    g = DEFAULT_META + BODY + E1 + ON_ACTION + TAIL
    found = EV.queued_events(g)
    assert [(e.number, e.kind, e.event, e.label, e.seed) for e in found] == [
        (1, "event", "on_action.1", "on_action.1", 333), (2, "on_action", "yearly_pulse", "on_action yearly_pulse", 444)]
    monkeypatch.setattr(cli, "interactive", lambda: False)
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=BODY + E1 + ON_ACTION + TAIL))
    assert cli.main(["edit", str(p), "events", "10"]) == 0
    assert "on_action yearly_pulse" in capsys.readouterr().out
    assert cli.main(["edit", str(p), "event-remove", "2"]) == 0                  # removed like an event
    assert read_save(p.with_name("Camp__event-remove.ck3")).gamestate == DEFAULT_META + BODY + E1 + TAIL


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


# --------------------------------------------------------------------------- event-schedule (U17)
GAME_EVENTS = (b"namespace = child_personality\n\nchild_personality.4015 = {\n\ttype = character_event\n}\n\n"
               b"child_personality.40150 = {\n}\n")


@pytest.fixture
def game_dir(tmp_path, monkeypatch) -> Path:
    """A game folder whose events define child_personality.4015 (and .40150, a near miss), found by $CK3_GAME_DIR."""
    from tests.test_update import game
    g = game(tmp_path)
    (g / "events" / "childhood").mkdir(parents=True)
    (g / "events" / "childhood" / "child_personality_events.txt").write_bytes(GAME_EVENTS)
    monkeypatch.setenv("CK3_GAME_DIR", str(g))
    return g


def scheduled(save: Path) -> bytes:
    return read_save(save.with_name("Camp__event-schedule.ck3")).gamestate


def test_event_schedule_adds_one_block_before_the_first_later_event(save, game_dir):
    assert cli.main(["edit", str(save), "event-schedule", "Conchenn nic Bruide", "child_personality.4015",
                     "987.11.5"]) == 0
    seed = EV.scheduled_seed(None, 10, "child_personality.4015", (987, 11, 5))
    new = block("child_personality.4015", 10, seed, "987.11.5").replace(b"\t\t}\n\n\t\tseed", b"\t\t}\n\t\tseed") \
        .replace(b"\t}\n\n\tdate", b"\t}\n\tdate")                               # the compact layout, then the gap
    assert scheduled(save) == DEFAULT_META + BODY + new + E1 + E2 + E3 + TAIL   # E1 (988.1.1) is the first later one
    found = EV.queued_events(scheduled(save))
    assert [(e.number, e.event, e.date, e.root) for e in found][0] == (1, "child_personality.4015", "987.11.5", 10)
    assert len(found) == 4


def test_event_schedule_goes_last_when_nothing_is_later(save, game_dir):
    assert cli.main(["edit", str(save), "event-schedule", "10", "child_personality.4015", "990.1.1"]) == 0
    found = EV.queued_events(scheduled(save))
    assert [(e.event, e.date) for e in found][-1] == ("child_personality.4015", "990.1.1") and len(found) == 4
    assert scheduled(save).endswith(TAIL) and scheduled(save).startswith(DEFAULT_META + BODY + E1 + E2 + E3[:-1])


def test_event_schedule_is_repeatable_and_revertable(save, game_dir):
    assert cli.main(["edit", str(save), "event-schedule", "10", "child_personality.4015", "987.11.5"]) == 0
    first = scheduled(save)
    assert cli.main(["edit", str(save), "event-schedule", "10", "child_personality.4015", "987.11.5", "--force"]) == 0
    assert scheduled(save) == first                                              # the same seed, the same bytes
    out = save.with_name("Camp__event-schedule.ck3")
    assert cli.main(["edit", str(out), "revert"]) == 0
    assert read_save(out.with_name("Camp__event-schedule__revert.ck3")).gamestate == read_save(save).gamestate


@pytest.mark.parametrize("values, message", [
    (["10", "child_personality.9999", "987.11.5"], "no event child_personality.9999 in the game's events"),
    (["10", "child_personality.401", "987.11.5"], "no event child_personality.401 in the game's events"),
    (["10", "not an event", "987.11.5"], "an event is named namespace.number"),
    (["10", "child_personality.4015", "987.10.26"], "is before the save's date, 987.10.27"),
    (["10", "child_personality.4015", "987.13.5"], "the date is year.month.day"),
    (["10", "child_personality.4015", "soon"], "the date is year.month.day"),
    (["30", "child_personality.4015", "987.11.5"], "no living character has the id 30"),
])
def test_event_schedule_refusals(save, game_dir, capsys, values, message):
    assert cli.main(["edit", str(save), "event-schedule", *values]) == 1
    assert message in capsys.readouterr().err and others(save) == []


def test_without_the_game_the_event_cannot_be_checked_unless_dangerous(save, capsys):
    """conftest sets CK3_GAME_DIR=none: no game folder."""
    assert cli.main(["edit", str(save), "event-schedule", "10", "my_mod.1", "987.11.5"]) == 1
    assert "the game folder was not found" in capsys.readouterr().err and others(save) == []
    assert cli.main(["edit", str(save), "event-schedule", "10", "my_mod.1", "987.11.5", "--dangerous"]) == 0
    assert b'event="my_mod.1"' in scheduled(save)
    assert E.read_ledger(save.with_name("Camp__event-schedule.ck3"))["entries"][-1]["dangerous"] is True


def test_an_event_of_a_workshop_mod_the_save_lists_is_found(tmp_path, game_dir):
    from ck3_save_migrator.discover import workshop_content_dir
    mod = workshop_content_dir(game_dir) / "2507209632"                           # DEFAULT_META lists ugc_2507209632
    (mod / "events").mkdir(parents=True)
    (mod / "events" / "x.txt").write_bytes(b"namespace = my_mod\nmy_mod.1 = {\n}\n")
    assert EV.event_defined("my_mod.1", game_dir, [mod]) and EV.event_defined("my_mod.2", game_dir, [mod]) is None
    p = tmp_path / "Camp.ck3"
    p.write_bytes(build_ck3(body=EVENTS_BODY))
    assert cli.main(["edit", str(p), "event-schedule", "10", "my_mod.1", "987.11.5"]) == 0
