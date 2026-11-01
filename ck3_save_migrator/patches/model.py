"""The patch format, version 1: loading and validating ``pack.toml`` and ``patch.toml``.

A pack is a folder of patch folders with a ``pack.toml`` (``format``, ``id``, ``title``, ``order``). A patch is a
folder with a ``patch.toml``: metadata, then either ``[[edit]]`` tables (a declarative patch), ``script =`` (a code
patch: a function with the rule signature) or ``[run]`` (a run patch: a separate program run over the save).

Folders are read as ``importlib.resources`` Traversables, so the shipped pack inside the installed package and a
player's pack on disk are read the same way. Every validation error names the file and the field.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:                                   # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

FORMAT = 1
OPS = ("delete_key", "delete_value", "delete_entry", "rename_key", "set", "insert")
TEMPLATE = re.compile(r"@@([A-Za-z_][A-Za-z0-9_]*)@@")
_SCRIPT_MODULE = re.compile(r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$")
_SCRIPT_FILE = re.compile(r"^[\w./\-]+\.py:[A-Za-z_]\w*$")
_TOOL_NAME = re.compile(r"^[A-Za-z0-9_][\w\-]*$")
RUN_TIMEOUT = 600                   # seconds a run patch's command may take, unless its run.timeout says otherwise


class PatchError(ValueError):
    """A pack or patch that cannot be loaded or run as written. The message names the file and the field."""


@dataclass(frozen=True)
class EditSpec:
    index: int                      # 1-based position among the patch's [[edit]] tables
    paths: tuple[str, ...]
    op: str
    key: str | None = None
    value: str | None = None
    to: str | None = None
    where: dict = field(default_factory=dict)
    position: str | None = None
    payload: str | None = None
    expect: Any = "any"
    at: str | None = None           # "line-start": the edited child's key must begin its line
    need_path: bool = False         # fail the patch when the path addresses no block at all


@dataclass(frozen=True)
class Patch:
    id: str
    name: str
    title: str
    since: str
    default: bool
    requires: tuple[str, ...]
    tested: dict
    issue: str
    source: str                     # where it was read from, for messages
    folder: Any                     # the patch folder (a Traversable)
    from_disk: bool                 # a folder pack on disk (not the shipped package data)
    edits: tuple[EditSpec, ...] = ()
    done: dict | None = None
    script: str | None = None
    run: dict | None = None
    matched: str = "found"          # the report's matched: targets "found", "blocks" addressed, or "blocks-hit"
                                    # (blocks addressed that held a target)

    @property
    def kind(self) -> str:
        return "script" if self.script else "run" if self.run else "declarative"


@dataclass(frozen=True)
class Pack:
    id: str
    title: str
    order: tuple[str, ...]
    patches: dict                   # id -> Patch
    source: str
    from_disk: bool
    applies: dict | None = None     # [applies]: {"save": span, "game": span}; None: no version span declared
    after: str | None = None        # run right after this patch of another pack, not after the built-in rules

    def ordered(self) -> list[Patch]:
        return [self.patches[i] for i in self.order]


# --------------------------------------------------------------------------- reading
def _read(entry, where: str) -> dict:
    try:
        return tomllib.loads(entry.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PatchError(f"{where}: not valid TOML: {exc}") from None


def _need(data: dict, key: str, kind, where: str, *, default=dataclasses.MISSING):
    if key not in data:
        if default is not dataclasses.MISSING:
            return default
        raise PatchError(f"{where}: missing field '{key}'")
    v = data[key]
    if not isinstance(v, kind) or (kind is int and isinstance(v, bool)):
        names = kind.__name__ if isinstance(kind, type) else " or ".join(k.__name__ for k in kind)
        raise PatchError(f"{where}: field '{key}' must be {names}, not {type(v).__name__} ({v!r})")
    return v


def _format(data: dict, where: str) -> None:
    f = _need(data, "format", int, where)
    if f != FORMAT:
        raise PatchError(f"{where}: field 'format' is {f}; this version reads format {FORMAT}")


def _strings(v, field_name: str, where: str) -> tuple[str, ...]:
    if isinstance(v, str):
        return (v,)
    if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
        return tuple(v)
    raise PatchError(f"{where}: field '{field_name}' must be a string or a non-empty list of strings")


def _scalar(v, field_name: str, where: str) -> str:
    """A value compared or written as the save's own bytes: TOML strings as written, numbers as their digits."""
    if isinstance(v, bool):
        raise PatchError(f"{where}: field '{field_name}' must be a string or a number, not a boolean")
    if isinstance(v, (str, int)):
        return str(v)
    raise PatchError(f"{where}: field '{field_name}' must be a string or a number")


