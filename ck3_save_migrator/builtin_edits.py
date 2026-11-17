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
    return f"#{e.number} {e.label} on {e.date or '?'}{who}"


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


# --------------------------------------------------------------------------- acknowledge-child
# The state the game itself writes for "the husband's son in law, another man's in blood" (1,351 characters in the
# founding campaign): the legal father lists the child, the child's own `real_father=` names the real one, and the
# child carries no bastard-family trait. Design: 2026-11-15__04-13-46__dev-workflow-process__acknowledge-child-*.md
BASTARD_TRAITS = ("bastard", "wild_oat", "legitimized_bastard", "disputed_heritage")   # remove_all_bastard_traits
PARENTAGE_SECRETS = ("secret_unmarried_illegitimate_child", "secret_disputed_heritage")
PASTS = ("honest", "clean")
_FAMILY = re.compile(rb"(?m)^\tfamily_data=\{\r?\n")
_FAMILY_END = re.compile(rb"(?m)^\t\}")
_CHILDREN = re.compile(rb"(?m)^\t\tchild=\{([^}\n]*)\}")          # these lists sit on one line in a save
_SPOUSES = re.compile(rb"(?m)^\t\t(?:primary_spouse|spouse)=(\d+)|^\t\tformer_spouses=\{([^}\n]*)\}")
_TRAITS = re.compile(rb"(?m)^\ttraits=\{([^}\n]*)\}")
_BIRTH = re.compile(rb"(?m)^\tbirth=([\d.]+)")
_ID_LIST = re.compile(rb"(?m)^\t+(?:secrets|targeting_secrets)=\{([^}\n]*)\}")


def _entry_of(ix, cid: int):
    return ix.living.get(cid) or ix.dead.get(cid)


def _family(g: bytes, e):
    """The span of a character's family_data block body, or None."""
    m = _FAMILY.search(g, e.open, e.close)
    if not m:
        return None
    end = _FAMILY_END.search(g, m.end(), e.close)
    return (m.end(), end.start()) if end else None


def _list_text(ids) -> bytes:
    return b"{ " + b" ".join(str(i).encode() for i in ids) + b" }" if ids else b"{ }"


def _birth_key(g: bytes, e) -> tuple:
    m = _BIRTH.search(g, e.open, e.close) if e else None
    return tuple(int(x) for x in m.group(1).split(b".")) if m else (99999,)


def _parentage_secrets(g: bytes, child: int) -> list:
    """(id, entry, type) of each parentage secret whose target is the child."""
    from . import gamestate as gs
    try:
        db = gs.locate(g, "secrets/secrets")
    except gs.GamestateError:
        return []
    out = []
    target = re.compile(rb"target=\{\s*type=char\s*identity=" + str(child).encode() + rb"\s")
    for e in gs.iter_entries(g, *db.body):
        body = g[e.open:e.close]
        t = re.search(rb'(?m)^\t+type="(secret_[a-z_]+)"', body)
        if t and t.group(1).decode() in PARENTAGE_SECRETS and target.search(body):
            out.append((e.key.decode(), e, t.group(1).decode(), e.open + t.start(1), e.open + t.end(1)))
    return out


