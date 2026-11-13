"""The save editor: ``ck3update edit <save> <edit> [params]``, a change the player asks for by name.

One engine, two front doors (the ruling of 2026-11-08): ``update`` carries what the game decided, ``edit`` makes an
outcome the player chose. They share the save reader and the verified writer; an edit never runs inside ``update``.

An edit plans a list of :class:`Change` (an offset in the gamestate, the bytes there, the bytes to write) against the
save as read, and says in one line what it touches. The front door shows the changes, asks at a terminal unless
``--yes``, applies them and writes ``<save stem>__<edit>.ck3`` beside the original through ``savefile.write_save``
(never in place, atomic, verified). The same change list is what the ledger records and what ``revert`` undoes.

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U2).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ._version import get_version
from .config import atomic_write
from .savefile import KIND_NAMES, KIND_UNIFIED_TEXT, CK3Save, parse_header, read_save, write_save


class EditError(ValueError):
    """An edit that cannot run as asked: the message says why, in a sentence a player can act on."""


@dataclass(frozen=True)
class Change:
    offset: int                     # where in the gamestate, as read
    before: bytes                   # the bytes there now (checked before writing)
    after: bytes                    # the bytes written in their place


@dataclass(frozen=True)
class EditDef:
    name: str                       # what the player types: ck3update edit <save> <name>
    title: str                      # one line for the list and the help
    params: tuple = ()              # ((name, type, help), ...), in the order positional values fill them
    plan: Callable = None           # plan(gamestate: bytes, params: dict) -> (changes, what): the changes and a line
                                    # naming what they touch
    help: str = ""                  # a paragraph for `help <edit>`
    id: str = ""                    # its patch id in its pack ("E1"); "" for an edit defined in code
    pack: str = "builtin"           # the pack it comes from; "builtin" for an edit defined in code
    state: str = "ready"            # "ready", or why it will not run: "not trusted", "changed since trusted",
                                    # "turned off", "name taken by a built-in edit"
    span: str | None = None         # its pack's [applies] save span (">=1.20"), or None: any save


@dataclass
class Planned:
    edit: EditDef
    params: dict
    changes: list
    what: str
    save: CK3Save = field(repr=False, default=None)
    out: Path | None = None
    src: Path | None = None             # the save the edit read (its ledger, if any, is carried into the output's)
    dangerous: bool = False             # --dangerous was given: recorded in the ledger
    note: str | None = None             # what --dangerous overrode (the edit's pack leaves this save's version out)
    steps: list | None = None           # revert: change lists applied one after another (each undoes one entry)
    entries: list | None = None         # revert: the output's whole ledger, prepared by plan_revert


LEDGER_FORMAT = 1


BUILTIN: dict[str, EditDef] = {}
EDITS_PACK = "edits"                # the shipped pack of built-in edits, beside to_1_20 (the ruling of 2026-11-08)
_pack_read = False


def register(edit: EditDef) -> EditDef:
    """Add a built-in edit (the shipped edits run without trust, like the shipped rules)."""
    BUILTIN[edit.name] = edit
    return edit


def builtin() -> dict[str, EditDef]:
    """The built-in edits by name: the shipped ``edits`` pack's code edits, read once, and any registered in code.
    A code edit's ``script`` names its plan function, ``plan(gamestate, params) -> (changes, what)``."""
    global _pack_read
    if not _pack_read:
        from .patches.model import load_pack
        from .patches.pack import edit_function, shipped_pack_folder
        pack = load_pack(shipped_pack_folder(EDITS_PACK), from_disk=False, context_fields=set())
        for p in pack.edits():
            if p.kind == "script":
                BUILTIN.setdefault(p.name, EditDef(p.name, p.title, p.params, edit_function(p), p.help, p.id,
                                                   pack.id))
        _pack_read = True              # only once every edit loaded: a failure part-way is tried again
    return BUILTIN


def _named(e: EditDef, want: str) -> bool:
    return want in (e.name.lower(), e.id.lower() or None)