def _where(v, where: str) -> dict:
    if not isinstance(v, dict):
        raise PatchError(f"{where}: field 'where' must be a table")
    out = {}
    for k, x in v.items():
        if k == "field":
            if not isinstance(x, dict) or len(x) != 1:
                raise PatchError(f"{where}: field 'where.field' must be a table of exactly one name = value")
            (name, val), = x.items()
            vals = x[name] if isinstance(x[name], list) else [x[name]]
            out["field"] = (name, tuple(_scalar(y, f"where.field.{name}", where) for y in vals))
        elif k in ("key", "value"):
            vals = x if isinstance(x, list) else [x]
            if not vals:
                raise PatchError(f"{where}: field 'where.{k}' is an empty list")
            out[k] = tuple(_scalar(y, f"where.{k}", where) for y in vals)
        else:
            raise PatchError(f"{where}: field 'where.{k}' is not known (where takes key, value and field; "
                             "anything more is a job for script =)")
    return out


def _check_path(p: str, where: str) -> None:
    segs = p.split("/")
    if not p or any(s == "" for s in segs):
        raise PatchError(f"{where}: field 'path' has an empty segment: {p!r}")
    if segs[0] == "*":
        raise PatchError(f"{where}: field 'path' {p!r}: the first segment must be a section name or '**'")


def _expect(v, where: str):
    if v == "any":
        return "any"
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return v
    if isinstance(v, dict) and set(v) == {"min"} and isinstance(v["min"], int) and v["min"] >= 0:
        return {"min": v["min"]}
    raise PatchError(f"{where}: field 'expect' must be \"any\", a count, or {{ min = n }}, not {v!r}")


def _edit(i: int, e: dict, where: str) -> EditSpec:
    w = f"{where} [[edit]] #{i}"
    if not isinstance(e, dict):
        raise PatchError(f"{w}: must be a table")
    op = _need(e, "op", str, w)
    if op not in OPS:
        raise PatchError(f"{w}: field 'op' is {op!r}; known: {', '.join(OPS)}")
    paths = _strings(_need(e, "path", (str, list), w), "path", w)
    for p in paths:
        _check_path(p, w)
    allowed = {"path", "op", "expect", "at", "key", "value", "to", "where", "position", "payload", "need_path"}
    extra = set(e) - allowed
    if extra:
        raise PatchError(f"{w}: unknown field '{sorted(extra)[0]}'")
    at = _need(e, "at", str, w, default=None)
    if at not in (None, "line-start"):
        raise PatchError(f"{w}: field 'at' must be \"line-start\" when given, not {at!r}")
    need_path = _need(e, "need_path", bool, w, default=False)
    if need_path and any("**" in p.split("/") for p in paths):
        raise PatchError(f"{w}: field 'need_path' is for paths without '**'")
    kw: dict = {"index": i, "paths": paths, "op": op, "expect": _expect(e.get("expect", "any"), w), "at": at,
                "need_path": need_path}
    need = {"delete_key": ("key",), "delete_value": ("value",), "delete_entry": ("where",),
            "rename_key": ("key", "to"), "set": ("key", "value"), "insert": ("position", "payload")}[op]
    for f in need:
        if f not in e:
            raise PatchError(f"{w}: op '{op}' needs field '{f}'")
    if "key" in e:
        kw["key"] = _need(e, "key", str, w)
    if "value" in e:
        kw["value"] = _scalar(e["value"], "value", w)
    if "to" in e:
        kw["to"] = _need(e, "to", str, w)
    if "where" in e:
        kw["where"] = _where(e["where"], w)
        if op not in ("delete_key", "delete_entry"):
            raise PatchError(f"{w}: field 'where' is for delete_key and delete_entry only")
        if op == "delete_key" and set(kw["where"]) - {"value"}:
            raise PatchError(f"{w}: delete_key takes where = {{ value = ... }} only")
        if op == "delete_entry" and not set(kw["where"]) & {"key", "field"}:
            raise PatchError(f"{w}: delete_entry needs where.key or where.field")
    if "position" in e:
        kw["position"] = _need(e, "position", str, w)
        if kw["position"] not in ("start", "end"):
            raise PatchError(f"{w}: field 'position' must be \"start\" or \"end\"")
    if "payload" in e:
        kw["payload"] = _need(e, "payload", str, w)
    for p in paths:
        if "**" in p.split("/") and not _prefilterable(op, p, kw):
            raise PatchError(f"{w}: a path with '**' ({p!r}) must end in a named segment, or the op must name "
                             "what it looks for (a key, a value, or where.key / where.field)")
    return EditSpec(**kw)


