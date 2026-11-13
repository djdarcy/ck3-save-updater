"""The events a save has queued: its top-level ``triggered_event={ ... }`` blocks.

Each block is one event the game will fire on a date::

    triggered_event={
    	event="child_personality.4000"
    	scope={
    		root={
    			type=char
    			identity=78307
    		}

    		seed=1985705388
    		event_targets={ ... }
    	}

    	date=987.11.2
    }

The seed decides what the event rolls when it fires (finding F16: a new seed changed the outcome for 7 of 22
children, against a 1% background), so an outcome is not stored before the event fires. The editor numbers the
blocks by their order in the save, from 1: a number names one event in one file, and changes when an earlier block
is removed.

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U13-U15).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_OPEN = re.compile(rb"(?m)^triggered_event=\{\r?\n")
_EVENT = re.compile(rb'(?m)^\tevent="?([^"\r\n]+)"?')
_DATE = re.compile(rb"(?m)^\tdate=([\d.]+)")
_SEED = re.compile(rb"(?m)^\t\tseed=(-?\d+)")
_ROOT = re.compile(rb"(?m)^\t\troot=\{\s*type=(\w+)\s*identity=(\d+)")
_TARGET = re.compile(rb"(?m)^\t\t\t(\w+)=\{\s*type=char\s*identity=(\d+)")
SEED_MODULUS = 2 ** 31


@dataclass(frozen=True)
class QueuedEvent:
    number: int                     # its place among the save's queued events, from 1
    start: int                      # the block, from "triggered_event={" to just past its closing "}" and newline
    end: int
    event: str                      # "namespace.number"
    date: str                       # when it fires, "Y.M.D" ("" when the block names none)
    root_type: str                  # "char" for an event about a character
    root: int | None                # the root's id
    seed: int | None
    seed_at: tuple[int, int] | None    # where the seed's digits are in the gamestate
    targets: tuple = ()             # ((name, character id), ...) from event_targets

    def line(self, role: str = "") -> str:
        seed = f"seed {self.seed}" if self.seed is not None else "no seed"
        return f"#{self.number:<6} {self.date or '?':<11} {self.event:<44} {seed}" + (f"  ({role})" if role else "")


def queued_events(g: bytes) -> list[QueuedEvent]:
    """Every queued event of the gamestate, in the save's order."""
    out = []
    for n, m in enumerate(_OPEN.finditer(g), 1):
        close = g.find(b"\n}", m.end() - 1)
        if close < 0:
            break
        end = close + 2
        end += 2 if g[end:end + 2] == b"\r\n" else 1 if g[end:end + 1] == b"\n" else 0
        blk = g[m.start():end]
        ev, date, seed, root = _EVENT.search(blk), _DATE.search(blk), _SEED.search(blk), _ROOT.search(blk)
        out.append(QueuedEvent(
            n, m.start(), end, ev.group(1).decode("utf-8", "replace") if ev else "?",
            date.group(1).decode() if date else "", root.group(1).decode() if root else "",
            int(root.group(2)) if root else None, int(seed.group(1)) if seed else None,
            (m.start() + seed.start(1), m.start() + seed.end(1)) if seed else None,
            tuple((t.group(1).decode(), int(t.group(2))) for t in _TARGET.finditer(blk))))
    return out


def event_numbered(g: bytes, number: int) -> QueuedEvent | None:
    events = queued_events(g)
    return events[number - 1] if 1 <= number <= len(events) else None


def date_key(date: str) -> tuple:
    return tuple(int(x) for x in date.split(".") if x.isdigit())


def events_of(g: bytes, character: int) -> list[tuple[QueuedEvent, str]]:
    """The queued events about a character, soonest first: ``(event, role)``, the role ``"root"`` when the event
    is the character's own, else the name it gives the character among its targets."""
    out = []
    for e in queued_events(g):
        if e.root_type == "char" and e.root == character:
            out.append((e, "root"))
        else:
            names = [name for name, cid in e.targets if cid == character]
            if names:
                out.append((e, "as " + ", ".join(names)))
    return sorted(out, key=lambda pair: (date_key(pair[0].date), pair[0].number))


EVENT_NAME = re.compile(r"[A-Za-z_]\w*\.\d+")


def event_defined(name: str, game_dir, mod_dirs=()) -> str | None:
    """The events file that defines ``name`` (``namespace.number = {`` at the start of a line), searched in the
    game's ``events`` folder and each mod folder's; None when no file does."""
    from pathlib import Path
    head = re.compile(rb"(?m)^" + re.escape(name.encode()) + rb"\s*=\s*\{")
    namespace = name.split(".", 1)[0].encode()
    for base in [Path(game_dir)] + [Path(m) for m in mod_dirs]:
        folder = base / "events"
        if not folder.is_dir():
            continue
        for f in sorted(folder.rglob("*.txt")):
            data = f.read_bytes()
            if namespace in data and head.search(data):
                return str(f)
    return None


def scheduled_seed(campaign_seed: str | None, character: int, name: str, date: tuple) -> int:
    """The seed a scheduled event gets: fixed by the campaign, the character, the event and the date, so the same
    edit of the same save writes the same bytes."""
    import zlib
    base = int(campaign_seed) if campaign_seed and campaign_seed.isdigit() else 0
    return (base * 31 + character * 7 + date[0] * 372 + date[1] * 31 + date[2] + zlib.crc32(name.encode())) \
        % SEED_MODULUS


def event_block(name: str, character: int, seed: int, date: str, newline: bytes = b"\n") -> bytes:
    """A queued event about a character, in the layout the game writes: the event, its root, a seed, the date."""
    text = (f'triggered_event={{\n\tevent="{name}"\n\tscope={{\n\t\troot={{\n\t\t\ttype=char\n'
            f"\t\t\tidentity={character}\n\t\t}}\n\t\tseed={seed}\n\t}}\n\tdate={date}\n}}\n")
    return text.encode().replace(b"\n", newline)


def new_seed(seed: int) -> int:
    """A different seed derived from the old one, so a reroll is repeatable and a second reroll differs again (the
    derivation F16's measurement used)."""
    return (seed * 7 + 12345) % SEED_MODULUS
