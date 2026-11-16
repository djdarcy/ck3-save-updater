"""keys: which keys a save's entries carry, read by key only, never by content (one field excepted).

* ``entry_keys``  the numeric keys of a database (its ``id={`` blocks);
* ``field_keys``  for each numeric entry, one scalar field at the entry's own depth (titles: ``key=``);
* ``scalar_map``  a section of ``token=number`` lines (``character_lookup``), whose tokens need not be numeric;
* ``union_keys``  the numeric keys of several databases together (the three character sections);
* ``key_gaps``    the keys one witness holds that another lacks, split by a third set;
* ``database_paths``  the paths of a save's databases (sections, or their children, holding many entries);
* ``field_coverage``  per field of a database's entries: how many carry it, how many leave it empty;
* ``coverage_gaps``   the fields a witness's entries carry that ours lack or leave empty.

``field_coverage`` reads field NAMES and counts, never values: an entry's value is read only to tell an empty one
(``""`` or ``{ }``) from a filled one.

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


# --------------------------------------------------------------------------- field coverage
def _is_empty(g: bytes, c: text.Child) -> bool:
    """``""`` or a block with nothing but whitespace inside: a field written but holding nothing."""
    if c.block is not None:
        return not g[c.block.open + 1:c.block.close].strip()
    return g[c.value_start:c.value_end] == b'""'


def _entries(g: bytes, b: text.Block) -> list[text.Block]:
    """The entries of a database body: ``id={...}`` blocks and anonymous ``{...}`` items (a list of records)."""
    return [e for e in text.iter_entries(g, *b.body) if e.key is None or e.key.isdigit()]


def database_paths(g: bytes, index: text.SectionIndex, min_entries: int = 20) -> list[str]:
    """The paths whose body holds at least ``min_entries`` entries: a top-level section's own entries
    (``living``), or one of its named children's (``faiths/database``). In save order."""
    out: list[str] = []
    for name, top in index.top.items():
        try:
            if len(_entries(g, top)) >= min_entries:
                out.append(name)
            for c in text.iter_entries(g, *top.body):
                if c.key and not c.key.isdigit() and len(_entries(g, c)) >= min_entries:
                    out.append(f"{name}/{c.key.decode('utf-8', 'replace')}")
        except text.SaveTextError:
            continue
    return out


def field_coverage(g: bytes, index: text.SectionIndex, path: str) -> dict:
    """Per depth-1 field of the entries of ``path``: how many entries carry it and how many leave it empty.

    Returns ``{"path", "entries": n, "unparsed": n, "first": [ids], "fields": {name: {"present": n, "empty": n,
    "missing_examples": [ids], "empty_examples": [ids]}}}``. An entry's id is its key, or ``#i`` (its position)
    when it has none. A field written twice in one entry counts once, and is empty only when every writing of it
    is empty; a second key on the same line as another
    counts (the read is structural, not by line). An entry whose body does not parse is counted in ``unparsed``
    and nowhere else. Empty when the path is absent."""
    b = text.locate(index, path)
    out: dict = {"path": path, "entries": 0, "unparsed": 0, "first": [], "fields": {}}
    if b is None:
        return out
    try:
        entries = _entries(g, b)
    except text.SaveTextError:
        return out
    seen: list[tuple[str, set, set]] = []
    for i, e in enumerate(entries):
        eid = e.key.decode() if e.key else f"#{i}"
        names: set = set()
        filled: set = set()
        try:
            for c in text.iter_children(g, *e.body):
                if c.key:
                    k = c.key.decode("utf-8", "replace")
                    names.add(k)
                    if not _is_empty(g, c):
                        filled.add(k)
        except text.SaveTextError:
            out["unparsed"] += 1
            continue
        seen.append((eid, names, names - filled))      # empty: written, but never with anything in it
    out["entries"] = len(seen)
    out["first"] = [s[0] for s in seen[:_EXAMPLES]]
    fields: dict = {}
    for eid, names, empty in seen:
        for k in names:
            f = fields.setdefault(k, {"present": 0, "empty": 0, "missing_examples": [], "empty_examples": []})
            f["present"] += 1
            if k in empty:
                f["empty"] += 1
                if len(f["empty_examples"]) < _EXAMPLES:
                    f["empty_examples"].append(eid)
    for k, f in fields.items():
        if f["present"] < len(seen):
            f["missing_examples"] = [eid for eid, names, _ in seen if k not in names][:_EXAMPLES]
    out["fields"] = fields
    return out


def coverage_gaps(ours: dict, witness: dict, threshold: float = 0.9) -> list[dict]:
    """The fields that at least ``threshold`` of the witness's entries carry filled, and that some of our entries
    lack or leave empty. ``ours`` and ``witness`` are ``field_coverage`` results for the same kind of entry (the
    witness may be ``ours`` itself: then a field our own entries nearly all carry).

    Each row: ``{"field", "witness_share", "missing", "empty", "entries", "missing_examples",
    "empty_examples"}``, sorted by how many of our entries are affected, most first. Nothing when either side
    has no entries (the caller says "nothing to compare with", never "clean")."""
    n, wn = ours["entries"], witness["entries"]
    rows: list[dict] = []
    for k, wf in witness["fields"].items():      # an empty witness has no fields; with none of ours, none missing
        share = (wf["present"] - wf["empty"]) / wn
        if share < threshold:
            continue
        f = ours["fields"].get(k)
        present = f["present"] if f else 0
        missing, empty = n - present, (f["empty"] if f else 0)
        if not missing and not empty:
            continue
        rows.append({"field": k, "witness_share": round(share, 4), "missing": missing, "empty": empty,
                     "entries": n,
                     "missing_examples": (f["missing_examples"] if f else ours["first"]),
                     "empty_examples": (f["empty_examples"] if f else [])})
    rows.sort(key=lambda r: (-(r["missing"] + r["empty"]), r["field"]))
    return rows
