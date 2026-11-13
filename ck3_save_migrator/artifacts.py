"""The artifacts a save holds, and who holds them.

An artifact is an entry of the ``artifacts={ artifacts={ ... } }`` database, keyed by its id, with an ``owner=``::

    artifacts={
    	artifacts={
    		21={
    			name="Pugyel Dynasty Banner"
    			type="wall_big"
    			...
    			owner=33569272
    		}

and its id stands in the owner's inventory, inside the owner's character entry::

    		inventory={
    			owner=33569272
    			equipped={ ... }
    			artifacts={ 20 21 72 }
    		}

An id is ``(generation << 24) | slot`` (finding F14). A copied artifact under the next free slot at generation 0,
with its id added to the owner's inventory list, loads and survives the game's own re-save (finding F17).

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U16).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import gamestate as gs

SLOT_MASK = 0xFFFFFF
_ENTRY = re.compile(rb"(?m)^\t\t(\d+)=\{")
_OWNER = re.compile(rb"(?m)^\t\t\towner=(\d+)")
_NAME = re.compile(rb'(?m)^\t\t\tname="([^"\r\n]*)"')
_TYPE = re.compile(rb'(?m)^\t\t\ttype="?([^"\r\n]*)"?')
_INVENTORY = re.compile(rb"(?m)^\t\tinventory=\{")
_LIST = re.compile(rb"(?m)^\t\t\tartifacts=\{([^}]*)\}")


@dataclass(frozen=True)
class Artifact:
    id: int
    start: int                      # the entry, from its id's first digit's line start to just past its closing "}"
    end: int
    name: str
    type: str                       # "" when the entry names none (770 of play14's 4,702 do not)
    owner: int | None
    owner_at: tuple[int, int] | None    # where the owner's digits are in the gamestate


def artifacts(g: bytes) -> dict[int, Artifact]:
    """Every artifact of the save, by id. Empty when the save has no artifacts database."""
    try:
        db = gs.locate(g, "artifacts/artifacts")
    except gs.GamestateError:
        return {}
    out = {}
    heads = list(_ENTRY.finditer(g, db.open, db.close))
    for m in heads:
        close = g.find(b"\n\t\t}", m.end(), db.close)
        if close < 0:
            continue
        end = close + len(b"\n\t\t}")
        body = g[m.start():end]
        owner, name, kind = _OWNER.search(body), _NAME.search(body), _TYPE.search(body)
        out[int(m.group(1))] = Artifact(
            int(m.group(1)), m.start(), end, name.group(1).decode("utf-8", "replace") if name else "?",
            kind.group(1).decode("utf-8", "replace") if kind else "", int(owner.group(1)) if owner else None,
            (m.start() + owner.start(1), m.start() + owner.end(1)) if owner else None)
    return out


def next_id(ids) -> int:
    """The id a new artifact takes: the slot after the highest in use, at generation 0 (F14, F17)."""
    return max((i & SLOT_MASK for i in ids), default=-1) + 1


def inventory_list(g: bytes, open_: int, close: int) -> tuple[int, int] | None:
    """Where the ids of a character's inventory list are (the text between ``artifacts={`` and ``}``), given the
    character entry's braces; None when the character has no inventory block."""
    inv = _INVENTORY.search(g, open_, close)
    if not inv:
        return None
    lst = _LIST.search(g, inv.end(), close)
    return (lst.start(1), lst.end(1)) if lst else None


def held_by(g: bytes, open_: int, close: int) -> list[int]:
    """The ids in a character's inventory list, in the save's order."""
    span = inventory_list(g, open_, close)
    return [int(x) for x in g[span[0]:span[1]].split() if x.isdigit()] if span else []


def copy_entry(g: bytes, art: Artifact, new: int, owner: int) -> bytes:
    """The artifact's entry under a new id and owner, otherwise byte for byte."""
    body = g[art.start:art.end]
    head = _ENTRY.match(body)
    body = body[:head.start(1)] + str(new).encode() + body[head.end(1):]
    m = _OWNER.search(body)
    if m:
        body = body[:m.start(1)] + str(owner).encode() + body[m.end(1):]
    return body