def _remove_secret(g: bytes, sid: str, entry) -> list:
    """The changes that take one secret out of the save: its entry, the knowledge records of who knows it, and its
    id in every character's `secrets={ }` or `targeting_secrets={ }` list. Any other mention of the id is refused,
    since removing the entry would leave it pointing at nothing."""
    from . import gamestate as gs
    s, e = gs.removal_span(g, entry.start, entry.end)
    changes, covered = [Change(s, g[s:e], b"")], [(entry.start, entry.end)]
    try:
        known = gs.locate(g, "secrets/known_secrets")
        rx = re.compile(rb"(?m)^\t+secret=" + sid.encode() + rb"\r?$")
        for c in gs.iter_children(g, known.open + 1, known.close):
            if c.block is not None and rx.search(g, c.block.open, c.block.close):
                a, b = gs.removal_span(g, c.start, c.block.end)
                changes.append(Change(a, g[a:b], b""))
                covered.append((c.start, c.block.end))
    except gs.GamestateError:
        pass
    for m in re.finditer(rb"(?<![\w.])" + sid.encode() + rb"(?![\w.])", g):
        p = m.start()
        if any(a <= p < b for a, b in covered):
            continue
        line_start = g.rfind(b"\n", 0, p) + 1
        lm = _ID_LIST.match(g, line_start)
        if not lm or not (lm.start(1) <= p < lm.end(1)):
            context = g[line_start:g.find(b"\n", p)].decode("utf-8", "replace").strip()[:80]
            raise EditError(f"acknowledge-child: the secret {sid} is also named in a place the tool does not know "
                            f"({context!r}), so it cannot be removed safely; use honest instead")
        ids = [x for x in g[lm.start(1):lm.end(1)].split() if x != sid.encode()]
        if ids:
            changes.append(Change(lm.start(1), g[lm.start(1):lm.end(1)], b" " + b" ".join(ids) + b" "))
        else:
            a, b = gs.removal_span(g, lm.start(), lm.end())
            changes.append(Change(a, g[a:b], b""))
    return changes


def acknowledge_child(ctx, params: dict):
    """A man takes a child of his wife (or former wife) as his own in law: the child joins his `child={ }` list in
    birth order and loses every bastard-family trait; `real_father` is kept. The parentage secret becomes the game's
    "disputed heritage" secret (`honest`), or is removed with every mention of it (`clean`)."""
    from .translate import traits_lookup
    past = str(params["past"]).strip().lower()
    if past not in PASTS:
        raise EditError(f"acknowledge-child: the past is honest (the truth stays a secret that can be found out) "
                        f"or clean (no secret is left), not {params['past']!r}")
    g, ix = ctx.gamestate, ctx.characters
    child, father = ix.character(int(params["child"])), ix.character(int(params["father"]))
    if child is None:
        raise EditError(f"acknowledge-child: no living character has the id {params['child']}")
    if father is None:
        raise EditError(f"acknowledge-child: no living character has the id {params['father']}")
    if father.female:
        raise EditError(f"acknowledge-child: {father.id} {father.first_name} is a woman; a save records a child's "
                        "real mother only, so only a legal father can be set")
    if father.id == child.id:
        raise EditError("acknowledge-child: a character cannot be their own father")
    if child.father is not None and child.father != father.id:
        raise EditError(f"acknowledge-child: {child.id} {child.first_name} already has a legal father, "
                        f"{child.father} {ix.first_names.get(child.father, '?')}; this edit does not move a child "
                        "from one father to another")
    if child.mother is None:
        raise EditError(f"acknowledge-child: no mother of {child.id} {child.first_name} is recorded, so there is "
                        "no wife whose child this could be")
    me = _entry_of(ix, child.mother)
    fam = _family(g, me) if me else None
    spouses = set()
    if fam:
        for m in _SPOUSES.finditer(g, fam[0], fam[1]):
            spouses |= {int(m.group(1))} if m.group(1) else {int(x) for x in m.group(2).split()}
    note = ""
    if father.id not in spouses:
        if not ctx.dangerous:
            raise EditError(f"acknowledge-child: {father.id} {father.first_name} is not a husband or former husband "
                            f"of the child's mother, {child.mother} {ix.first_names.get(child.mother, '?')}; "
                            "--dangerous allows it")
        note = "; not the mother's husband (--dangerous)"
    changes, parts = [], []
    if child.father is None:
        fe = _entry_of(ix, father.id)
        ffam = _family(g, fe)
        if ffam is None:
            raise EditError(f"acknowledge-child: {father.id} {father.first_name} has no family block in this save, "
                            "and the tool does not make one yet")
        cm = _CHILDREN.search(g, ffam[0], ffam[1])
        if cm:
            kids = [int(x) for x in cm.group(1).split()]
            mine = _birth_key(g, _entry_of(ix, child.id))
            at = sum(1 for k in kids if _birth_key(g, _entry_of(ix, k)) <= mine)
            new = kids[:at] + [child.id] + kids[at:]
            span = (cm.start(1) - 1, cm.end(1) + 1)          # the braces and what is between them
            changes.append(Change(span[0], g[span[0]:span[1]], _list_text(new)))
        else:
            nl = b"\r\n" if g[ffam[1] - 2:ffam[1]] == b"\r\n" else b"\n"
            changes.append(Change(ffam[1], b"", b"\t\tchild=" + _list_text([child.id]) + nl))
        parts.append(f"{father.id} {father.first_name} lists him as a child")
    names = traits_lookup(g)
    drop = {str(i).encode() for i, n in enumerate(names) if n in BASTARD_TRAITS}
    ce = _entry_of(ix, child.id)
    tm = _TRAITS.search(g, ce.open, ce.close)
    if tm:
        have = tm.group(1).split()
        gone = [names[int(x)] for x in have if x in drop]
        if gone:
            keep = [x for x in have if x not in drop]
            changes.append(Change(tm.start(1) - 1, g[tm.start(1) - 1:tm.end(1) + 1],
                                  b"{ " + b" ".join(keep) + b" }" if keep else b"{ }"))
            parts.append("traits removed: " + ", ".join(gone))
    for sid, entry, kind, a, b in _parentage_secrets(g, child.id):
        if past == "clean":
            changes += _remove_secret(g, sid, entry)
            parts.append(f"secret {sid} ({kind}) removed")
        elif kind != "secret_disputed_heritage":
            changes.append(Change(a, g[a:b], b"secret_disputed_heritage"))
            parts.append(f"secret {sid} becomes secret_disputed_heritage")
    real = re.search(rb"(?m)^\t\treal_father=(\d+)", g[ce.open:ce.close])
    who = " ".join(ix.describe(child).split())
    if not changes:
        return [], f"{child.id} {child.first_name} is already {father.first_name}'s child in law, with nothing to " \
                   "remove"
    keep_real = f"real father {int(real.group(1))} {ix.first_names.get(int(real.group(1)), '?')} kept" if real \
        else "no real father recorded"
    return changes, f"{who}: " + "; ".join(parts + [keep_real]) + note


