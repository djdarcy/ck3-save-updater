"""Planning and applying a declarative patch's edits through ``gamestate.EditPass``.

``plan`` finds every edit a patch would make on a gamestate without making it: that is how a patch is known to be
*needed* (some edit would happen) or *done* (none would), and how ``expect`` fails closed (an edit whose count is
wrong stops the whole patch before anything is applied). ``apply_patch`` then applies the planned edits in one
splice, so everything the patch does not touch stays byte-identical.

The six operations, at each block a path addresses:

* ``delete_key``    delete each child with ``key`` (and ``where.value``, if given), tidily (``removal_span``);
* ``delete_value``  delete each bare list value equal to ``value``;
* ``delete_entry``  delete each child entry whose ``where`` holds (its own key, or one depth-1 field);
* ``rename_key``    rename each child key ``key`` to ``to``;
* ``set``           replace the value of each child ``key`` with ``value`` (no edit when already equal);
* ``insert``        insert ``payload`` at the block's ``start`` or ``end`` (skipped once the patch's ``done`` holds).

``at = "line-start"`` keeps only targets whose key (for ``delete_entry`` with ``where.field``: the field's key)
begins its line, as the rules that find their targets with a line-anchored regex do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import gamestate as gs
from . import paths as P
from .model import TEMPLATE, EditSpec, Patch, PatchError


@dataclass
class Plan:
    edits: list = field(default_factory=list)          # gs.Edit, deduplicated, in the order found
    stats: list = field(default_factory=list)          # one row per [[edit]]: found, edits, skipped
    failure: str | None = None                          # set when an expect did not hold: nothing may be applied
    done: bool = False                                  # an inserting patch whose done marker is present

    @property
    def needed(self) -> bool:
        return bool(self.edits)


# --------------------------------------------------------------------------- templates
def fill(text: str | None, values: dict) -> tuple[str | None, list[str]]:
    """``text`` with each ``@@name@@`` replaced; the names whose value is None (the edit is then skipped)."""
    if text is None:
        return None, []
    missing = []

    def sub(m):
        v = values.get(m.group(1))
        if v is None:
            missing.append(m.group(1))
            return m.group(0)
        return str(v)
    return TEMPLATE.sub(sub, text), missing


def _filled(spec: EditSpec, values: dict) -> tuple[EditSpec | None, list[str]]:
    missing: list[str] = []
    out = {}
    for f in ("key", "value", "to", "payload"):
        v, m = fill(getattr(spec, f), values)
        out[f] = v
        missing += m
    where = {}
    for k, vals in spec.where.items():
        if k == "field":
            name, vs = vals
            filled = []
            for x in vs:
                y, m = fill(x, values)
                filled.append(y)
                missing += m
            where[k] = (name, tuple(filled))
        else:
            filled = []
            for x in vals:
                y, m = fill(x, values)
                filled.append(y)
                missing += m
            where[k] = tuple(filled)
    if missing:
        return None, missing
    return EditSpec(spec.index, spec.paths, spec.op, out["key"], out["value"], out["to"], where, spec.position,
                    out["payload"], spec.expect, spec.at), []


# --------------------------------------------------------------------------- targets
def _scalar(d: bytes, c: gs.Child) -> bytes | None:
    return None if c.block is not None else d[c.value_start:c.value_end]


def _ok_start(d: bytes, spec: EditSpec, pos: int) -> bool:
    return spec.at is None or P.at_line_start(d, pos)


def _field_hit(d: bytes, entry: gs.Block, name: bytes, values: tuple[bytes, ...], spec: EditSpec) -> bool:
    for c in gs.iter_children(d, *entry.body):
        if c.key == name and _scalar(d, c) in values and _ok_start(d, spec, c.key_start):
            return True
    return False


def _in_block(d: bytes, block: gs.Block, spec: EditSpec) -> list[tuple]:
    """(kind, start, end, extra) targets of ``spec`` among ``block``'s direct children."""
    out = []
    if spec.op == "insert":
        return [("insert", block.open, block.close, None)]
    key = spec.key.encode() if spec.key is not None else None
    for c in gs.iter_children(d, *block.body):
        if spec.op in ("delete_key", "rename_key", "set"):
            if c.key != key or not _ok_start(d, spec, c.key_start):
                continue
            if spec.op == "delete_key" and "value" in spec.where:
                if _scalar(d, c) not in tuple(v.encode() for v in spec.where["value"]):
                    continue
            if spec.op == "set" and c.block is not None:
                continue
            out.append((spec.op, c.key_start, c.end, c))
        elif spec.op == "delete_value":
            if c.key is None and c.block is None and d[c.start:c.end] == spec.value.encode() \
                    and _ok_start(d, spec, c.start):
                out.append(("delete", c.start, c.end, c))
        elif spec.op == "delete_entry":
            if _entry_hit(d, c, spec):
                out.append(("delete", c.start, c.end, c))
    return out


