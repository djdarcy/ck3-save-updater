"""The player's own packs: a standard folder, extra folders, and code packs trusted once.

The standard folder is ``packs`` beside the config file (``config.config_path().parent / "packs"``; on Windows
``%APPDATA%\\ck3-save-migrator\\packs``). ``ensure_packs_dir`` creates it, the first time a command that loads rules
runs, with a README ("ADD RULES HERE") and ``_example-pack``; a folder that exists is never touched. The config's
``pack_dirs`` names extra folders, each scanned the same way: every subfolder holding a ``pack.toml``, in name order,
except those whose name starts with ``_`` or ``.``. A pack folder reached twice loads once.

Every pack found runs on every update, in the same call, after the built-in rules and before any ``--pack`` folder.
A pack of edits only runs as it is. A pack with code (a ``script`` or ``[run]`` patch) runs only when the player
trusted it (``ck3update trust <pack id>``, which records the hash of the pack's files) and its files still hash the
same, or when ``--allow-run`` is given; otherwise it is skipped and said so, and the update goes on. The hash is a
sha256 over the pack folder's files: each relative path and its bytes, in sorted order, so any edit, added file or
removed file changes it (``__pycache__`` folders and ``.pyc`` files are left out: Python writes them by itself).

A pack may carry ``vars.toml`` beside its ``pack.toml``: variables for its run patches, read when it loads; a
``--vars`` file or ``--var`` given on the command line wins.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from .config import config_path, disabled_ids, pack_dirs, trusted_packs
from .patches import read_pack, rules_from_pack
from .patches.model import Pack, PatchError, tomllib

SKIP = ("_", ".")
README = """# ADD RULES HERE

This folder holds your own packs for ck3update. Every pack in it runs on every update, in the same call, after
the tool's built-in rules: `ck3update migrate <save>` runs them without any extra option.

A pack is a folder with a `pack.toml` and one folder per patch, each with a `patch.toml`. A patch is one fix to a
save: edits addressed by a path through the save, or code. `docs/writing-a-patch.md` in the tool's documentation
explains the format; `_example-pack` here is a complete one to copy.

- A pack of edits runs as it is.
- A pack that runs code (a `script =` or `[run]` patch) runs only once you trust it: `ck3update trust <pack id>`.
  The tool records a fingerprint of the pack's files; if any file changes, it stops running the pack until you
  trust it again. `ck3update untrust <pack id>` takes the trust back.
- `ck3update packs` lists the packs found, and whether each runs.
- `ck3update disable <patch id>` turns one patch off for every later update; `ck3update enable <patch id>` turns
  it back on.
- A pack may hold a `vars.toml` beside its `pack.toml`, with the variables its run patches use (`@@name@@`).
- Folders whose name starts with `_` or `.` are not loaded (so `_example-pack` does not run). Rename a copy of it
  to use it.
- More folders like this one can be added in the config file, as `pack_dirs = ["<folder>", ...]`.
"""

EXAMPLE = {
    "pack.toml": '''format = 1
id = "example"
title = "An example pack: copy this folder, rename it without the underscore, change it"
order = ["X1"]
''',
    "X1-load-screen-name/patch.toml": '''# A patch of edits: changes the name the game's load screen shows for this save, so you can see that it ran.
# Change only keys the game itself writes: a key it does not know is reported as an error ("Unexpected token").
format = 1
id = "X1"
name = "load-screen-name"
title = "show \\"Edited with ck3update\\" as the save's name on the load screen"
since = "1.20.1.2"

[[edit]]
path = "meta_data"
op = "set"                        # set changes nothing when the value is already this one
key = "meta_player_name"
value = '"Edited with ck3update"'
''',
    "_X2-run-a-script/patch.toml": '''# A run patch: runs a program of yours over the save.
# This folder starts with "_", so it is not loaded.
# To use it: rename the folder X2-run-a-script, add "X2" to the order in pack.toml, set tools_dir in vars.toml,
# and trust the pack (`ck3update trust example`): a pack that runs code runs only once trusted.
format = 1
id = "X2"
name = "run-a-script"
title = "run my_fix.py over the save"
since = "1.20.1.2"

[run]
# @@python@@ is the Python running the tool; @@input@@ and @@output@@ are the save before and after;
# @@tools_dir@@ comes from vars.toml (or --var tools_dir=...).
command = ["@@python@@", "-I", "@@tools_dir@@/my_fix.py", "@@input@@", "@@output@@"]
needs = ["tools_dir"]
''',
    "vars.toml": '''# Variables for this pack's run patches (@@name@@ in their command).
# --vars or --var on the command line win.
# tools_dir = "C:/Users/me/ck3-tools"
''',
}


def packs_dir() -> Path:
    """The standard folder of the player's own packs, beside the config file."""
    return config_path().parent / "packs"