# --------------------------------------------------------------------------- set-eminent-holy-sites
# The game's own rule (common/decisions/50_holy_site_decisions.txt:33-38, elevate_holy_site_decision): a site must
# already be one of the faith's holy sites, and a faith has 1 to 3 eminent ones (defines FAITH_EMINENT_HOLY_SITES_MIN /
# _MAX_DEFAULT, 00_defines.txt:920-927). In a save, holy_sites={} lists every site and eminent_holy_sites={} the subset
# (all 104 faiths of the founding campaign). Design: 2026-11-16__15-00-12__dev-workflow-process__three-faith-edits-...
EMINENT_MIN, EMINENT_MAX = 1, 3
_RULE_HOLY = "game/common/decisions/50_holy_site_decisions.txt:33-38"


def _faith_entry(g: bytes, faith_id: str):
    from . import gamestate as gs
    db = gs.locate(g, "faiths/database")
    return next(e for e in gs.iter_entries(g, db.open + 1, db.close) if e.key == faith_id.encode())


def set_eminent_holy_sites(ctx, params: dict):
    """A faith's eminent holy sites: 1 to 3 of its own holy sites, as the head of faith may choose in play. Only the
    faith's ``eminent_holy_sites={}`` changes; the sites' own faith lists do not record eminence."""
    from . import faith_lookup as FL
    from .names import book, parse_list
    g, bk = ctx.gamestate, book(ctx.game_dir)
    try:
        faith = FL.find_faith(g, str(params["faith"]), book=bk)
        table = FL.holy_sites(g)
        # "Bodh Gaya, Jerusalem, Iona" or "jerusalem rome iona"; a name two sites share is settled by the faith's own
        want = [it.value for it in parse_list(str(params["sites"]), resolve=lambda s: FL.find_holy_site(
            g, s, table, book=bk, prefer=faith.holy_sites))]
    except LookupError as e:
        raise EditError(f"set-eminent-holy-sites: {e}") from None
    label = lambda ids: ", ".join(f"{FL.holy_site_name(table.get(i, '?'), bk)} ({i})" for i in ids) or "none"
    problems = []
    if len(set(want)) != len(want):
        problems.append("a site is named twice")
    stray = [i for i in want if i not in faith.holy_sites]
    if stray:
        problems.append(f"{label(stray)} {'is' if len(stray) == 1 else 'are'} not among the faith's holy sites "
                        f"({label(faith.holy_sites)}); the game makes only a faith's own holy site eminent ({_RULE_HOLY})")
    if not EMINENT_MIN <= len(set(want)) <= EMINENT_MAX:
        problems.append(f"a faith has {EMINENT_MIN} to {EMINENT_MAX} eminent holy sites, not {len(set(want))} "
                        "(game/common/defines/00_defines.txt:920-927)")
    if problems and not ctx.dangerous:
        raise EditError("set-eminent-holy-sites: " + "; ".join(problems) + " (--dangerous writes it anyway)")
    name = faith.name or faith.tag or faith.id
    if want == faith.eminent:
        return [], f"faith {faith.id} {name}: eminent holy sites are already {label(want)}"
    e = _faith_entry(g, faith.id)
    body = g[e.open:e.close]
    new = b"eminent_holy_sites={ " + b" ".join(i.encode() for i in want) + b" }"
    m = re.search(rb"(?m)^\t+(eminent_holy_sites=\{[^}\n]*\})", body)
    if m:
        change = Change(e.open + m.start(1), m.group(1), new)
    else:                                   # after holy_sites, where the game writes it
        h = re.search(rb"(?m)^(\t+)holy_sites=\{[^}\n]*\}(\r?\n)", body)
        if h is None:
            raise EditError(f"set-eminent-holy-sites: faith {faith.id} has no holy_sites line to place it after")
        change = Change(e.open + h.end(), b"", h.group(1) + new + h.group(2))
    forced = f" (forced: {'; '.join(problems)})" if problems else ""
    return [change], f"faith {faith.id} {name}: eminent holy sites {label(faith.eminent)} -> {label(want)}{forced}"