def _prefilterable(op: str, path: str, kw: dict) -> bool:
    last = path.split("/")[-1]
    if last not in ("*", "**"):
        return True
    if op in ("delete_key", "rename_key", "set"):
        return True
    if op == "delete_value":
        return True
    if op == "delete_entry":
        return bool(kw.get("where", {}).get("field") or kw.get("where", {}).get("key"))
    return False                          # insert into "anything" cannot be prefiltered


def load_patch(folder, *, from_disk: bool, context_fields: set[str]) -> Patch:
    """One patch folder. ``context_fields``: the template names a declarative patch may use."""
    entry = folder.joinpath("patch.toml")
    where = f"{getattr(folder, 'name', folder)}/patch.toml"
    if not entry.is_file():
        raise PatchError(f"{where}: missing (every patch folder holds a patch.toml)")
    d = _read(entry, where)
    _format(d, where)
    known = {"format", "id", "name", "title", "since", "default", "requires", "tested", "issue", "edit", "done",
             "script", "run", "matched"}
    extra = set(d) - known
    if extra:
        raise PatchError(f"{where}: unknown field '{sorted(extra)[0]}'")
    pid = _need(d, "id", str, where)
    kinds = [k for k in ("edit", "script", "run") if k in d]
    if len(kinds) != 1:
        raise PatchError(f"{where}: a patch has exactly one of [[edit]], script = or [run]; found "
                         f"{', '.join(kinds) or 'none'}")
    common = dict(
        id=pid, name=_need(d, "name", str, where), title=_need(d, "title", str, where),
        since=_need(d, "since", str, where), default=_need(d, "default", bool, where, default=True),
        requires=tuple(_need(d, "requires", list, where, default=[])),
        tested=_need(d, "tested", dict, where, default={}), issue=_need(d, "issue", str, where, default=""),
        source=where, folder=folder, from_disk=from_disk)
    if not all(isinstance(r, str) for r in common["requires"]):
        raise PatchError(f"{where}: field 'requires' must be a list of patch ids")
    if "script" in d:
        script = _need(d, "script", str, where)
        if _SCRIPT_MODULE.match(script) and not _SCRIPT_FILE.match(script):
            if from_disk:
                # '<module>:<function>' would import anything on sys.path (the current folder, under python -m)
                raise PatchError(f"{where}: field 'script' {script!r}: a pack folder names a file in the patch "
                                 "folder, '<file>.py:<function>'; '<module>:<function>' is for the shipped pack")
        elif _SCRIPT_FILE.match(script):
            if not from_disk:
                raise PatchError(f"{where}: field 'script' {script!r}: a pack inside the package names "
                                 "'<module>:<function>', not a file")
            file = script.rsplit(":", 1)[0]
            if file.startswith("/") or ".." in file.split("/"):
                raise PatchError(f"{where}: field 'script' {script!r}: the file must be inside the patch folder "
                                 "(a relative path without '..')")
        else:
            raise PatchError(f"{where}: field 'script' must be '<module>:<function>' or '<file>.py:<function>', "
                             f"not {script!r}")
        for f in ("done", "matched"):
            if f in d:
                raise PatchError(f"{where}: field '{f}' is for declarative patches")
        return Patch(**common, script=script)
    if "run" in d:
        if "matched" in d:
            raise PatchError(f"{where}: field 'matched' is for declarative patches")
        run = _need(d, "run", dict, where)
        extra = set(run) - {"command", "tool", "args", "needs", "timeout", "done_command"}
        if extra:
            raise PatchError(f"{where}: unknown field 'run.{sorted(extra)[0]}'")
        if ("command" in run) == ("tool" in run):
            raise PatchError(f"{where}: [run] has exactly one of 'command' or 'tool'")
        needs = run.get("needs", [])
        if isinstance(needs, dict):            # needs = { tools_dir = "the folder holding fix_faces.py" }
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in needs.items()):
                raise PatchError(f"{where}: field 'run.needs' as a table maps each variable to its help text")
            needs_help = dict(needs)
        elif isinstance(needs, list) and all(isinstance(n, str) for n in needs):
            needs_help = {n: "" for n in needs}
        else:
            raise PatchError(f"{where}: field 'run.needs' must be a list of variable names, or a table of "
                             "name = \"help text\"")
        timeout = run.get("timeout", RUN_TIMEOUT)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise PatchError(f"{where}: field 'run.timeout' must be a number of seconds above 0")
        done_cmd = run.get("done_command")
        if done_cmd is not None and (not isinstance(done_cmd, list) or not done_cmd
                                     or not all(isinstance(c, str) for c in done_cmd)):
            raise PatchError(f"{where}: field 'run.done_command' must be a non-empty list of strings (a program "
                             "given @@input@@; exit code 0 means the patch is already done)")
        rdone = _done_field(d, where) if "done" in d else None
        if rdone is not None and done_cmd is not None:
            raise PatchError(f"{where}: a run patch has at most one done check: 'done' or 'run.done_command'")
        common_run = {"needs": tuple(needs_help), "needs_help": needs_help, "timeout": float(timeout),
                      "done_command": tuple(done_cmd) if done_cmd else None}
        common["done"] = rdone
        if "tool" in run:
            tool = run["tool"]
            if not isinstance(tool, str) or not _TOOL_NAME.match(tool):
                raise PatchError(f"{where}: field 'run.tool' must be a script name such as \"edit_save\" (the "
                                 f"file <scripts folder>/<name>.py), not {tool!r}")
            args = run.get("args", [])
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise PatchError(f"{where}: field 'run.args' must be a list of strings")
            return Patch(**common, run={"command": None, "tool": tool, "args": tuple(args), **common_run})
        if "args" in run:
            raise PatchError(f"{where}: field 'run.args' goes with 'run.tool'; put arguments in 'run.command'")
        cmd = run.get("command")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
            raise PatchError(f"{where}: field 'run.command' must be a non-empty list of strings")
        return Patch(**common, run={"command": tuple(cmd), "tool": None, "args": (), **common_run})
    raw = d["edit"]
    if not isinstance(raw, list) or not raw:
        raise PatchError(f"{where}: field 'edit' must be one or more [[edit]] tables")
    edits = tuple(_edit(i, e, where) for i, e in enumerate(raw, 1))
    for e in edits:
        where_values = [x for k, vals in e.where.items() for x in (vals[1] if k == "field" else vals)]
        for v in (e.key, e.value, e.to, e.payload, *where_values):
            for name in TEMPLATE.findall(v or ""):
                if name not in context_fields:
                    raise PatchError(f"{where} [[edit]] #{e.index}: template @@{name}@@ is not a known value "
                                     f"(known: {', '.join(sorted(context_fields))})")
    done = _done_field(d, where) if "done" in d else None
    if any(e.op == "insert" for e in edits) and done is None:
        raise PatchError(f"{where}: a patch with an insert must give field 'done' (the path and key whose presence "
                         "means it was applied), or it would insert again on every run")
    matched = _need(d, "matched", str, where, default="found")
    if matched not in ("found", "blocks", "blocks-hit"):
        raise PatchError(f"{where}: field 'matched' must be \"found\", \"blocks\" or \"blocks-hit\", not {matched!r}")
    if matched != "found" and any("**" in p.split("/") for e in edits for p in e.paths):
        raise PatchError(f"{where}: field 'matched' = {matched!r} is for paths without '**'")
    return Patch(**common, edits=edits, done=done, matched=matched)