def _declarative_plan(patch, pack_vars: dict) -> Callable:
    """The plan function of a declarative edit: its ``[[edit]]`` tables run through the patch engine, with the
    edit's values (and the pack's ``vars.toml``) filling the ``@@name@@`` templates. Nothing is changed here: the
    engine's planned edits become the editor's change list."""
    def plan(gamestate: bytes, params: dict):
        from .patches import engine
        values = {**{k: str(v) for k, v in pack_vars.items()}, **{k: str(v) for k, v in params.items()}}
        pl = engine.plan(gamestate, patch, values)
        if pl.failure:
            raise EditError(f"{patch.name}: {pl.failure}")
        skipped = [r["skipped"] for r in pl.stats if r.get("skipped")]
        if skipped:
            raise EditError(f"{patch.name}: {patch.source}: {skipped[0]}")
        changes = [Change(e.start, gamestate[e.start:e.end], e.replacement) for e in pl.edits]
        parts = []
        for name, kind, _ in patch.params:
            if kind == "character":
                from .characters import index_for
                ix = index_for(gamestate)
                c = ix.character(int(params[name]))
                parts.append(" ".join(ix.describe(c).split()) if c else f"{name}={params[name]}")
            else:
                parts.append(f"{name}={params[name]}")
        found = sum(r.get("found", 0) for r in pl.stats)
        if not changes:
            parts.append("no such place in this save" if not found else "already so")
        return changes, "; ".join(parts) or f"{len(changes)} change(s)"
    return plan


def player_edits() -> list[EditDef]:
    """The edits in the player's own packs (the packs folder and ``pack_dirs``), each with its state. A declarative
    edit runs as it is; one that runs code needs its pack trusted, like a fix (``ck3update trust``). No code of a
    pack is imported here: a code edit's function loads when it runs. An edit that names a program (``[run]``) is
    not offered."""
    from .config import disabled_ids
    from .patches.pack import edit_function
    from .userpacks import find_user_packs
    off, out = set(disabled_ids()), []
    taken = {x for e in builtin().values() for x in (e.name.lower(), e.id.lower()) if x} | {"revert"}
    for up in find_user_packs().packs:
        for p in up.pack.edits():
            if p.kind == "run":
                continue
            state = "ready" if up.state == "runs" else up.state
            if p.id in off:
                state = "turned off"
            if p.name.lower() in taken or p.id.lower() in taken:
                state = "name taken by a built-in edit"
            plan = _declarative_plan(p, up.vars) if p.kind == "declarative" else \
                (lambda g, params, _p=p: edit_function(_p)(g, params))
            out.append(EditDef(p.name, p.title, p.params, plan, p.help, p.id, up.pack.id, state,
                               (up.pack.applies or {}).get("save")))
    return out


def lookup(name: str) -> EditDef | None:
    """The edit a player names, by its name or its patch id, any case; ``revert`` too. A built-in edit is found
    without reading the player's packs. None when there is none."""
    want = name.strip().lower()
    if want == "revert":
        return REVERT
    hit = next((e for e in builtin().values() if _named(e, want)), None)
    return hit or next((e for e in player_edits() if _named(e, want)), None)


def outside_span(e: EditDef, save_version: str | None) -> bool:
    """Does the edit's pack declare a save span that leaves this save's version out? Unknown either way: no."""
    if not e.span or not save_version:
        return False
    from .patches.model import span_matches
    return span_matches(e.span, save_version) is False


def listing(save_version: str | None = None) -> list[tuple[str, str, str, str, str]]:
    """One row per edit the door offers: (id, name, pack, state, title). A shipped edit is always ``ready``; a
    player's may be ``not trusted``, ``changed since trusted`` or ``turned off``; with a save's version, an edit
    whose pack leaves that version out is ``outside this save's version``."""
    rows = [(e.id or "-", e.name, e.pack, "ready", e.title)
            for e in sorted(builtin().values(), key=lambda e: (e.id == "", e.id, e.name))]
    rows.append(("-", REVERT.name, REVERT.pack, "ready", REVERT.title))
    for e in player_edits():
        state = "outside this save's version" if e.state == "ready" and outside_span(e, save_version) else e.state
        rows.append((e.id or "-", e.name, e.pack, state, e.title))
    return rows