# --------------------------------------------------------------------------- set-faith
# A character's faith is one depth-1 line of their entry, rite=<rite id> (every living and dead character of the v16
# golden has exactly one, 44,553 + 38,925, measured 2026-11-16); the rite names its faith, the faith its religion.
# Design: 2026-11-16__15-00-12__dev-workflow-process__three-faith-edits-eminent-sites-doctrines-set-faith.md
_RITE_LINE = re.compile(rb"(?m)^\trite=(\d+)\r?$")


def _rite_label(r, faiths: dict, bk=None) -> str:
    """A rite as a player knows it: the name the game shows (Shafi'i) with a game folder, else its type (shafii); a
    custom faith's own rite (source=fallback, rite 152 of Way of Scarcity in v16) has no name, type or tag, and is
    known by its faith."""
    from .faith_lookup import rite_name
    own = rite_name(r, bk)
    if own:
        return f"{own} ({r.id})"
    f = faiths.get(r.faith)
    return f"{(f.name or f.tag) if f else 'faith ' + str(r.faith)}'s own rite ({r.id})"


def _faith_label(faiths: dict, fid) -> str:
    f = faiths.get(fid)
    return f"{(f.name or f.tag) if f else '?'} ({fid})"


def set_faith(ctx, params: dict):
    """A character's rite, as a conversion in play would set it: the target is a rite (by number, key or name) or a
    faith, which means its main rite. Only the character's ``rite=`` line changes; titles, holy orders and faith heads
    stay as they are. A dead character is changed only under ``--dangerous``."""
    from . import faith_lookup as FL
    from .characters import CharacterError, resolve_character
    g, ix = ctx.gamestate, ctx.characters
    who = " ".join(str(params["who"]).split())
    dead = False
    try:
        c = resolve_character(g, who, ix)
        cid, entry, first = c.id, ix.living[c.id], ix.shown(c.first_name)
    except CharacterError as exc:
        if not (who.isdigit() and int(who) in ix.dead):
            raise EditError(f"set-faith: {exc}") from None
        cid, entry, dead = int(who), ix.dead[int(who)], True
        first = ix.shown(ix.first_names.get(cid, "")) or "?"
        if not ctx.dangerous:
            raise EditError(f"set-faith: {cid} {first} is dead; the game converts only the living "
                            "(--dangerous changes the dead character's record anyway)")
    rites, faiths, bk = FL.rites(g), FL.faiths(g), ix.book
    target = str(params["target"]).strip()
    try:
        rite = FL.find_rite(g, target, rites, book=bk)
        how = ""
    except LookupError as rite_err:
        try:
            faith = FL.find_faith(g, target, faiths, book=bk)
        except LookupError as faith_err:
            raise EditError(f"set-faith: {target!r} is neither a rite nor a faith ({rite_err}; {faith_err})") from None
        if faith.main_rite not in rites:
            raise EditError(f"set-faith: faith {faith.id} {faith.name or faith.tag} names no main rite in this save")
        rite, how = rites[faith.main_rite], f", the main rite of {_faith_label(faiths, faith.id)}"
    body = g[entry.open:entry.close]
    m = _RITE_LINE.search(body)
    if m is None:
        raise EditError(f"set-faith: {cid} {first} has no rite= line to change")
    old = rites.get(m.group(1).decode())
    old_text = _rite_label(old, faiths, bk) if old else m.group(1).decode()
    if m.group(1).decode() == rite.id:
        return [], f"{cid} {first} already follows {_rite_label(rite, faiths, bk)}"
    notes = []
    if old is None or old.faith != rite.faith:
        notes.append(f"faith {_faith_label(faiths, old.faith if old else None)} -> {_faith_label(faiths, rite.faith)}: "
                     "under a same-faith succession law this can change who inherits from them and whom they inherit")
    notes.append("titles, holy orders and faith heads are unchanged")
    if dead:
        notes.append("dead: forced")
    what = f"{cid} {first}: rite {old_text} -> {_rite_label(rite, faiths, bk)}{how}; " + "; ".join(notes)
    return [Change(entry.open + m.start(1), m.group(1), rite.id.encode())], what


