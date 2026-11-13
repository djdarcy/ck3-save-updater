"""The save editor: ``ck3update edit <save> <edit> [params]``, a change the player asks for by name.

One engine, two front doors (the ruling of 2026-11-08): ``update`` carries what the game decided, ``edit`` makes an
outcome the player chose. They share the save reader and the verified writer; an edit never runs inside ``update``.

The module has two halves. The catalog: what the door offers (the shipped ``edits`` pack and the player's packs,
through one loader), each with its state, its values and its help. The change machinery: an edit plans a list of
:class:`Change` (an offset in the gamestate, the bytes there, the bytes to write) against the save as read, and says
in one line what it touches. The front door shows the changes, asks at a terminal unless ``--yes``, and writes
``<save stem>__<edit>.ck3`` beside the original through ``savefile.write_save`` (never in place, atomic, verified).
The same change list is what the ledger records and what ``revert`` undoes.

What the door offers comes in two roles. An **edit**'s function is ``plan(ctx, params) -> (changes, what)``. A
**view**'s is ``show(ctx, params) -> lines``: it lists or shows, and nothing is written. ``ctx`` is an
:class:`EditContext`: the save as read, its path, version, date and seed, and the character index, built when
first asked for.

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addenda 2026-11-09 02:51, the unit
list, and 2026-11-13 04:16, the refactor-advisor's table and this shape).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Callable

from ._version import get_version
from .config import atomic_write
from .savefile import KIND_NAMES, KIND_UNIFIED_TEXT, CK3Save, parse_header, parse_save, write_save


class EditError(ValueError):
    """An edit that cannot run as asked: the message says why, in a sentence a player can act on."""


@dataclass(frozen=True)
class Change:
    offset: int                     # where in the gamestate, as read
    before: bytes                   # the bytes there now (checked before writing)
    after: bytes                    # the bytes written in their place


_DATE = re.compile(rb"(?m)^date=(\d+)\.(\d+)\.(\d+)")
_SEED = re.compile(rb"(?m)^random_seed=(\d+)")


@dataclass
class EditContext:
    """What an edit or a view is given: the save as read, and what the door already knows about it. The lookups
    are made when first asked for and kept, so two edits' worth of questions read the save once."""
    save: CK3Save
    path: Path | None = None
    input_sha256: str = ""              # of the file's bytes as read (what the ledger names as the input)

    @property
    def gamestate(self) -> bytes:
        return self.save.gamestate

    @cached_property
    def version(self) -> str | None:
        """The game version the save's meta block names."""
        from .discover import save_versions
        return save_versions(self.save.meta).get("version")

    @cached_property
    def date(self) -> tuple[int, int, int] | None:
        """The save's date (year, month, day)."""
        m = _DATE.search(self.gamestate)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None

    @cached_property
    def seed(self) -> str | None:
        """The campaign's ``random_seed`` (what a pack's ``[applies] campaign`` names)."""
        m = _SEED.search(self.gamestate)
        return m.group(1).decode() if m else None

    @cached_property
    def characters(self):
        """The character index (:class:`~ck3_save_migrator.characters.CharacterIndex`); seconds on a real save."""
        from .characters import CharacterIndex
        return CharacterIndex(self.gamestate)


@dataclass(frozen=True)
class EditDef:
    name: str                       # what the player types: ck3update edit <save> <name>
    title: str                      # one line for the list and the help
    params: tuple = ()              # ((name, type, help), ...), in the order positional values fill them
    plan: Callable = None           # an edit: plan(ctx, params) -> (changes, what), the changes and a line naming
                                    # what they touch; a view: show(ctx, params) -> lines
    help: str = ""                  # a paragraph for `help <edit>`
    id: str = ""                    # its patch id in its pack ("E1"); "" for an edit defined in code
    pack: str = "builtin"           # the pack it comes from; "builtin" for an edit defined in code
    state: str = "ready"            # "ready", or why it will not run: "not trusted", "changed since trusted",
                                    # "turned off", "name taken by a built-in edit"
    applies: dict | None = None     # its pack's [applies], without `game` (the editor resolves no game install):
                                    # a `save` span and/or a `campaign`; None: any save
    role: str = "edit"              # "edit" (plans changes) or "view" (shows, writes nothing)


