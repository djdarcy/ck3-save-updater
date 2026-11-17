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
from .names import NO_GAME_HINT, NameBook, norm


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
    return norm(s or "")


def _find(kind: str, key: str, items: dict, names, *, label=None, prefer=None, book=None, hint=True) -> str:
    """The id whose id, or any of `names(item)`, matches `key` (names.norm: case, accents and punctuation ignored).
    `prefer` (ids) is tried first when several match: a faith's own holy sites before all holy sites. Exactly one,
    or LookupError_ listing the candidates by `label(id)` (with their ids), or the nearest names."""
    if key in items:
        return key
    want = _norm(key)
    hits = [i for i, it in items.items() if want and want in {_norm(n) for n in names(it) if n}]
    if len(hits) > 1 and prefer:
        mine = [i for i in hits if i in set(prefer)]
        if len(mine) == 1:
            return mine[0]
    if len(hits) == 1:
        return hits[0]
    show = label or (lambda i: i)
    if len(hits) > 1:
        raise LookupError_(f"{kind} {key!r} names {len(hits)}: {', '.join(show(i) for i in sorted(hits))}; "
                           "write the one you mean")
    pool = sorted({n for it in items.values() for n in names(it) if n})
    near = difflib.get_close_matches(key, pool, n=4, cutoff=0.5)
    raise LookupError_(f"no {kind} {key!r}" + (f"; nearest: {', '.join(near)}" if near else "")
                       + ("" if book or not hint else f" ({NO_GAME_HINT})"))


def find_faith(g: bytes, key: str, table: dict | None = None, *, book: NameBook | None = None) -> Faith:
    t = table if table is not None else faiths(g)
    shown = (lambda f: book.display(f.tag)) if book else (lambda f: None)
    return t[_find("faith", key, t, lambda f: (f.tag, f.name, shown(f)), book=book, hint=False,
                   label=lambda i: f"{t[i].name or t[i].tag} ({i})")]     # a faith's name is in the save itself


def rite_name(r: Rite, book: NameBook | None = None) -> str | None:
    """The name the game shows for a rite (Shafi'i), or its own name/type/tag without a game folder."""
    return (book.display(r.rite_type) if book and r.rite_type else None) or r.name or r.rite_type or r.tag


def find_rite(g: bytes, key: str, table: dict | None = None, *, book: NameBook | None = None) -> Rite:
    t = table if table is not None else rites(g)
    shown = (lambda r: book.display(r.rite_type) if r.rite_type else None) if book else (lambda r: None)
    return t[_find("rite", key, t, lambda r: (r.tag, r.name, r.rite_type, shown(r)), book=book,
                   label=lambda i: f"{rite_name(t[i], book) or '?'} ({i})")]


def holy_site_name(typ: str, book: NameBook | None = None) -> str:
    """The name the game shows for a holy site type (Ise Jingū), or the type itself without a game folder."""
    return (book.display(f"holy_site_{typ}_name") if book else None) or typ


def find_holy_site(g: bytes, key: str, table: dict | None = None, *, book: NameBook | None = None,
                   prefer=None) -> str:
    """A holy site's id by id, type ("ise_jingu") or the name the game shows ("Ise Jingu", "Ise Jingū"). `prefer`:
    ids tried first when a name is shared (Carthage, Toledo and Dwin each name two sites, measured 2026-11-17)."""
    t = table if table is not None else holy_sites(g)
    shown = (lambda typ: book.display(f"holy_site_{typ}_name")) if book else (lambda typ: None)
    return _find("holy site", key, t, lambda typ: (typ, shown(typ)), prefer=prefer, book=book,
                 label=lambda i: f"{holy_site_name(t[i], book)} ({t[i]}, {i})")


def religion_doctrines(g: bytes, religion: str, table: dict | None = None) -> set[str]:
    """The doctrines every faith of `religion` carries: the religion's own (a faith of it cannot drop them), as the save
    shows them (all 20 Christian faiths carry special_doctrine_is_christian_faith, measured 2026-11-16)."""
    t = table if table is not None else faiths(g)
    sets = [set(f.doctrines) for f in t.values() if f.religion == religion and f.doctrines]
    return set.intersection(*sets) if sets else set()