# --------------------------------------------------------------------------- set-doctrines
# A 1.20 faith keeps its tenets and doctrines twice, as `tenet=` / `doctrine=` lines of the faith entry (3 tabs) and
# of its main rite's data={} (4 tabs); Way of Scarcity's 24 lines are the same set in both (measured on v16). The rules
# come from the game's files (faith_rules.py). Design: 2026-11-16__15-00-12__dev-workflow-process__three-faith-edits-...


def _faith_lines(g: bytes, start: int, end: int, tabs: int) -> list:
    """(start, end, kind, key, newline) of each tenet=/doctrine= line at exactly `tabs` tabs in g[start:end]."""
    rx = re.compile(rb"(?m)^" + b"\t" * tabs + rb"(tenet|doctrine)=(\S+)(\r?\n)")
    return [(m.start(), m.end(), m.group(1).decode(), m.group(2).decode(), m.group(3)) for m in rx.finditer(g, start, end)]


def _religion_tag(g: bytes, religion_id: str | None) -> str | None:
    from . import gamestate as gs
    try:
        db = gs.locate(g, "religion/religions")
    except gs.GamestateError:
        return None
    for e in gs.iter_entries(g, db.open + 1, db.close):
        if e.key == str(religion_id).encode():
            m = re.search(rb'(?m)\btag="?([\w]+)"?', g[e.open:e.close])
            return m.group(1).decode() if m else None
    return None