@dataclass
class Planned:
    """An edit planned and not yet written. ``steps`` are change lists applied one after another (an ordinary edit
    is one step; a revert has one per entry it undoes), ``result`` the gamestate they give, and ``entries`` the
    ledger entries the write will add, their hashes filled in then."""
    edit: EditDef
    params: dict
    steps: list
    what: str
    ctx: EditContext = field(repr=False, default=None)
    out: Path | None = None
    result: bytes = field(repr=False, default=b"")
    prior: list = field(default_factory=list)        # the input's own ledger entries, carried into the output's
    entries: list = field(default_factory=list)
    dangerous: bool = False             # --dangerous was given: recorded in the ledger
    note: str | None = None             # what --dangerous overrode (the edit's pack is not for this save)

    @property
    def changes(self) -> list:
        return [c for st in self.steps for c in st]

    @property
    def save(self) -> CK3Save:
        return self.ctx.save

    @property
    def src(self) -> Path | None:
        return self.ctx.path


LEDGER_FORMAT = 1


# --------------------------------------------------------------------------- the catalog
BUILTIN: dict[str, EditDef] = {}
EDITS_PACK = "edits"                # the shipped pack of built-in edits, beside to_1_20 (the ruling of 2026-11-08)
_pack_read = False
FOR_ANOTHER_GAME = "for another save game"
OUTSIDE_VERSION = "outside this save's version"


def register(edit: EditDef) -> EditDef:
    """Add a built-in edit (the shipped edits run without trust, like the shipped rules)."""
    BUILTIN[edit.name] = edit
    return edit


def _declarative_plan(patch, pack_vars: dict) -> Callable:
    """The plan function of a declarative edit: its ``[[edit]]`` tables run through the patch engine, with the
    edit's values (and the pack's ``vars.toml``) filling the ``@@name@@`` templates. Nothing is changed here: the
    engine's planned edits become the editor's change list."""
    def plan(ctx: EditContext, params: dict):
        from .patches import engine
        g = ctx.gamestate
        values = {**{k: str(v) for k, v in pack_vars.items()}, **{k: str(v) for k, v in params.items()}}
        pl = engine.plan(g, patch, values)
        if pl.failure:
            raise EditError(f"{patch.name}: {pl.failure}")
        skipped = [r["skipped"] for r in pl.stats if r.get("skipped")]
        if skipped:
            raise EditError(f"{patch.name}: {patch.source}: {skipped[0]}")
        changes = [Change(e.start, g[e.start:e.end], e.replacement) for e in pl.edits]
        parts = []
        for name, kind, _ in patch.params:
            c = ctx.characters.character(int(params[name])) if kind == "character" else None
            parts.append(" ".join(ctx.characters.describe(c).split()) if c else f"{name}={params[name]}")
        found = sum(r.get("found", 0) for r in pl.stats)
        if not changes:
            parts.append("no such place in this save" if not found else "already so")
        return changes, "; ".join(parts) or f"{len(changes)} change(s)"
    return plan


def edits_from_pack(pack, *, state: str = "ready", pack_vars: dict | None = None, off=frozenset(),
                    taken=frozenset()) -> list[EditDef]:
    """What the door offers from one pack, the shipped one or a player's: its edits and views, each with its
    state. A declarative edit plans through the patch engine; a code edit or a view names a function, loaded only
    when it runs (so nothing of an untrusted pack is imported). A ``[run]`` program is not offered."""
    from .patches.pack import edit_function
    applies = {k: v for k, v in (pack.applies or {}).items() if k != "game"} or None
    out = []
    for p in pack.edits():
        if p.kind == "run":
            continue
        s = state
        if p.id in off:
            s = "turned off"
        if p.name.lower() in taken or p.id.lower() in taken:
            s = "name taken by a built-in edit"
        fn = _declarative_plan(p, pack_vars or {}) if p.kind == "declarative" else \
            (lambda ctx, params, _p=p: edit_function(_p)(ctx, params))
        out.append(EditDef(p.name, p.title, p.params, fn, p.help, p.id, pack.id, s, applies, p.role))
    return out