def ensure_packs_dir() -> bool:
    """Create the standard folder with its README and example pack, if it does not exist; True when created. A
    folder that exists is left as it is, whatever it holds."""
    folder = packs_dir()
    if folder.exists():
        return False
    for rel, text in {"README.md": README, **{f"_example-pack/{k}": v for k, v in EXAMPLE.items()}}.items():
        p = folder / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return True


def pack_hash(folder: Path) -> str:
    """sha256 over the pack folder's files: each relative path (with ``/``) and its bytes, in sorted order."""
    folder = Path(folder)
    files = sorted((p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.relative_to(folder).parts
                    and p.suffix != ".pyc"), key=lambda p: p.relative_to(folder).as_posix())
    h = hashlib.sha256()
    for p in files:
        rel = p.relative_to(folder).as_posix().encode("utf-8")
        data = p.read_bytes()
        h.update(len(rel).to_bytes(8, "big") + rel + len(data).to_bytes(8, "big") + data)
    return h.hexdigest()


def read_vars_file(path: Path, label: str) -> dict:
    """Variables from a TOML file, as ``--vars`` reads them: strings, numbers (as text) and lists of them."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{label}: not valid TOML: {exc}") from None
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            raise ValueError(f"{label}: '{k}' is a table; give a string, a number or a list")
        out[k] = [str(x) for x in v] if isinstance(v, list) else str(v)
    return out


@dataclass
class UserPack:
    folder: Path
    where: str                  # which scanned folder it was found in
    pack: Pack
    kind: str                   # "declarative" (edits only) or "code" (a script or run patch)
    hash: str
    state: str                  # "runs", "not trusted", "changed since trusted" or "turned off"
    vars: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.pack.id

    def as_dict(self) -> dict:
        return {"id": self.id, "folder": str(self.folder), "kind": self.kind, "state": self.state, "hash": self.hash}


@dataclass
class Found:
    packs: list[UserPack]
    scanned: list[tuple[Path, str, bool]]     # (folder, which, exists)
    not_packs: list[Path]                     # subfolders without a pack.toml


def scanned_folders() -> list[tuple[Path, str]]:
    return [(packs_dir(), "the standard folder")] + [(Path(os.path.expanduser(d)), "pack_dirs") for d in pack_dirs()]


def find_user_packs(builtin_ids: set[str] | None = None) -> Found:
    """Every pack in the standard folder and the ``pack_dirs`` folders. Refused (ValueError, naming both): a user
    patch id that a built-in rule has, two packs with one id, or one patch id in two packs. No code of any pack is
    imported here."""
    if builtin_ids is None:
        from .rules import REGISTRY
        builtin_ids = {r.id for r in REGISTRY}
    trusted = trusted_packs()
    off = set(disabled_ids())
    found = Found([], [], [])
    seen: set[str] = set()
    for base, which in scanned_folders():
        found.scanned.append((base, which, base.is_dir()))
        if not base.is_dir():
            continue
        for sub in sorted((c for c in base.iterdir() if c.is_dir() and not c.name.startswith(SKIP)),
                          key=lambda c: c.name):
            key = os.path.normcase(str(sub.resolve()))
            if key in seen:
                continue
            seen.add(key)
            if not (sub / "pack.toml").is_file():
                found.not_packs.append(sub)
                continue
            try:
                pack = read_pack(sub)
            except PatchError as exc:
                raise ValueError(f"your pack {sub}: {exc}") from None
            kind = "code" if any(p.kind != "declarative" for p in pack.patches.values()) else "declarative"
            digest = pack_hash(sub)
            if kind == "declarative" or trusted.get(pack.id) == digest:
                state = "runs"
            elif pack.id in trusted:
                state = "changed since trusted"
            else:
                state = "not trusted"
            if all(p.id in off for p in pack.patches.values()):
                state = "turned off"
            pvars = read_vars_file(sub / "vars.toml", f"{sub / 'vars.toml'}") if (sub / "vars.toml").is_file() else {}
            found.packs.append(UserPack(sub, which, pack, kind, digest, state, pvars))
    _refuse_collisions(found.packs, builtin_ids)
    return found


def _refuse_collisions(packs: list[UserPack], builtin_ids: set[str]) -> None:
    by_pack: dict[str, UserPack] = {}
    by_patch: dict[str, UserPack] = {}
    for up in packs:
        if up.id in by_pack:
            raise ValueError(f"two of your packs have the id {up.id!r}: {by_pack[up.id].folder} and {up.folder}; "
                             "change one pack.toml's id")
        by_pack[up.id] = up
        for pid in up.pack.order:
            if pid in builtin_ids:
                raise ValueError(f"your pack {up.folder} has a patch {pid!r}, the id of a built-in rule; give the "
                                 "patch another id")
            if pid in by_patch:
                raise ValueError(f"patch id {pid!r} is in two of your packs: {by_patch[pid].folder} and {up.folder}; "
                                 "give one another id")
            by_patch[pid] = up


def _with_pack_vars(rule, pack_vars: dict):
    """The rule, run with the pack's vars.toml under the command line's variables (which win)."""
    if not pack_vars:
        return rule
    inner = rule.apply

    def apply(save, ctx, r):
        given = ctx.state.get("patch_vars", {})
        ctx.state["patch_vars"] = {**pack_vars, **given}
        try:
            return inner(save, ctx, r)
        finally:
            ctx.state["patch_vars"] = given
    if hasattr(inner, "patch"):
        apply.patch = inner.patch
    apply.__doc__ = inner.__doc__
    return dataclasses.replace(rule, apply=apply)


def user_rules(found: Found, *, allow_run: bool) -> tuple[list, list[str], list[str]]:
    """(rules to run, what was skipped and why, patch ids skipped by the config), in loading order: each runnable
    pack's default patches that are not turned off. A code pack that is not trusted (or changed since) is skipped
    whole, before any of its code is imported, unless ``allow_run``."""
    off = set(disabled_ids())
    rules, skipped, skipped_off = [], [], []
    for up in found.packs:
        if up.state in ("not trusted", "changed since trusted") and not allow_run:
            why = ("found, not trusted: run 'ck3update trust {id}' to let it run" if up.state == "not trusted" else
                   "trust is for an earlier version of this pack (its files changed): run 'ck3update trust {id}' "
                   "again")
            skipped.append(f"your pack {up.id} ({up.folder}): " + why.format(id=up.id))
            continue
        for r in rules_from_pack(up.pack, allow_run=True):
            if not r.default:
                continue
            if r.id in off:
                skipped_off.append(r.id)
                continue
            rules.append(_with_pack_vars(r, up.vars))
    return rules, skipped, skipped_off


def runs_what(up: UserPack) -> list[str]:
    """What a pack's code patches run, one line each (for ``trust``)."""
    out = []
    for p in up.pack.ordered():
        if p.kind == "script":
            out.append(f"{p.id} {p.name}: runs Python code, {p.script} (in {p.folder})")
        elif p.kind == "run":
            cmd = p.run.get("command") or ["@@python@@", f"<scripts folder>/{p.run.get('tool')}.py",
                                           *p.run.get("args", [])]
            out.append(f"{p.id} {p.name}: runs the program {' '.join(str(c) for c in cmd)}")
    return out
