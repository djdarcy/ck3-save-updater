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


def event_schedule(ctx, params: dict):
    """Queue an event for a living character on a date: one new block, placed before the first queued event with
    a later date. The event must be one the game defines (its own events, or those of the Workshop mods the save
    lists); the date may not be before the save's own."""
    from .events import EVENT_NAME, date_key, event_block, event_defined, scheduled_seed
    from .lint import workshop_mod_dirs
    who, name, date = int(params["who"]), str(params["event"]).strip(), str(params["date"]).strip()
    c = ctx.characters.character(who)
    if c is None:
        raise EditError(f"event-schedule: no living character has the id {who}")
    if not EVENT_NAME.fullmatch(name):
        raise EditError(f"event-schedule: an event is named namespace.number, such as child_personality.4000; "
                        f"not {name!r}")
    d = date_key(date)
    if not re.fullmatch(r"\d+\.\d+\.\d+", date) or not (1 <= d[1] <= 12 and 1 <= d[2] <= 31):
        raise EditError(f"event-schedule: the date is year.month.day, such as 987.11.5; not {date!r}")
    if ctx.date and d < ctx.date:
        raise EditError(f"event-schedule: {date} is before the save's date, {'.'.join(map(str, ctx.date))}")
    if not ctx.dangerous:
        if ctx.game_dir is None:
            raise EditError("event-schedule: the game folder was not found, so the event cannot be checked "
                            "(set CK3_GAME_DIR, or pass --dangerous to schedule it unchecked)")
        if event_defined(name, ctx.game_dir, workshop_mod_dirs(ctx.save.meta, ctx.game_dir)) is None:
            raise EditError(f"event-schedule: no event {name} in the game's events or in the Workshop mods the "
                            "save lists (--dangerous schedules it anyway, for an event of a mod kept elsewhere)")
    events, g = ctx.events, ctx.gamestate
    if not events:
        raise EditError("event-schedule: this save has no queued events to place a new one among")
    newline = b"\r\n" if b"\r\n" in g[events[0].start:events[0].end] else b"\n"
    block = event_block(name, who, scheduled_seed(ctx.seed, who, name, d), ".".join(map(str, d)), newline)
    gap = g[events[0].end:events[1].start] if len(events) > 1 else b""       # what the save puts between two blocks
    later = next((e for e in events if date_key(e.date) > d), None)
    change = Change(later.start, b"", block + gap) if later else Change(events[-1].end, b"", gap + block)
    what = f"queue {name} on {'.'.join(map(str, d))} for " + " ".join(ctx.characters.describe(c).split())
    return [change], what


# --------------------------------------------------------------------------- artifacts
def artifacts_view(ctx, params: dict) -> list[str]:
    """The artifacts a character holds: id, type and name, in the order of their inventory."""
    from .artifacts import artifacts, held_by
    who = int(params["who"])
    c = ctx.characters.character(who)
    if c is None:
        raise EditError(f"artifacts: no living character has the id {who}")
    known = artifacts(ctx.gamestate)
    held = held_by(ctx.gamestate, c.open, c.close)
    head = " ".join(ctx.characters.describe(c).split())
    if not held:
        return [head, "  holds no artifacts"]
    rows = []
    for i in held:
        a = known.get(i)
        rows.append(f"  {i:<10} {(a.type if a else '') or '-':<22} "
                    f"{a.name if a else '(not in the artifacts database)'}")
    return [head] + rows + [f"  {len(held)} artifacts, of the save's {len(known)}"]


def give_artifact(ctx, params: dict):
    """Give a character a copy of an artifact the save already holds: the entry copied under the next free id with
    the character as its owner, and that id added to the character's inventory (finding F17). The original and its
    owner are untouched."""
    from .artifacts import artifacts, copy_entry, inventory_list, next_id
    who, source = int(params["who"]), int(params["artifact"])
    c = ctx.characters.character(who)
    if c is None:
        raise EditError(f"give-artifact: no living character has the id {who}")
    g = ctx.gamestate
    known = artifacts(g)
    art = known.get(source)
    if art is None:
        raise EditError(f"give-artifact: the save has no artifact {source}; `ck3update edit <save> artifacts "
                        "<character>` lists a character's with their ids")
    span = inventory_list(g, c.open, c.close)
    if span is None:
        raise EditError(f"give-artifact: {c.id} {c.first_name} has no inventory in this save (they have never "
                        "held an artifact), and the tool cannot make one yet")
    new = next_id(known)
    newline = b"\r\n" if b"\r\n" in g[art.start:art.end] else b"\n"
    entry = Change(art.end, b"", newline + copy_entry(g, art, new, who))
    listed = Change(span[1], b"", str(new).encode() + b" ")
    what = (f'a copy of {source} "{art.name}"{f" ({art.type})" if art.type else ""} as {new} for '
            + " ".join(ctx.characters.describe(c).split()))
    return [entry, listed], what