def _rewrite(g: bytes, lines: list, replaced: dict, removed: set, adds: list, indent: bytes) -> list:
    """The Changes that make one location's lines say the new set: a replaced key rewritten in place, a removed key's
    line dropped, and each key still to add written after the last line of its kind (or the last line)."""
    keys_here = {k for *_, k, _ in lines}
    new = {i: g[s:e] for i, (s, e, *_r) in enumerate(lines)}
    todo = [k for k in adds if k not in keys_here]
    for i, (s, e, kind, key, nl) in enumerate(lines):
        if key in replaced:
            to = replaced[key]
            new[i] = b"" if to in keys_here else indent + (b"tenet=" if to.startswith("tenet_") else b"doctrine=") \
                + to.encode() + nl
            todo = [k for k in todo if k != to]
        elif key in removed:
            new[i] = b""
    for k in [v for old, v in replaced.items() if old not in keys_here and v not in keys_here]:
        if k not in todo:
            todo.append(k)
    if todo and lines:
        for k in todo:
            kind = "tenet" if k.startswith("tenet_") else "doctrine"
            same = [i for i, ln in enumerate(lines) if ln[2] == kind]
            at = same[-1] if same else len(lines) - 1
            new[at] = new[at] + indent + f"{kind}={k}".encode() + lines[at][4]
    return [Change(s, g[s:e], new[i]) for i, (s, e, *_r) in enumerate(lines) if new[i] != g[s:e]]


