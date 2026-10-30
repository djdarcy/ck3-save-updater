"""Read the game's history files (``game/history/characters`` and ``game/history/titles``) as of a date.

The files are Paradox script: ``key = value`` pairs, ``{ }`` blocks, quoted strings and ``#`` comments, in UTF-8
(usually with a byte-order mark). A history entry has plain fields (``name``, ``culture``, ``religion``,
``dynasty_house``, ``female``) and dated blocks, ``<y.m.d> = { ... }``, that change them on that date; the last
value at or before a date is the value on it. A character is born and dies in dated blocks (``birth = yes``,
``death = yes`` or ``death = { ... }``); older files also write ``birth = "<date>"`` and ``death = "<date>"``. A
title's dated blocks set its ``holder`` (``0`` means no holder) and sometimes its ``government``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

Date = tuple[int, int, int]
_DATE = re.compile(r"^(-?\d{1,4})\.(\d{1,2})\.(\d{1,2})$")
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|#[^\n]*|([{}])|(<=|>=|!=|\?=|==|=|<|>)|([^\s{}=<>!?"#]+)')


def as_date(text: str | None) -> Date | None:
    m = _DATE.match((text or "").strip().strip('"'))
    return tuple(int(x) for x in m.groups()) if m else None


# --------------------------------------------------------------------------- the script reader
def parse(text: str) -> list:
    """Paradox script as a list of ``(key, value)``: ``value`` is a string, or a list of the same for a block.
    A bare item of a block (``{ a b }``) is ``(None, "a")``. Comparison operators are read as ``=``. Unbalanced
    braces end the read without raising: what was read is kept."""
    tokens = []
    for m in _TOKEN.finditer(text.lstrip("﻿")):
        if m.group(1) is not None:
            tokens.append(("s", m.group(1)))
        elif m.group(2):
            tokens.append((m.group(2), None))
        elif m.group(3):
            tokens.append(("=", None))
        elif m.group(4):
            tokens.append(("s", m.group(4)))
    pos = 0

    def block() -> list:
        nonlocal pos
        out = []
        while pos < len(tokens):
            kind, val = tokens[pos]
            if kind == "}":
                pos += 1
                return out
            if kind == "{":
                pos += 1
                out.append((None, block()))
                continue
            if kind == "=":                        # a stray operator
                pos += 1
                continue
            pos += 1
            if pos < len(tokens) and tokens[pos][0] == "=":
                pos += 1
                if pos < len(tokens) and tokens[pos][0] == "{":
                    pos += 1
                    out.append((val, block()))
                elif pos < len(tokens) and tokens[pos][0] == "s":
                    out.append((val, tokens[pos][1]))
                    pos += 1
            else:
                out.append((None, val))
        return out

    return block()


def read_folder(folder: Path) -> list:
    """Every ``.txt`` file of ``folder`` parsed and joined, in file-name order (the game's load order)."""
    out = []
    for f in sorted(Path(folder).glob("*.txt")):
        out += parse(f.read_text(encoding="utf-8-sig", errors="replace"))
    return out


# --------------------------------------------------------------------------- characters
@dataclass
class Character:
    id: str
    fields: dict = field(default_factory=dict)             # the undated fields
    events: list = field(default_factory=list)             # (date, [(key, value)]) in file order
    birth: Date | None = None
    death: Date | None = None

    def as_of(self, date: Date) -> dict:
        """The fields on ``date``: the undated ones, then every dated block at or before it, in date order."""
        out = dict(self.fields)
        for d, pairs in sorted((e for e in self.events if e[0] <= date), key=lambda e: e[0]):
            for k, v in pairs:
                if isinstance(v, str):
                    out[k] = v
        return out

    def alive_on(self, date: Date) -> bool:
        return self.birth is not None and self.birth <= date and (self.death is None or self.death > date)

    def age_on(self, date: Date) -> int | None:
        if self.birth is None:
            return None
        return date[0] - self.birth[0] - ((date[1], date[2]) < (self.birth[1], self.birth[2]))


def characters(folder: Path) -> dict[str, Character]:
    """The characters of ``game/history/characters``, by history id."""
    out = {}
    for cid, body in read_folder(folder):
        if cid is None or not isinstance(body, list):
            continue
        c = Character(cid)
        for k, v in body:
            d = as_date(k)
            if d is not None and isinstance(v, list):
                c.events.append((d, v))
                for kk, vv in v:
                    if kk == "birth" and c.birth is None:
                        c.birth = d
                    elif kk == "death" and c.death is None:
                        c.death = d
            elif k == "birth" and isinstance(v, str) and as_date(v):
                c.birth = as_date(v)
            elif k == "death" and isinstance(v, str) and as_date(v):
                c.death = as_date(v)
            elif k is not None and isinstance(v, str):
                c.fields[k] = v
        out[cid] = c
    return out


# --------------------------------------------------------------------------- titles
def titles(folder: Path) -> dict[str, list]:
    """The titles of ``game/history/titles``: key -> ``[(date, {"holder"?, "government"?})]`` in date order."""
    out: dict[str, list] = {}
    for key, body in read_folder(folder):
        if key is None or not isinstance(body, list):
            continue
        rows = out.setdefault(key, [])
        for k, v in body:
            d = as_date(k)
            if d is None or not isinstance(v, list):
                continue
            got = {kk: vv for kk, vv in v if kk in ("holder", "government") and isinstance(vv, str)}
            if got:
                rows.append((d, got))
        rows.sort(key=lambda r: r[0])
    return out


def as_of(rows: list, key: str, date: Date) -> str | None:
    """The last ``key`` set at or before ``date`` in a title's rows."""
    val = None
    for d, got in rows:
        if d > date:
            break
        if key in got:
            val = got[key]
    return val


def holders(title_rows: dict[str, list], date: Date) -> dict[str, list[str]]:
    """character id -> the titles they hold on ``date`` (a holder of ``0`` is no holder)."""
    out: dict[str, list[str]] = {}
    for key, rows in title_rows.items():
        h = as_of(rows, "holder", date)
        if h and h != "0":
            out.setdefault(h, []).append(key)
    return out