def builtin() -> dict[str, EditDef]:
    """The built-in edits by name: the shipped ``edits`` pack's, read once, and any registered in code."""
    global _pack_read
    if not _pack_read:
        from .patches.model import load_pack
        from .patches.pack import shipped_pack_folder
        pack = load_pack(shipped_pack_folder(EDITS_PACK), from_disk=False, context_fields=set())
        for e in edits_from_pack(pack):
            BUILTIN.setdefault(e.name, e)
        _pack_read = True              # only once every edit loaded: a failure part-way is tried again
    return BUILTIN


def player_edits() -> list[EditDef]:
    """The edits in the player's own packs (the packs folder and ``pack_dirs``), each with its state. A declarative
    edit runs as it is; one that runs code needs its pack trusted, like a fix (``ck3update trust``)."""
    from .config import disabled_ids
    from .userpacks import find_user_packs
    off, out = set(disabled_ids()), []
    taken = {x for e in builtin().values() for x in (e.name.lower(), e.id.lower()) if x} | {"revert"}
    for up in find_user_packs().packs:
        out += edits_from_pack(up.pack, state="ready" if up.state == "runs" else up.state, pack_vars=up.vars,
                               off=off, taken=taken)
    return out


def _named(e: EditDef, want: str) -> bool:
    return want in (e.name.lower(), e.id.lower() or None)


def lookup(name: str) -> EditDef | None:
    """The edit a player names, by its name or its patch id, any case; ``revert`` too. A built-in edit is found
    without reading the player's packs. None when there is none."""
    want = name.strip().lower()
    if want == "revert":
        return REVERT
    hit = next((e for e in builtin().values() if _named(e, want)), None)
    return hit or next((e for e in player_edits() if _named(e, want)), None)


def outside(e: EditDef, version: str | None, seed: str | None) -> tuple[str, str] | None:
    """Is the edit's pack for other saves than this one? ``(state, why)`` when its ``[applies]`` names another save
    game (``campaign``) or a save span that leaves this version out, else None. A span cannot be judged without
    the save's version, so then it is not held against the edit. The judging is ``plan._span_why``, as for a
    pack's fixes."""
    if not e.applies:
        return None
    applies = {k: v for k, v in e.applies.items() if k == "campaign" or (k == "save" and version)}
    if not applies:
        return None
    from .plan import _span_why
    ok, why, _, skip_why = _span_why(applies, version, None, seed)
    if ok:
        return None
    why = why.replace("; game: any", "")       # the editor judges no game version
    return (FOR_ANOTHER_GAME if skip_why.startswith(FOR_ANOTHER_GAME) else OUTSIDE_VERSION), why


def listing(version: str | None = None, seed: str | None = None) -> list[tuple[str, str, str, str, str]]:
    """One row per edit the door offers: (id, name, pack, state, title). A shipped edit is always ``ready``; a
    player's may be ``not trusted``, ``changed since trusted`` or ``turned off``; with a save's version and seed,
    an edit whose pack is for other saves is ``outside this save's version`` or ``for another save game``."""
    rows = [(e.id or "-", e.name, e.pack, "ready", e.title)
            for e in sorted(builtin().values(), key=lambda e: (e.id == "", e.id, e.name))]
    rows.append(("-", REVERT.name, REVERT.pack, "ready", REVERT.title))
    for e in player_edits():
        out = outside(e, version, seed) if e.state == "ready" else None
        rows.append((e.id or "-", e.name, e.pack, out[0] if out else e.state, e.title))
    return rows


def check_runnable(e: EditDef, version: str | None, seed: str | None, dangerous: bool) -> str | None:
    """Refuse an edit that may not run, with what to do about it. Returns a note when ``--dangerous`` let an edit
    run on a save its pack is not for, else None."""
    if e.state in ("not trusted", "changed since trusted"):
        raise EditError(f"{e.name} is in your pack {e.pack}, which runs code and is {e.state}: read it, then "
                        f"`ck3update trust {e.pack}`")
    if e.state == "turned off":
        raise EditError(f"{e.name} ({e.id}) is turned off: `ck3update enable {e.id}` turns it back on")
    if e.state != "ready":
        raise EditError(f"{e.name} in your pack {e.pack}: {e.state}; give it another name and id")
    out = outside(e, version, seed)
    if out:
        if not dangerous:
            raise EditError(f"{e.name}: its pack {e.pack} is not for this save ({out[1]}); --dangerous runs it "
                            "anyway")
        return f"{e.name} runs on a save its pack {e.pack} is not for ({out[1]})"
    return None