def check_runnable(e: EditDef, save_version: str | None, dangerous: bool) -> str | None:
    """Refuse an edit that may not run, with what to do about it. Returns a note when ``--dangerous`` let an edit
    run outside its pack's version span, else None."""
    if e.state in ("not trusted", "changed since trusted"):
        raise EditError(f"{e.name} is in your pack {e.pack}, which runs code and is {e.state}: read it, then "
                        f"`ck3update trust {e.pack}`")
    if e.state == "turned off":
        raise EditError(f"{e.name} ({e.id}) is turned off: `ck3update enable {e.id}` turns it back on")
    if e.state != "ready":
        raise EditError(f"{e.name} in your pack {e.pack}: {e.state}; give it another name and id")
    if outside_span(e, save_version):
        if not dangerous:
            raise EditError(f"{e.name} is for saves {e.span}, and this save is {save_version}; --dangerous runs it "
                            "anyway")
        return f"{e.name} runs outside its version span (saves {e.span}; this save is {save_version})"
    return None


def help_lines(e: EditDef) -> list[str]:
    """What ``ck3update help <edit>`` prints: the usage, each value with its type, and the edit's own paragraph."""
    usage = " ".join(f"<{n}>" for n, _, _ in e.params)
    out = [f"{(e.id + ' ') if e.id else ''}{e.name}: {e.title}",
           f"  pack      : {e.pack}",
           "  kind      : an edit (ck3update edit runs it; update never does)",
           f"  usage     : ck3update edit <save> {e.name}{(' ' + usage) if usage else ''}"]
    for n, kind, text in e.params:
        out.append(f"  value     : {n} ({kind})" + (f" -- {text}" if text else ""))
    if e.help:
        out += ["", "  " + e.help]
    return out


def find_edit(name: str) -> EditDef:
    e = lookup(name) if name.strip().lower() != "revert" else None
    if e is None:
        known = ", ".join(sorted(BUILTIN)) or "none yet"
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


def resolve_params(edit: EditDef, params: dict, gamestate: bytes) -> dict:
    """Turn each typed value into what the edit works on: a ``character`` becomes one living character's id (or
    the edit is refused with the candidates), a ``number`` an int; ``text`` stays as given."""
    from .characters import CharacterError, index_for, resolve_character
    out = dict(params)
    for name, kind, _ in edit.params:
        if kind == "character":
            try:
                out[name] = resolve_character(gamestate, params[name], index_for(gamestate)).id
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


# The reader for each save header kind the editor can open. Each returns a CK3Save whose gamestate is text. A
# binary (melted) reader would register its kinds here; it waits on the legal answer about shipping a token table
# (the ruling of 2026-11-08, item 7), so binary kinds are refused for now.
READERS: dict[int, Callable[[Path], CK3Save]] = {KIND_UNIFIED_TEXT: read_save}


def read_editable(save_path: Path) -> CK3Save:
    """Read a save the editor can change, through the reader for its header kind; a kind with no reader (a binary
    save: ironman, or saved in binary mode) is refused with the sentence why."""
    save_path = Path(save_path)
    if not save_path.is_file():
        raise FileNotFoundError(f"save file not found: {save_path}")
    with open(save_path, "rb") as fh:
        header = parse_header(fh.read(64))
    reader = READERS.get(header.kind)
    if reader is None:
        raise EditError(f"{save_path.name} is a binary save (ironman, or saved in binary mode; header kind "
                        f"{header.kind:02x}, {KIND_NAMES.get(header.kind, 'unknown')}); the editor reads text "
                        "saves only")
    return reader(save_path)


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


