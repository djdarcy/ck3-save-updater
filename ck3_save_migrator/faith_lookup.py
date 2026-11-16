"""Faiths, rites and holy sites in a 1.20 save, found by id, tag or name: the lookups the faith edits share.

A save keeps faiths in `faiths={ database={ N={...} } }` (tag, name, religion, main_rite, holy_sites, eminent_holy_sites,
tenet= and doctrine= lines), rites in `rites={ database={ N={...} } }` (tag, name, faith, rite_type, data={...}), holy
sites in `religion={ holy_sites={ N={ holy_site_type=... } } }`, and a character's faith as `rite=<rite id>`.
Design: 2026-11-16__15-00-12__dev-workflow-process__three-faith-edits-eminent-sites-doctrines-set-faith.md.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from . import gamestate as gs


class LookupError_(LookupError):
    """Nothing matched; the message lists the nearest names."""


def _str(v: bytes | None) -> str | None:
    if v is None:
        return None
    s = v.decode("utf-8", "replace").strip()
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == '"' else s


def _fields(g: bytes, e) -> dict:
    """Depth-1 scalar fields of an entry (first writing of each); blocks as their raw text."""
    out: dict = {}
    for c in gs.iter_children(g, e.open + 1, e.close):
        if c.key and c.key.decode() not in out:
            out[c.key.decode()] = g[c.value_start:c.value_end]
    return out


def _ids(raw: bytes | None) -> list[str]:
    return raw.strip(b"{} \t\r\n").decode().split() if raw else []


@dataclass
class Faith:
    id: str
    tag: str | None
    name: str | None
    religion: str | None
    main_rite: str | None
    holy_sites: list[str] = field(default_factory=list)
    eminent: list[str] = field(default_factory=list)
    tenets: list[str] = field(default_factory=list)
    doctrines: list[str] = field(default_factory=list)


@dataclass
class Rite:
    id: str
    tag: str | None
    name: str | None
    faith: str | None
    rite_type: str | None


def _entries(g: bytes, path: str):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return []
    return [e for e in gs.iter_entries(g, b.open + 1, b.close) if e.key and e.key.isdigit()]


def faiths(g: bytes) -> dict[str, Faith]:
    out = {}
    for e in _entries(g, "faiths/database"):
        f = _fields(g, e)
        body = g[e.open:e.close]
        out[e.key.decode()] = Faith(
            e.key.decode(), _str(f.get("tag")), _str(f.get("name")), _str(f.get("religion")), _str(f.get("main_rite")),
            _ids(f.get("holy_sites")), _ids(f.get("eminent_holy_sites")),
            [_str(m) for m in re.findall(rb"(?m)^\t\t\ttenet=([^\s]+)", body)],
            [_str(m) for m in re.findall(rb"(?m)^\t\t\tdoctrine=([^\s]+)", body)])
    return out


def rites(g: bytes) -> dict[str, Rite]:
    out = {}
    for e in _entries(g, "rites/database"):
        f = _fields(g, e)
        out[e.key.decode()] = Rite(e.key.decode(), _str(f.get("tag")), _str(f.get("name")), _str(f.get("faith")),
                                   _str(f.get("rite_type")))
    return out


def holy_sites(g: bytes) -> dict[str, str]:
    """holy site id -> its type (jerusalem, iona...)."""
    return {e.key.decode(): _str(_fields(g, e).get("holy_site_type")) or "?" for e in _entries(g, "religion/holy_sites")}


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _find(kind: str, key: str, items: dict, names) -> str:
    """The id whose id, or any of `names(item)`, matches `key` (case and punctuation ignored). Exactly one, or raise."""
    if key in items:
        return key
    want = _norm(key)
    hits = [i for i, it in items.items() if want and want in {_norm(n) for n in names(it) if n}]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise LookupError_(f"{kind} {key!r} matches several: {', '.join(sorted(hits))}; give the id")
    pool = sorted({n for it in items.values() for n in names(it) if n})
    near = difflib.get_close_matches(key, pool, n=4, cutoff=0.5)
    raise LookupError_(f"no {kind} {key!r}" + (f"; nearest: {', '.join(near)}" if near else ""))


def find_faith(g: bytes, key: str, table: dict | None = None) -> Faith:
    t = table if table is not None else faiths(g)
    return t[_find("faith", key, t, lambda f: (f.tag, f.name))]


def find_rite(g: bytes, key: str, table: dict | None = None) -> Rite:
    t = table if table is not None else rites(g)
    return t[_find("rite", key, t, lambda r: (r.tag, r.name, r.rite_type))]


def find_holy_site(g: bytes, key: str, table: dict | None = None) -> str:
    t = table if table is not None else holy_sites(g)
    return _find("holy site", key, t, lambda typ: (typ,))


def religion_doctrines(g: bytes, religion: str, table: dict | None = None) -> set[str]:
    """The doctrines every faith of `religion` carries: the religion's own (a faith of it cannot drop them), as the save
    shows them (all 20 Christian faiths carry special_doctrine_is_christian_faith, measured 2026-11-16)."""
    t = table if table is not None else faiths(g)
    sets = [set(f.doctrines) for f in t.values() if f.religion == religion and f.doctrines]
    return set.intersection(*sets) if sets else set()
