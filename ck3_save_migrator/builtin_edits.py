"""The code of the built-in edits (the shipped ``edits`` pack names these functions in its ``script =`` fields).

An edit's function plans and never writes: ``plan(gamestate, params) -> (changes, what)``. ``params`` holds the
edit's values as the engine resolved them (a ``character`` is the character's id, a ``number`` an int). ``changes``
is a list of :class:`~ck3_save_migrator.edit.Change`; an empty list means there is nothing to do, and ``what`` says
why. ``what`` is otherwise one line naming what the edit touches.

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U7, U9).
"""

from __future__ import annotations

import re

from .characters import index_for
from .edit import Change, EditError
from .savefile import meta_block_end

# --------------------------------------------------------------------------- set-sex
SEXES = {"male": False, "m": False, "female": True, "f": True}
_FEMALE_LINE = re.compile(rb"(?m)^\tfemale=yes\r?\n")
_AFTER = (re.compile(rb"(?m)^\tbirth=[^\n]*\n"), re.compile(rb"(?m)^\tfirst_name=[^\n]*\n"))


def set_sex(gamestate: bytes, params: dict):
    """A character's sex is one line of their entry: ``female=yes`` present or absent, at depth 1, where the game
    writes it (after ``birth``). Nothing else of theirs changes; the game recomputes heirs by itself (finding F13)."""
    sex = str(params["sex"]).strip().lower()
    if sex not in SEXES:
        raise EditError(f"set-sex: the sex is male or female, not {params['sex']!r}")
    female = SEXES[sex]
    ix = index_for(gamestate)
    c = ix.character(int(params["who"]))
    if c is None:
        raise EditError(f"set-sex: no living character has the id {params['who']}")
    if c.female == female:
        return [], f"{c.id} {c.first_name} is already {'female' if female else 'male'}"
    what = " ".join(ix.describe(c).split())
    body = gamestate[c.open:c.close]
    if not female:
        m = _FEMALE_LINE.search(body)
        return [Change(c.open + m.start(), m.group(0), b"")], what
    m = next((m for m in (rx.search(body) for rx in _AFTER) if m), None)
    at = c.open + (m.end() if m else body.index(b"\n") + 1)
    newline = b"\r\n" if gamestate[at - 2:at] == b"\r\n" else b"\n"
    return [Change(at, b"", b"\tfemale=yes" + newline)], what


# --------------------------------------------------------------------------- ironman-off
_IRONMAN_YES = re.compile(rb"(?m)^\tironman=(yes)\r?$")     # depth 1 of its block
_IRONMAN_MANAGER = re.compile(rb"(?m)^ironman_manager=\{\r?$")
_TOP_CLOSE = re.compile(rb"(?m)^\}")


def ironman_off(gamestate: bytes, params: dict):
    """``ironman=yes`` to ``no`` in the two places a text save keeps it: the ``meta_data`` block (whose plaintext
    copy before the zip is re-derived on write, so it follows) and the top-level ``ironman_manager`` block."""
    changes, where = [], []
    meta_end = meta_block_end(gamestate)
    m = _IRONMAN_YES.search(gamestate, 0, meta_end)
    if m:
        changes.append(Change(m.start(1), b"yes", b"no"))
        where.append("meta_data")
    mm = _IRONMAN_MANAGER.search(gamestate, meta_end)
    if mm:
        close = _TOP_CLOSE.search(gamestate, mm.end())
        m2 = _IRONMAN_YES.search(gamestate, mm.end(), close.start() if close else len(gamestate))
        if m2:
            changes.append(Change(m2.start(1), b"yes", b"no"))
            where.append("ironman_manager")
    what = "ironman=yes -> no in " + " and ".join(where) if where else "ironman is already off"
    return changes, what
