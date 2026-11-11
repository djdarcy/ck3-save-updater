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
from .savefile import CK3Save, UnsupportedKindError, read_save, write_save


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


@dataclass
class Planned:
    edit: EditDef
    params: dict
    changes: list
    what: str
    save: CK3Save = field(repr=False, default=None)
    out: Path | None = None
    src: Path | None = None             # the save the edit read (its ledger, if any, is carried into the output's)


LEDGER_FORMAT = 1


BUILTIN: dict[str, EditDef] = {}


def register(edit: EditDef) -> EditDef:
    """Add a built-in edit (the shipped edits run without trust, like the shipped rules)."""
    BUILTIN[edit.name] = edit
    return edit


def find_edit(name: str) -> EditDef:
    e = BUILTIN.get(name)
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


def output_path(save_path: Path, edit_name: str) -> Path:
    """The default output: ``<save stem>__<edit>.ck3`` beside the original (djdarcy's Q261106-06 answer)."""
    return save_path.with_name(f"{save_path.stem}__{edit_name}.ck3")


def read_editable(save_path: Path) -> CK3Save:
    """Read a save the editor can change; a binary (ironman) save is refused with the sentence why."""
    try:
        return read_save(save_path)
    except UnsupportedKindError as exc:
        raise EditError(f"{save_path.name} is a binary save (ironman, or saved in binary mode); the editor reads "
                        f"text saves only ({exc})") from None


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


def plan_edit(save_path: Path, edit_name: str, tokens: list[str], *, out: Path | None = None) -> Planned:
    """Read the save, resolve the edit and its params, and plan its changes. Writes nothing."""
    edit = find_edit(edit_name)
    params = parse_params(edit, tokens)
    save = read_editable(save_path)
    changes, what = edit.plan(save.gamestate, params)
    if not changes:
        raise EditError(f"{edit.name}: nothing to change ({what})")
    return Planned(edit, params, list(changes), what, save, out or output_path(save_path, edit.name), save_path)


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
    return {"edit": p.edit.name, "pack": "builtin", "params": dict(p.params), "what": p.what,
            "tool": get_version(), "input_sha256": in_sha, "sha256": out_sha, "changes": changes}


def write_planned(p: Planned, *, force: bool = False):
    """Apply the planned changes, write the output beside the original (never over it), and write its ledger: the
    input's ledger entries, if it had one, followed by this edit's."""
    in_sha = hashlib.sha256(p.src.read_bytes()).hexdigest() if p.src else ""
    prior = read_ledger(p.src) if p.src else None
    p.save.set_gamestate(apply_changes(p.save.gamestate, p.changes))
    res = write_save(p.save, p.out, force=force)
    entries = list(prior["entries"]) if prior else []
    entries.append(_entry(p, res.sha256, in_sha))
    ledger = {"format": LEDGER_FORMAT, "save": p.out.name, "entries": entries}
    atomic_write(ledger_path(p.out), json.dumps(ledger, indent=1) + "\n")
    return res