def _entry_hit(d: bytes, c: gs.Child, spec: EditSpec) -> bool:
    w = spec.where
    if "key" in w:
        if c.key is None or c.key.decode("utf-8", "replace") not in w["key"]:
            return False
        if "field" not in w and not _ok_start(d, spec, c.key_start):
            return False
    if "field" in w:
        if c.block is None:
            return False
        name, vals = w["field"]
        return _field_hit(d, c.block, name.encode(), tuple(v.encode() for v in vals), spec)
    return True


def _prefiltered(d: bytes, spec: EditSpec, path: str) -> list[tuple]:
    """Targets of a ``**`` path, found by byte regex and resolved in grouped passes, never by a tree walk."""
    pattern = P.segments(path)
    last = pattern[-1]
    line = spec.at == "line-start"
    if last not in ("*", "**"):                       # the last segment names the block: find those blocks
        rx = P.key_regex(last, line_start=False, block=True)
        found = P.resolve(d, [m.start(1) for m in rx.finditer(d)])
        out = []
        if P.matches(pattern, [last.encode()]):        # '**' may match no depth: the top-level sections too
            for b in gs.find_sections(d, last):
                out += _in_block(d, b, spec)
        for _, (anc, child) in sorted(found.items()):
            if child.block is None or child.key != last.encode():
                continue
            if P.matches(pattern, P.chain_keys(anc) + [child.key]):
                out += _in_block(d, child.block, spec)
        return out
    out = []
    if spec.op in ("delete_key", "rename_key", "set"):
        rx = P.key_regex(spec.key, line_start=line)
        for _, (anc, c) in sorted(P.resolve(d, [m.start(1) for m in rx.finditer(d)]).items()):
            if c.key != spec.key.encode() or not P.matches(pattern, P.chain_keys(anc)):
                continue
            if spec.op == "delete_key" and "value" in spec.where:
                if _scalar(d, c) not in tuple(v.encode() for v in spec.where["value"]):
                    continue
            if spec.op == "set" and c.block is not None:
                continue
            out.append((spec.op, c.key_start, c.end, c))
    elif spec.op == "delete_value":
        rx = P.value_regex(spec.value)
        for _, (anc, c) in sorted(P.resolve(d, [m.start(1) for m in rx.finditer(d)]).items()):
            if c.key is None and c.block is None and d[c.start:c.end] == spec.value.encode() \
                    and P.matches(pattern, P.chain_keys(anc)) and (not line or P.at_line_start(d, c.start)):
                out.append(("delete", c.start, c.end, c))
    elif spec.op == "delete_entry":
        w = spec.where
        seen = set()
        if "field" in w:
            name, vals = w["field"]
            vb = tuple(v.encode() for v in vals)
            rx = P.key_regex(name, line_start=line)
            for _, (anc, c) in sorted(P.resolve(d, [m.start(1) for m in rx.finditer(d)]).items()):
                if c.key != name.encode() or _scalar(d, c) not in vb:
                    continue
                entry = anc[-1]
                if entry.start in seen:
                    continue
                if "key" in w and (entry.key is None or entry.key.decode("utf-8", "replace") not in w["key"]):
                    continue
                if not P.matches(pattern, P.chain_keys(anc[:-1])):
                    continue
                seen.add(entry.start)
                out.append(("delete", entry.start, entry.end, entry))
        else:
            for k in w["key"]:
                rx = P.key_regex(k, line_start=line)
                for _, (anc, c) in sorted(P.resolve(d, [m.start(1) for m in rx.finditer(d)]).items()):
                    if c.key == k.encode() and c.start not in seen and P.matches(pattern, P.chain_keys(anc)):
                        seen.add(c.start)
                        out.append(("delete", c.start, c.end, c))
    else:
        raise PatchError(f"edit #{spec.index}: op {spec.op!r} cannot follow a path ending in {last!r}")
    return out