def _done_field(d: dict, where: str) -> dict:
    """``done = { path = "...", key = "..." }``: the place and key whose presence means the patch has run."""
    done = _need(d, "done", dict, where)
    if set(done) != {"path", "key"} or not all(isinstance(x, str) for x in done.values()):
        raise PatchError(f"{where}: field 'done' must be {{ path = \"...\", key = \"...\" }}")
    _check_path(done["path"], f"{where} done")
    if "**" in done["path"].split("/"):
        raise PatchError(f"{where}: field 'done.path' may not use '**'")
    return done


def load_pack(folder, *, from_disk: bool, context_fields: set[str]) -> Pack:
    """A pack folder: its pack.toml and every patch folder in it, checked against ``order``."""
    name = getattr(folder, "name", str(folder))
    where = f"{name}/pack.toml"
    entry = folder.joinpath("pack.toml")
    if not entry.is_file():
        raise PatchError(f"{where}: missing (a pack folder holds a pack.toml)")
    d = _read(entry, where)
    _format(d, where)
    extra = set(d) - {"format", "id", "title", "order", "applies", "after"}
    if extra:
        raise PatchError(f"{where}: unknown field '{sorted(extra)[0]}'")
    applies = d.get("applies")
    if applies is not None:
        spans = {k: v for k, v in applies.items() if k != "campaign"} if isinstance(applies, dict) else None
        if spans is None or set(spans) - {"save", "game"} or not all(isinstance(v, str) for v in spans.values()):
            raise PatchError(f"{where}: [applies] holds save = \"<span>\", game = \"<span>\" (for example "
                             "save = \">=1.8, <1.20\") and campaign = { name = \"<label>\", seed = <random_seed> }")
        for k, v in spans.items():
            try:
                parse_span(v)
            except ValueError as exc:
                raise PatchError(f"{where}: [applies] {k}: {exc}") from None
        camp = applies.get("campaign")
        if camp is not None:
            seed = camp.get("seed") if isinstance(camp, dict) else None
            if not isinstance(camp, dict) or set(camp) != {"name", "seed"} or not isinstance(camp["name"], str) \
                    or isinstance(seed, bool) or not (isinstance(seed, int) or (isinstance(seed, str) and seed.isdigit())):
                raise PatchError(f"{where}: [applies] campaign = {{ name = \"<label>\", seed = <the save's "
                                 "random_seed, a number> }}")
            applies = {**applies, "campaign": {"name": camp["name"], "seed": str(seed)}}
    after = d.get("after")
    if after is not None and not (isinstance(after, str) and after):
        raise PatchError(f"{where}: field 'after' must be a patch id (for example \"R17\")")
    order = _need(d, "order", list, where)
    if not order or not all(isinstance(x, str) for x in order):
        raise PatchError(f"{where}: field 'order' must be a non-empty list of patch ids")
    if len(set(order)) != len(order):
        raise PatchError(f"{where}: field 'order' names a patch twice")
    patches: dict = {}
    for sub in sorted((c for c in folder.iterdir() if c.is_dir() and not c.name.startswith(("_", "."))),
                      key=lambda c: c.name):
        p = load_patch(sub, from_disk=from_disk, context_fields=context_fields)
        if p.id in patches:
            raise PatchError(f"{p.source}: field 'id' {p.id!r} is also used by {patches[p.id].source}")
        patches[p.id] = p
    missing = [i for i in order if i not in patches]
    if missing:
        raise PatchError(f"{where}: field 'order' names {', '.join(missing)}, which no patch folder has")
    unlisted = sorted(set(patches) - set(order))
    if unlisted:
        raise PatchError(f"{where}: field 'order' leaves out {', '.join(unlisted)}")
    for p in patches.values():
        unknown = [r for r in p.requires if r not in patches]
        if unknown:
            raise PatchError(f"{p.source}: field 'requires' names {', '.join(unknown)}, not in this pack")
    return Pack(_need(d, "id", str, where), _need(d, "title", str, where), tuple(order), patches, where,
                from_disk, dict(applies) if applies else None, after)