def save_version(save: CK3Save) -> str | None:
    """The game version the save's meta block names, or None."""
    from .discover import save_versions
    return save_versions(save.meta).get("version")


def plan_edit(save_path: Path, edit_name: str, tokens: list[str], *, out: Path | None = None,
              dangerous: bool = False) -> Planned:
    """Read the save, resolve the edit and its params, and plan its changes. Writes nothing. An edit that may not
    run (its pack not trusted, turned off, or for other save versions unless ``dangerous``) is refused first."""
    edit = find_edit(edit_name)
    params = parse_params(edit, tokens)
    save = read_editable(save_path)
    note = check_runnable(edit, save_version(save), dangerous)
    params = resolve_params(edit, params, save.gamestate)
    changes, what = edit.plan(save.gamestate, params)
    if not changes:
        raise EditError(f"{edit.name}: nothing to change ({what})")
    p = Planned(edit, params, list(changes), what, save, out or output_path(save_path, edit.name), save_path)
    p.note = note
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


def _entry(p: Planned, out_sha: str, in_sha: str) -> dict:
    """One ledger entry: the edit, its values, and every change with its offset in the input and in the output (the
    output offset moves by the size difference of the changes before it, so revert can work on the output)."""
    changes, shift = [], 0
    for c in sorted(p.changes, key=lambda c: c.offset):
        changes.append({"offset": c.offset, "offset_out": c.offset + shift,
                        "before": base64.b64encode(c.before).decode("ascii"),
                        "after": base64.b64encode(c.after).decode("ascii")})
        shift += len(c.after) - len(c.before)
    entry = {"edit": p.edit.name, "pack": p.edit.pack, "params": dict(p.params), "what": p.what,
             "tool": get_version(), "input_sha256": in_sha, "sha256": out_sha, "changes": changes}
    if p.dangerous:                    # the director's ruling 2026-11-13 02:32: always recorded; since U11 it also
        entry["dangerous"] = True      # overrides the save span of an edit's pack, and the entry says so
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
    cur = hashlib.sha256(save_path.read_bytes()).hexdigest()
    if entries[-1].get("sha256") != cur:
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
    save = read_editable(save_path)
    g = save.gamestate
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
    flat = [c for st in steps for c in st]
    p = Planned(REVERT, {"to": arg or "last"}, flat, "undo " + ", ".join(names), save,
                out or output_path(save_path, "revert"), save_path)
    p.steps, p.entries = steps, list(entries) + new
    return p


def write_planned(p: Planned, *, force: bool = False):
    """Apply the planned changes, write the output beside the original (never over it), and write its ledger: the
    input's ledger entries, if it had one, followed by this edit's (a revert's ledger comes ready from plan_revert)."""
    in_sha = hashlib.sha256(p.src.read_bytes()).hexdigest() if p.src else ""
    if p.steps is not None:                                # revert: undo the entries one after another
        g = p.save.gamestate
        for st in p.steps:
            g = apply_changes(g, st)
        p.save.set_gamestate(g)
        res = write_save(p.save, p.out, force=force)
        entries = p.entries
        first_new = len(entries) - len(p.steps)
        entries[first_new]["input_sha256"] = in_sha
        entries[-1]["sha256"] = res.sha256
        ledger = {"format": LEDGER_FORMAT, "save": p.out.name, "entries": entries}
        atomic_write(ledger_path(p.out), json.dumps(ledger, indent=1) + "\n")
        return res
    prior = read_ledger(p.src) if p.src else None
    p.save.set_gamestate(apply_changes(p.save.gamestate, p.changes))
    res = write_save(p.save, p.out, force=force)
    entries = list(prior["entries"]) if prior else []
    entries.append(_entry(p, res.sha256, in_sha))
    ledger = {"format": LEDGER_FORMAT, "save": p.out.name, "entries": entries}
    atomic_write(ledger_path(p.out), json.dumps(ledger, indent=1) + "\n")
    return res
