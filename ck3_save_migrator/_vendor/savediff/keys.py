"""keys: which keys a save's entries carry, read by key only, never by content (one field excepted).

* ``entry_keys``  the numeric keys of a database (its ``id={`` blocks);
* ``field_keys``  for each numeric entry, one scalar field at the entry's own depth (titles: ``key=``);
* ``scalar_map``  a section of ``token=number`` lines (``character_lookup``), whose tokens need not be numeric;
* ``union_keys``  the numeric keys of several databases together (the three character sections);
* ``key_gaps``    the keys one witness holds that another lacks, split by a third set.

Every function takes a ``text.SectionIndex`` built once per save. Generalised from a probe script of the host
project (see ``_VENDORED.md``).
"""
from __future__ import annotations

import re

from . import text

_LOOKUP_LINE = re.compile(rb"(?m)^\t*([^\s={}]+)=(\d+)")
_EXAMPLES = 6


def entry_keys(g: bytes, index: text.SectionIndex, path: str) -> set[int]:
    """The numeric keys of the blocks at depth 0 of ``path``; empty when the path is absent or does not parse.

    Only ``id={ ... }`` blocks count: a freed slot written ``12=none`` is not an entry."""
    b = text.locate(index, path)
    if b is None:
        return set()
    try:
        return {int(e.key) for e in text.iter_entries(g, *b.body) if e.key and e.key.isdigit()}
    except text.SaveTextError:
        return set()


def field_keys(g: bytes, index: text.SectionIndex, path: str, field: bytes = b"key") -> dict[int, str]:
    """For each numeric entry of ``path``: the value of ``field=`` at the entry's own depth, quotes removed.

    ``key="b_foo"`` and ``key=b_foo`` give ``b_foo``. A ``field=`` inside a nested block of the entry
    (``history={ key=x }``) is not read; an entry with no such field at its own depth is left out, and so is an
    entry whose body does not parse."""
    b = text.locate(index, path)
    out: dict[int, str] = {}
    if b is None:
        return out
    try:
        entries = [e for e in text.iter_entries(g, *b.body) if e.key and e.key.isdigit()]
    except text.SaveTextError:
        return out
    for e in entries:
        try:
            for c in text.iter_children(g, *e.body):
                if c.key == field and c.block is None:
                    v = g[c.value_start:c.value_end]
                    if len(v) >= 2 and v[:1] == v[-1:] == b'"':
                        v = v[1:-1]
                    out[int(e.key)] = v.decode("utf-8", "replace")
                    break
        except text.SaveTextError:
            continue
    return out


def scalar_map(g: bytes, index: text.SectionIndex, section: str) -> dict[str, int]:
    """A section of ``token=number`` lines -> ``{token: number}``; empty when the section is absent.

    The key is the whole token at the start of the line (after tabs), numeric or not: ``han_1176=5`` gives
    ``han_1176`` (an unanchored ``(\\d+)=`` would read ``1176``), ``188854bis=7`` gives ``188854bis``."""
    b = text.locate(index, section)
    if b is None:
        return {}
    return {k.decode("utf-8", "replace"): int(v) for k, v in _LOOKUP_LINE.findall(g, b.open + 1, b.close)}


def union_keys(g: bytes, index: text.SectionIndex, paths) -> set[int]:
    """The numeric keys of every path in ``paths`` together (e.g. the living, the dead kept, the dead prunable)."""
    out: set[int] = set()
    for p in paths:
        out |= entry_keys(g, index, p)
    return out


def key_gaps(sets: dict[str, set], have: str, want: str, split: set | None = None) -> dict:
    """The keys witness ``want`` holds that witness ``have`` lacks, split into those in ``split`` and the rest.

    Returns ``{"have", "want", "totals": {witness: size}, "lacking": n, "in_split": {"count", "examples"},
    "rest": {"count", "examples"}}``; examples are the first six in sorted order. The two parts are disjoint and
    together are exactly ``sets[want] - sets[have]``. With ``split=None`` everything is in ``rest``."""
    lack = set(sets[want]) - set(sets[have])
    inside = lack & set(split) if split is not None else set()
    rest = lack - inside

    def part(s: set) -> dict:
        return {"count": len(s), "examples": sorted(s)[:_EXAMPLES]}

    return {"have": have, "want": want, "totals": {n: len(s) for n, s in sets.items()}, "lacking": len(lack),
            "in_split": part(inside), "rest": part(rest)}