def help_lines(e: EditDef) -> list[str]:
    """What ``ck3update help <edit>`` prints: the usage, each value with its type, and the edit's own paragraph."""
    usage = " ".join(f"<{n}>" for n, _, _ in e.params)
    kind = "a view (ck3update edit shows it; nothing is written)" if e.role == "view" else \
        "an edit (ck3update edit runs it; update never does)"
    out = [f"{(e.id + ' ') if e.id else ''}{e.name}: {e.title}",
           f"  pack      : {e.pack}",
           f"  kind      : {kind}",
           f"  usage     : ck3update edit <save> {e.name}{(' ' + usage) if usage else ''}"]
    for n, kind, text in e.params:
        out.append(f"  value     : {n} ({kind})" + (f" -- {text}" if text else ""))
    if e.help:
        out += ["", "  " + e.help]
    return out


def find_edit(name: str) -> EditDef:
    e = lookup(name) if name.strip().lower() != "revert" else None
    if e is None:
        known = ", ".join(r[1] for r in listing() if r[1] != "revert") or "none yet"
        raise EditError(f"no edit named {name!r} (known: {known}); `ck3update edit --list` lists them")
    return e


def parse_params(edit: EditDef, tokens: list[str]) -> dict:
    """Values for the edit's params from the command line: ``--<name> value`` pairs, then positional values filling
    the params not named yet, in their declared order. Every param is required; an extra value is refused."""
    names = [p[0] for p in edit.params]
    out: dict = {}
    rest: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--") and t[2:].replace("-", "_") in names:
            if i + 1 >= len(tokens):
                raise EditError(f"{t} needs a value")
            out[t[2:].replace("-", "_")] = tokens[i + 1]
            i += 2
            continue
        rest.append(t)
        i += 1
    for n in names:
        if n not in out and rest:
            out[n] = rest.pop(0)
    if rest:
        raise EditError(f"{edit.name} takes {len(names)} value(s) ({', '.join(names) or 'none'}); "
                        f"not understood: {' '.join(rest)}")
    missing = [n for n in names if n not in out]
    if missing:
        usage = " ".join(f"<{n}>" for n in names)
        raise EditError(f"{edit.name} needs {', '.join(missing)}: ck3update edit <save> {edit.name} {usage}")
    return out


def resolve_params(edit: EditDef, params: dict, ctx: EditContext) -> dict:
    """Turn each typed value into what the edit works on: a ``character`` becomes one living character's id (or
    the edit is refused with the candidates), a ``number`` an int; ``text`` stays as given."""
    from .characters import CharacterError, resolve_character
    out = dict(params)
    for name, kind, _ in edit.params:
        if kind == "character":
            try:
                out[name] = resolve_character(ctx.gamestate, params[name], ctx.characters).id
            except CharacterError as exc:
                raise EditError(f"{edit.name}: {exc}") from None
        elif kind == "number":
            try:
                out[name] = int(params[name])
            except ValueError:
                raise EditError(f"{edit.name}: {name} must be a whole number, not {params[name]!r}") from None
    return out


def output_path(save_path: Path, edit_name: str) -> Path:
    """The default output: ``<save stem>__<edit>.ck3`` beside the original (djdarcy's Q261106-06 answer)."""
    return save_path.with_name(f"{save_path.stem}__{edit_name}.ck3")


# --------------------------------------------------------------------------- reading a save
# The reader for each save header kind the editor can open: reader(data, path) -> a CK3Save whose gamestate is text.
# A binary (melted) reader would register its kinds here; it waits on the legal answer about shipping a token table
# (the ruling of 2026-11-08, item 7), so binary kinds are refused for now.
READERS: dict[int, Callable[[bytes, Path], CK3Save]] = {
    KIND_UNIFIED_TEXT: lambda data, path: parse_save(data, source=path)}


def open_context(save_path: Path) -> EditContext:
    """Read a save the editor can change, once, through the reader for its header kind, and hash the bytes read. A
    kind with no reader (a binary save: ironman, or saved in binary mode) is refused with the sentence why."""
    save_path = Path(save_path)
    if not save_path.is_file():
        raise FileNotFoundError(f"save file not found: {save_path}")
    data = save_path.read_bytes()
    header = parse_header(data[:64])
    reader = READERS.get(header.kind)
    if reader is None:
        raise EditError(f"{save_path.name} is a binary save (ironman, or saved in binary mode; header kind "
                        f"{header.kind:02x}, {KIND_NAMES.get(header.kind, 'unknown')}); the editor reads text "
                        "saves only")
    return EditContext(reader(data, save_path), save_path, hashlib.sha256(data).hexdigest())


