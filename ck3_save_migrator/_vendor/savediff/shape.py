"""shape: what sections a save has and how many entries each holds, by kind -- counts and key sets, no content.

``shape(g)`` reads every top-level section and every named child block one level down (the "databases"), and
counts their entries by kind: numeric keys (an id database), title-key-like keys, other keys, anonymous list
items, bare list values, scalars, freed slots. ``shape_rows`` lines up the shapes of any number of named
witnesses, path by path. Lifted from a probe script of the host project (see ``_VENDORED.md``).
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import text as gs

TITLE_KEY = re.compile(r"^[bcdkehx]_[\w\-']+$")
SCALAR_LIMIT = 32 * 1024 * 1024          # iter_children tokenises a whole body: only below this size
_TOP = re.compile(rb"(?m)^([A-Za-z_][\w.]*)[ \t]*=[ \t]*\{")


@dataclass
class Shape:
    size: int
    kinds: Counter = field(default_factory=Counter)   # num / tkey / other / anon / scalar:<kind> / bare
    keys: set = field(default_factory=set)             # distinct keys of keyed blocks and keyed scalars
    repeats: int = 1

    @property
    def count(self) -> int:
        """Entries: distinct keys when keyed (1.20 writes dead_unprunable twice), else list items / values."""
        if self.keys:
            return len(self.keys)
        return self.kinds.get("anon", 0) + self.kinds.get("bare", 0)

    @property
    def kind(self) -> str:
        if not self.kinds:
            return "empty"
        k, _ = self.kinds.most_common(1)[0]
        return k


def _kind(k: bytes | None) -> str:
    if k is None:
        return "anon"
    if k.isdigit():
        return "num"
    return "tkey" if TITLE_KEY.match(k.decode("utf-8", "replace")) else "other"


def _shape(g: bytes, blk: gs.Block, scalar_limit: int = SCALAR_LIMIT) -> Shape:
    s = Shape(blk.close - blk.open)
    try:
        for e in gs.iter_entries(g, *blk.body):
            s.kinds[_kind(e.key)] += 1
            if e.key is not None:
                s.keys.add(e.key.decode("utf-8", "replace"))
    except gs.SaveTextError:
        return s
    if s.size < scalar_limit:
        try:
            for c in gs.iter_children(g, *blk.body):
                if c.block is not None:
                    continue
                if c.key is None or c.key == b"":
                    s.kinds["bare"] += 1
                elif c.key.isdigit() and g[c.value_start:c.value_end] == b"none":
                    s.kinds["free"] += 1        # a freed slot (``12=none``), not an entry
                else:
                    s.kinds["scalar:" + _kind(c.key)] += 1
                    s.keys.add(c.key.decode("utf-8", "replace"))
        except gs.SaveTextError:
            pass
    return s


def shape(g: bytes, *, scalar_limit: int = SCALAR_LIMIT, db_threshold: int = 50,
          child_sample: int = 60) -> dict[str, Shape]:
    """Every top-level section and every named child block (one level down).

    A top-level name written more than once is shaped from its first block; ``repeats`` says how many there are.
    A section with more than ``db_threshold`` numeric entries is a database: its entries are not descended into.
    Of a section's named children, the first ``child_sample`` (counting repeats of a name) are shaped. Scalars are
    read only in bodies smaller than ``scalar_limit`` bytes.
    """
    idx = gs.SectionIndex(g)
    reps = Counter(m.group(1).decode() for m in _TOP.finditer(g))
    out: dict[str, Shape] = {}
    for name, b in idx.top.items():
        s = _shape(g, b, scalar_limit)
        s.repeats = reps.get(name, 1)
        out[name] = s
        if s.kinds.get("num", 0) > db_threshold:       # a database itself: its entries are not sub-databases
            continue
        try:
            children = [e for e in gs.iter_entries(g, *b.body) if e.key and not e.key.isdigit()]
        except gs.SaveTextError:
            continue
        seen = set()
        for c in children[:child_sample]:
            if c.key in seen:
                continue
            seen.add(c.key)
            out[f"{name}/{c.key.decode()}"] = _shape(g, c, scalar_limit)
    return out


def shape_rows(witnesses: dict[str, dict[str, Shape]]) -> dict:
    """One row per path in the union of the witnesses' shapes, in sorted path order.

    Each row: ``path``; ``kind`` (from the first witness, in the dict's order, that has the path); ``counts``,
    ``{witness: count}`` with ``None`` where the witness lacks the path (never 0: absent is not empty);
    ``repeats``, ``{witness: repeats}`` for the witnesses where a top-level name occurs more than once.

    ``sections_counted`` is the survival rule: ``{path: entries counted at that path, summed over every witness}``
    for every path read, always present, so a result with no difference still says what was read (a non-empty
    save always has at least one path).
    """
    paths = sorted(set().union(*(set(s) for s in witnesses.values()))) if witnesses else []
    rows = []
    for path in paths:
        first = next(s[path] for s in witnesses.values() if path in s)
        rows.append({"path": path, "kind": first.kind,
                     "counts": {n: (s[path].count if path in s else None) for n, s in witnesses.items()},
                     "repeats": {n: s[path].repeats for n, s in witnesses.items()
                                 if path in s and s[path].repeats > 1}})
    counted = {r["path"]: sum(c for c in r["counts"].values() if c is not None) for r in rows}
    return {"sections_counted": counted, "rows": rows}