def targets(d: bytes, spec: EditSpec, path: str) -> list[tuple]:
    if P.has_globstar(path):
        return _prefiltered(d, spec, path)
    out = []
    for b in P.walk(d, path):
        out += _in_block(d, b, spec)
    return out


# --------------------------------------------------------------------------- planning
def _done(d: bytes, patch: Patch) -> bool:
    if patch.done is None:
        return False
    key = patch.done["key"].encode()
    return any(c.key == key for b in P.walk(d, patch.done["path"]) for c in gs.iter_children(d, *b.body))


def _expect_ok(expect, n: int) -> bool:
    if expect == "any":
        return True
    if isinstance(expect, dict):
        return n >= expect["min"]
    return n == expect


def plan(d: bytes, patch: Patch, values: dict) -> Plan:
    """Every edit ``patch`` would make on ``d``; nothing is changed."""
    pl = Plan(done=_done(d, patch))
    seen = set()
    for spec in patch.edits:
        filled, missing = _filled(spec, values)
        row = {"edit": spec.index, "op": spec.op, "paths": list(spec.paths), "found": 0, "edits": 0}
        if filled is None:
            row["skipped"] = f"no value for {', '.join('@@' + m + '@@' for m in sorted(set(missing)))}"
            pl.stats.append(row)
            continue
        hits = []
        for path in filled.paths:
            hits += [(path, t) for t in targets(d, filled, path)]
        row["found"] = len(hits)
        if not _expect_ok(filled.expect, len(hits)):
            pl.failure = (f"{patch.source} [[edit]] #{spec.index} ({spec.op} at "
                          f"{' | '.join(spec.paths)}): expected {_say(filled.expect)}, found {len(hits)}")
            row["failed"] = pl.failure
            pl.stats.append(row)
            pl.edits = []
            return pl
        for path, (kind, start, end, c) in hits:
            e = _edit(d, filled, kind, start, end, c, patch.name, path, pl.done)
            if e is None:
                continue
            ident = (e.start, e.end, e.replacement)
            if ident in seen:
                continue
            seen.add(ident)
            pl.edits.append(e)
            row["edits"] += 1
        pl.stats.append(row)
    return pl


def _say(expect) -> str:
    return f"at least {expect['min']}" if isinstance(expect, dict) else str(expect)


def _edit(d: bytes, spec: EditSpec, kind: str, start: int, end: int, c, rule: str, path: str, done: bool):
    note = f"#{spec.index} {path}"
    if kind in ("delete", "delete_key"):
        s, e = gs.removal_span(d, start, end)
        return gs.Edit(s, e, b"", rule, note)
    if kind == "rename_key":
        return gs.Edit(c.key_start, c.key_end, spec.to.encode(), rule, note)
    if kind == "set":
        new = spec.value.encode()
        if d[c.value_start:c.value_end] == new:
            return None
        return gs.Edit(c.value_start, c.value_end, new, rule, note)
    if kind == "insert":
        if done:
            return None
        at = start + 1 if spec.position == "start" else end
        return gs.Edit(at, at, spec.payload.encode(), rule, note)
    raise PatchError(f"unknown edit kind {kind!r}")


def apply_patch(save, patch: Patch, values: dict) -> Plan:
    """Plan, then apply in one ``EditPass`` unless an ``expect`` failed (then nothing is applied)."""
    pl = plan(save.gamestate, patch, values)
    if pl.failure is None:
        p = gs.EditPass()
        for e in pl.edits:
            p.add(e)
        p.apply_to(save)
    return pl