def read_editable(save_path: Path) -> CK3Save:
    """The save alone (see :func:`open_context`)."""
    return open_context(save_path).save


# --------------------------------------------------------------------------- the change machinery
def apply_changes(gamestate: bytes, changes: list) -> bytes:
    """Splice the changes in, after checking each one's ``before`` against the save and that none overlap."""
    ordered = sorted(changes, key=lambda c: c.offset)
    end = -1
    for c in ordered:
        if c.offset < end:
            raise EditError(f"internal: two changes overlap at offset {c.offset}")
        if gamestate[c.offset:c.offset + len(c.before)] != c.before:
            raise EditError(f"internal: the save at offset {c.offset} is not what the edit read")
        end = c.offset + len(c.before)
    parts, pos = [], 0
    for c in ordered:
        parts += [gamestate[pos:c.offset], c.after]
        pos = c.offset + len(c.before)
    parts.append(gamestate[pos:])
    return b"".join(parts)


def _prepare(edit_name: str, save_path: Path, tokens: list[str], dangerous: bool):
    """The steps an edit and a view share: find it, take its values, read the save, refuse what may not run, and
    resolve the values. Returns (edit, ctx, params, note)."""
    edit = find_edit(edit_name)
    params = parse_params(edit, tokens)
    ctx = open_context(save_path)
    note = check_runnable(edit, ctx.version, ctx.seed, dangerous)
    return edit, ctx, resolve_params(edit, params, ctx), note


def run_view(save_path: Path, name: str, tokens: list[str], *, dangerous: bool = False) -> list[str]:
    """Run a view: the lines it shows. Nothing is written, and no ledger is touched."""
    edit, ctx, params, _ = _prepare(name, save_path, tokens, dangerous)
    if edit.role != "view":
        raise EditError(f"{edit.name} is an edit, not a view")
    return list(edit.plan(ctx, params))


def plan_edit(save_path: Path, edit_name: str, tokens: list[str], *, out: Path | None = None,
              dangerous: bool = False) -> Planned:
    """Read the save, resolve the edit and its params, and plan its changes. Writes nothing. An edit that may not
    run (its pack not trusted, turned off, or for other saves unless ``dangerous``) is refused first."""
    edit, ctx, params, note = _prepare(edit_name, save_path, tokens, dangerous)
    if edit.role == "view":
        raise EditError(f"{edit.name} is a view: it shows and writes nothing")
    changes, what = edit.plan(ctx, params)
    changes = list(changes)
    if not changes:
        raise EditError(f"{edit.name}: nothing to change ({what})")
    led = read_ledger(save_path)
    p = Planned(edit, params, [changes], what, ctx, out or output_path(save_path, edit.name),
                apply_changes(ctx.gamestate, changes), list(led["entries"]) if led else [],
                dangerous=dangerous, note=note)
    p.entries = [_entry(p, changes)]
    return p


def ledger_path(save_path: Path) -> Path:
    """The ledger beside a save: ``<save stem>.edits.json``."""
    return save_path.with_name(f"{save_path.stem}.edits.json")


def read_ledger(save_path: Path) -> dict | None:
    """The ledger beside ``save_path``, or None. A ledger in a newer format than this tool knows is refused."""
    lp = ledger_path(save_path)
    if not lp.is_file():
        return None
    data = json.loads(lp.read_text(encoding="utf-8"))
    if data.get("format") != LEDGER_FORMAT:
        raise EditError(f"{lp.name}: ledger format {data.get('format')!r}; this tool reads format {LEDGER_FORMAT} "
                        "(update the tool)")
    return data