# --------------------------------------------------------------------------- version spans ([applies])
_SPAN_PART = re.compile(r"^\s*(>=|<=|==|!=|>|<|=)?\s*v?(\d+(?:\.\d+)*)\s*$")


def parse_span(text: str) -> list[tuple[str, str]]:
    """``">=1.8, <1.20"`` -> ``[(">=", "1.8"), ("<", "1.20")]``: comma-separated comparisons on dotted versions
    (a bare version means ``==``). Every comparison must hold."""
    parts = [p for p in text.split(",") if p.strip()]
    if not parts:
        raise ValueError(f"{text!r} is empty (write comparisons such as \">=1.8, <1.20\")")
    out = []
    for p in parts:
        m = _SPAN_PART.match(p)
        if not m:
            raise ValueError(f"{p.strip()!r} is not a comparison on a dotted version (such as >=1.20)")
        out.append((m.group(1) if m.group(1) not in (None, "=") else "==", m.group(2)))
    return out


def span_matches(text: str, version: str | None) -> bool | None:
    """Whether ``version`` satisfies the span; None when the version has no number to compare."""
    from ..discover import compare_versions
    for op, v in parse_span(text):
        c = compare_versions(version, v)
        if c is None:
            return None
        if not {">=": c >= 0, "<=": c <= 0, "==": c == 0, "!=": c != 0, ">": c > 0, "<": c < 0}[op]:
            return False
    return True


def as_folder(path) -> Any:
    """A folder given as a path string or Path, or already a Traversable."""
    return Path(path) if isinstance(path, (str, Path)) else path