def set_doctrines(ctx, params: dict):
    """A faith's tenets and doctrines, as a reformation in play would set them: `+key` adds (a doctrine replaces its
    group's current one), `-key` removes. The faith's lines and its main rite's data change together. What the game
    refuses is refused, naming its rule; ``--dangerous`` writes it anyway."""
    from . import faith_lookup as FL
    from . import faith_rules
    from . import gamestate as gs
    g = ctx.gamestate
    if ctx.game_dir is None:
        raise EditError("set-doctrines: the game's own files are needed to know its rules; set CK3_GAME_DIR to the "
                        "game's 'game' folder")
    rules = faith_rules.load(str(ctx.game_dir))
    from .names import book, parse_list
    bk = book(ctx.game_dir)
    try:
        faith = FL.find_faith(g, str(params["faith"]), book=bk)
    except LookupError as e:
        raise EditError(f"set-doctrines: {e}") from None
    nm = lambda k: (bk.display(f"{k}_name") if bk else None) or k        # "Christian Syncretism", else the key
    gn = lambda grp: (bk.display(f"{grp}_name") if bk else None) or grp  # "Pilgrimage Attitude", else the key
    adds, removes = [], []
    try:   # "+doctrine_x -tenet_y", "-Jewish Syncretism, +Christian Syncretism", "+Pilgrimage Attitude: Encouraged"
        items = parse_list(str(params["changes"]), modifiers=True)
    except LookupError as e:
        raise EditError(f"set-doctrines: {e}") from None
    for it in items:
        try:
            key = faith_rules.find_belief(rules, it.text, bk)
        except LookupError as e:
            if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", it.text):   # a game key has an underscore; a name
                raise EditError(f"set-doctrines: {e}") from None          # ("Encouraged") keeps its refusal
            key = it.text            # a key the game does not define: refused below as such, or forced
        (removes if it.sign == "-" else adds).append(key)
    if not adds and not removes:
        raise EditError("set-doctrines: name a change: +key adds a tenet or doctrine, -key removes one")
    fe = _faith_entry(g, faith.id)
    flines = _faith_lines(g, fe.open, fe.close, 3)
    rlines, rite_id = [], faith.main_rite
    if rite_id:
        db = gs.locate(g, "rites/database")
        re_ = next((e for e in gs.iter_entries(g, db.open + 1, db.close) if e.key == rite_id.encode()), None)
        rlines = _faith_lines(g, re_.open, re_.close, 4) if re_ else []
    have = [k for *_, k, _ in flines] + [k for *_, k, _ in rlines if k not in {x[3] for x in flines}]
    missing = [k for k in removes if k not in have]
    if missing:
        raise EditError(f"set-doctrines: faith {faith.id} does not have {', '.join(missing)}")
    adds = [k for k in adds if k not in have]
    if not adds and not removes:
        return [], f"faith {faith.id} {faith.name or faith.tag}: already has everything named"
    tag = _religion_tag(g, faith.religion)
    locked = FL.religion_doctrines(g, faith.religion)
    problems, replaced, done = [], {}, []
    is_tenet = lambda k: k in rules.tenets or k.startswith("tenet_")
    for k in adds:
        if k not in rules.doctrines and k not in rules.tenets:
            problems.append(f"{k} is not a doctrine or tenet the game defines")
        if k in rules.doctrines:
            grp = rules.doctrines[k].group
            current = [h for h in have if h in rules.doctrines and rules.doctrines[h].group == grp]
            for c in current:
                replaced[c] = k
            done.append(f"{gn(grp)}: {', '.join(nm(c) for c in current) or 'empty'} -> {nm(k)}")
    gone_tenets = [k for k in removes if is_tenet(k)]
    new_tenets = [k for k in adds if is_tenet(k)]
    for old, new in zip(gone_tenets, new_tenets):
        replaced[old] = new
        done.append(f"tenet {nm(old)} -> {nm(new)}")
    done += [f"tenet {nm(k)} removed" for k in gone_tenets[len(new_tenets):]]
    done += [f"tenet {nm(k)} added" for k in new_tenets[len(gone_tenets):]]
    removed = set(removes) | set(replaced)
    for k in removes:
        if k in rules.doctrines and k not in replaced:
            grp = rules.doctrines[k].group
            done.append(f"{gn(grp)}: {nm(k)} removed")
            if rules.group_must_be_filled(grp):
                first = rules.group_members(grp)[0].key
                problems.append(f"removing {k} leaves {grp} ({rules.group_category.get(grp)}) with no doctrine, which a "
                                f"faith does not choose in play; the game most likely reads it as the group's first, "
                                f"{first} ({rules.doctrines[first].where})")
    for k in sorted(removed & locked):
        where = rules.religion_defaults.get(tag or "", {}).get(k, "game/common/religion/religion_types")
        problems.append(f"{k} is carried by every faith of {tag or faith.religion} and is not a faith's to drop ({where})")
    final_tenets = [h for h in have if is_tenet(h) and h not in removed] + new_tenets
    if gone_tenets or new_tenets:
        if len(final_tenets) != rules.tenets_cap:
            problems.append(f"a faith holds {rules.tenets_cap} tenets, not {len(final_tenets)} ({rules.cap_where})")
        for trig, (members, where) in sorted(rules.unique_sets.items()):
            both = sorted(set(final_tenets) & members)
            if len(both) > 1:
                problems.append(f"a faith may hold only one of {', '.join(both)} ({trig}, {where})")
        for k in new_tenets:
            t = rules.tenets.get(k)
            if t and tag in t.closed_to:
                problems.append(f"{k} cannot be chosen by a faith of {tag} ({t.where})")
    if problems and not ctx.dangerous:
        raise EditError("set-doctrines: " + "; ".join(problems) + " (--dangerous writes it anyway)")
    changes = _rewrite(g, flines, replaced, removed, adds, b"\t\t\t")
    changes += _rewrite(g, rlines, replaced, removed, adds, b"\t\t\t\t")
    rites = FL.rites(g)
    others = sorted((r.id for r in rites.values() if r.faith == faith.id and r.id != rite_id), key=int)
    where = f"faith {faith.id} {faith.name or faith.tag}" + (f" and its main rite {rite_id}" if rlines else "")
    notes = [f"rites {', '.join(others)} keep their own" if others else ""]
    notes.append("the game's other conditions on choosing these in play are not checked")
    if problems:
        notes.append(f"forced: {'; '.join(problems)}")
    return changes, f"{where}: " + "; ".join(done) + "; " + "; ".join(n for n in notes if n)