def _entry(p: Planned, changes: list) -> dict:
    """One ledger entry: the edit, its values, and every change with its offset in the input and in the output (the
    output offset moves by the size difference of the changes before it, so revert can work on the output). The
    two file hashes are filled in when the output is written."""
    rows, shift = [], 0
    for c in sorted(changes, key=lambda c: c.offset):
        rows.append({"offset": c.offset, "offset_out": c.offset + shift,
                     "before": base64.b64encode(c.before).decode("ascii"),
                     "after": base64.b64encode(c.after).decode("ascii")})
        shift += len(c.after) - len(c.before)
    entry = {"edit": p.edit.name, "pack": p.edit.pack, "params": dict(p.params), "what": p.what,
             "tool": get_version(), "input_sha256": None, "sha256": None, "changes": rows}
    if p.dangerous:                    # the director's ruling 2026-11-13 02:32: always recorded; since U11 it also
        entry["dangerous"] = True      # overrides what an edit's pack is for, and the entry says so
        if p.note:
            entry["dangerous_note"] = p.note
    return entry


REVERT = EditDef("revert", "undo edits recorded in the save's ledger (itself an edit, so it can be undone)",
                 (("to", "text", "the last edit (default), an entry number to go back to, or 'all'"),),
                 help="Reads the ledger beside the save and writes the bytes each undone edit replaced back in "
                      "place, last edit first. The result is a new file beside the save, with its own ledger "
                      "entry, so a revert can itself be reverted. Refused when the save has changed since its "
                      "last edit (the game, or another tool, saved it): then the backup or the original is the "
                      "way back.")


def plan_revert(save_path: Path, tokens: list[str], *, out: Path | None = None) -> Planned:
    """Plan ``revert [n|all]``: undo the ledger's entries after entry n (the last one by default, all of them for
    'all'), last first, each against the bytes the one after it left. Writes nothing."""
    led = read_ledger(save_path)
    entries = led["entries"] if led else []
    if not entries:
        raise EditError(f"{save_path.name} has no ledger beside it ({ledger_path(save_path).name}): only a save "
                        "this tool edited can be reverted")
    ctx = open_context(save_path)
    if entries[-1].get("sha256") != ctx.input_sha256:
        raise EditError(f"{save_path.name} has changed since its last edit (the game or another tool saved it); "
                        "revert works only on the file its ledger describes")
    if len(tokens) > 1:
        raise EditError("revert takes one value: nothing (the last edit), an entry number, or 'all'")
    arg = tokens[0] if tokens else None
    if arg is None:
        keep = len(entries) - 1
    elif arg == "all":
        keep = 0
    elif arg.isdigit() and int(arg) < len(entries):
        keep = int(arg)
    else:
        raise EditError(f"revert {arg}: give an entry number from 0 (the original) to {len(entries) - 1}, or 'all'")
    g = ctx.gamestate
    steps, new, names = [], [], []
    for idx in range(len(entries), keep, -1):              # entry numbers are 1-based; undo the last first
        e = entries[idx - 1]
        undo = [Change(c["offset_out"], base64.b64decode(c["after"]), base64.b64decode(c["before"]))
                for c in e["changes"]]
        g = apply_changes(g, undo)
        steps.append(undo)
        names.append(f"{idx} {e['edit']}")
        new.append({"edit": "revert", "pack": "builtin", "params": {"undoes": idx}, "what": f"undo entry {idx} "
                    f"({e['edit']}: {e.get('what', '')})", "tool": get_version(), "input_sha256": None,
                    "sha256": None, "gamestate_sha256": hashlib.sha256(g).hexdigest(),
                    "changes": [{"offset": c["offset_out"], "offset_out": c["offset"], "before": c["after"],
                                 "after": c["before"]} for c in e["changes"]]})
    return Planned(REVERT, {"to": arg or "last"}, steps, "undo " + ", ".join(names), ctx,
                   out or output_path(save_path, "revert"), g, list(entries), new)


def write_planned(p: Planned, *, force: bool = False):
    """Write the planned result beside the original (never over it), and its ledger: the input's own entries,
    followed by this edit's, the first naming the hash of the save as it was read and the last the output's."""
    p.save.set_gamestate(p.result)
    res = write_save(p.save, p.out, force=force)
    p.entries[0]["input_sha256"] = p.ctx.input_sha256
    p.entries[-1]["sha256"] = res.sha256
    ledger = {"format": LEDGER_FORMAT, "save": p.out.name, "entries": p.prior + p.entries}
    atomic_write(ledger_path(p.out), json.dumps(ledger, indent=1) + "\n")
    return res
