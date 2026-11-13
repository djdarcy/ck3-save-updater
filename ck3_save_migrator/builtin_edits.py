"""The code of the built-in edits (the shipped ``edits`` pack names these functions in its ``script =`` fields).

An edit's function plans and never writes: ``plan(ctx, params) -> (changes, what)``. ``ctx`` is the door's
:class:`~ck3_save_migrator.edit.EditContext` (the gamestate, the save's date and version, the character index).
``params`` holds the edit's values as the door resolved them (a ``character`` is the character's id, a ``number``
an int). ``changes`` is a list of :class:`~ck3_save_migrator.edit.Change`; an empty list means there is nothing to
do, and ``what`` says why. ``what`` is otherwise one line naming what the edit touches.

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U7, U9).
"""

from __future__ import annotations

import re

from .edit import Change, EditError
from .savefile import meta_block_end

# --------------------------------------------------------------------------- set-sex
SEXES = {"male": False, "m": False, "female": True, "f": True}
_FEMALE_LINE = re.compile(rb"(?m)^\tfemale=yes\r?\n")
_AFTER = (re.compile(rb"(?m)^\tbirth=[^\n]*\n"), re.compile(rb"(?m)^\tfirst_name=[^\n]*\n"))


def set_sex(ctx, params: dict):
    """A character's sex is one line of their entry: ``female=yes`` present or absent, at depth 1, where the game
    writes it (after ``birth``). Nothing else of theirs changes; the game recomputes heirs by itself (finding F13)."""
    sex = str(params["sex"]).strip().lower()
    if sex not in SEXES:
        raise EditError(f"set-sex: the sex is male or female, not {params['sex']!r}")
    female = SEXES[sex]
    gamestate, ix = ctx.gamestate, ctx.characters
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


def ironman_off(ctx, params: dict):
    """``ironman=yes`` to ``no`` in the two places a text save keeps it: the ``meta_data`` block (whose plaintext
    copy before the zip is re-derived on write, so it follows) and the top-level ``ironman_manager`` block."""
    gamestate = ctx.gamestate
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


# --------------------------------------------------------------------------- queued events
def _event(ctx, number: int, name: str):
    """The queued event a player named by its number, or the refusal that says how to find one."""
    events = ctx.events
    if not 1 <= number <= len(events):
        raise EditError(f"{name}: this save has {len(events)} queued events, numbered from 1; "
                        "`ck3update edit <save> events <character>` lists a character's with their numbers")
    return events[number - 1]


def _about(ctx, e) -> str:
    """One line naming an event: its number, date, name, and whose it is."""
    who = ""
    if e.root_type == "char" and e.root is not None:
        who = f" for {e.root} {ctx.characters.first_names.get(e.root, '?')}"
    return f"#{e.number} {e.event} on {e.date or '?'}{who}"


def events_view(ctx, params: dict) -> list[str]:
    """The queued events about one character, soonest first, each with the number the other event edits take."""
    from .events import events_of
    who = int(params["who"])
    c = ctx.characters.character(who)
    found = events_of(ctx.gamestate, who)
    head = " ".join(ctx.characters.describe(c).split()) if c else str(who)
    if not found:
        return [head, "  no queued events"]
    return [head] + ["  " + e.line(role) for e, role in found] + \
           [f"  {len(found)} of the save's {len(ctx.events)} queued events"]


def event_show(ctx, params: dict) -> list[str]:
    """One queued event as the save holds it."""
    e = _event(ctx, int(params["number"]), "event-show")
    text = ctx.gamestate[e.start:e.end].decode("utf-8", "replace").expandtabs(4)
    return [_about(ctx, e)] + ["  " + ln for ln in text.splitlines()]


def event_remove(ctx, params: dict):
    """Take one queued event out of the save: its whole block, and the blank line the game leaves after it."""
    e = _event(ctx, int(params["number"]), "event-remove")
    g, end = ctx.gamestate, e.end
    for blank in (b"\r\n", b"\n"):
        if g[end:end + len(blank)] == blank:
            end += len(blank)
            break
    return [Change(e.start, g[e.start:end], b"")], "remove " + _about(ctx, e)


def event_reroll(ctx, params: dict):
    """Give one queued event a new seed, so it rolls again when it fires (finding F16). The new seed is derived
    from the old one: the same reroll of the same save gives the same seed, and a second reroll another."""
    from .events import new_seed
    e = _event(ctx, int(params["number"]), "event-reroll")
    if e.seed is None:
        return [], f"{_about(ctx, e)} has no seed"
    a, b = e.seed_at
    seed = new_seed(e.seed)
    return [Change(a, ctx.gamestate[a:b], str(seed).encode())], f"{_about(ctx, e)}: seed {e.seed} -> {seed}"
