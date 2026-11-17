"""Find a character in a save: the ``character`` parameter type of the save editor.

The player names a character by id, or by name pieces: a first name, then any of a parent's first name, the house's
name, or a held title. One match is the answer. Several are refused with the candidates listed (id, sex, age, house,
parents, titles), and none is refused too: the resolver never guesses (the ruling of 2026-11-08, item 5).

A child's own entry names no parents: they are found through the parents' ``child={ }`` lists, over the living and
the dead kept in the save (finding 2026-11-09__01-52-22; Conchenn nic Bruide is 78307, one of 30 living Conchenns).

Design: 2026-11-06__21-37-30__dev-workflow-process__save-edits-front-door.md (addendum 2026-11-09 02:51, U8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cached_property

from . import translate as T
from .names import norm

# Words in a name that narrow nothing: patronymic and locative particles ("Conchenn nic Bruide", "Ragnar of Uppland").
PARTICLES = frozenset({"nic", "mac", "ni", "ua", "ap", "ferch", "verch", "of", "de", "di", "da", "du", "von", "van",
                       "the", "son", "daughter", "bin", "bint", "ibn", "ben", "bat", "al", "el"})
CANDIDATES_SHOWN = 50

_DATE = re.compile(rb"(?m)^date=(\d+)\.(\d+)\.(\d+)")
_CHILD = re.compile(rb"(?m)^\t\tchild=\{([^}]*)\}")
_FEMALE = re.compile(rb"(?m)^\tfemale=yes\r?$")
_HOLDER = re.compile(rb"(?m)^\tholder=(\d+)")


class CharacterError(ValueError):
    """No character, or more than one, answers to what the player gave: the message lists what to do."""


def _field(body: bytes, key: bytes) -> str:
    m = re.search(rb"(?m)^\t" + key + rb'=("?)([^"\r\n]*)\1', body)
    return m.group(2).decode("utf-8", "replace") if m else ""


def _ymd(text: str) -> tuple[int, int, int] | None:
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


@dataclass(frozen=True)
class Character:
    id: int
    first_name: str
    female: bool
    birth: str
    age: int | None
    house_id: str
    house: str                   # the house's name or key, "" when the save gives neither
    father: int | None
    mother: int | None
    titles: tuple = ()           # keys of the titles held
    open: int = 0                # the entry's "{" and "}" in the gamestate
    close: int = 0


class CharacterIndex:
    """Lazy lookups over one gamestate: the living by id, everyone's first name, parents, houses, title holders.

    A first name, a house name and a title in a save are localisation keys (Gabrán is stored as ``GabrA_n``; 1,919
    of the founding save's 21,544 distinct first names carry that escape). With a ``book`` (names.NameBook) a query
    may use the names the game shows ("Gabrán", "Gabran") and descriptions print them; without one, the keys still
    match, folded the same way (``GabrA_n`` and "Gabran" both fold to "gabran"). Measured 2026-11-17: 21,487 of
    21,544 first names, 16,979 of 17,302 house names and 10,997 of 11,647 held titles have an English name.
    """

    def __init__(self, gamestate: bytes, book=None):
        self.g = gamestate
        self.book = book

    def shown(self, key: str) -> str:
        """The name the game shows for a key (a first name, a house name, a title), or the key itself."""
        return (self.book.display(key) if self.book and key else None) or key

    def _forms(self, key: str, prefixed: bool = False) -> set:
        """The folded forms a key answers to: itself, the name the game shows, and for a house or a title the key
        without its prefix ("dynn_Orsini" and "c_tara" answer to "Orsini" and "tara")."""
        if not key:
            return set()
        out = {norm(key), norm(self.shown(key))}
        if prefixed:
            out.add(norm(key.split("_", 1)[-1]))
        out.discard("")
        return out

    @cached_property
    def first_name_index(self) -> dict:
        """folded first-name form -> ids of the living with that first name."""
        out: dict = {}
        forms: dict = {}
        for cid, e in self.living.items():
            fn = _field(self.g[e.open:e.close], b"first_name")
            if fn not in forms:
                forms[fn] = self._forms(fn)
            for f in forms[fn]:
                out.setdefault(f, []).append(cid)
        return out

    @cached_property
    def date(self) -> tuple[int, int, int] | None:
        m = _DATE.search(self.g)
        return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None

    @cached_property
    def living(self) -> dict:
        return dict(T.entries(self.g, "living"))

    @cached_property
    def dead(self) -> dict:
        return dict(T.entries(self.g, "dead_unprunable"))

    @cached_property
    def first_names(self) -> dict[int, str]:
        out = {}
        for space in (self.dead, self.living):
            for i, e in space.items():
                out[i] = _field(self.g[e.open:e.close], b"first_name")
        return out

    @cached_property
    def parents(self) -> dict[int, tuple[int | None, int | None]]:
        """child id -> (father, mother), from every kept character's ``child={ }`` list."""
        out: dict[int, list] = {}
        for space in (self.living, self.dead):
            for i, e in space.items():
                body = self.g[e.open:e.close]
                m = _CHILD.search(body)
                if not m:
                    continue
                slot = 1 if _FEMALE.search(body) else 0
                for c in m.group(1).split():
                    if c.isdigit():
                        out.setdefault(int(c), [None, None])[slot] = i
        return {k: (v[0], v[1]) for k, v in out.items()}

    @cached_property
    def houses(self) -> dict[str, str]:
        out = {}
        for i, e in T.entries(self.g, "dynasties/dynasty_house"):
            body = self.g[e.open:e.close]
            out[str(i)] = _field(body, b"name") or _field(body, b"key")
        return out

    @cached_property
    def titles(self) -> dict[int, list[str]]:
        out: dict[int, list[str]] = {}
        for _, e in T.entries(self.g, "landed_titles/landed_titles"):
            body = self.g[e.open:e.close]
            h = _HOLDER.search(body)
            key = _field(body, b"key")
            if h and key:
                out.setdefault(int(h.group(1)), []).append(key)
        return out

    def character(self, cid: int) -> Character | None:
        e = self.living.get(cid)
        if e is None:
            return None
        body = self.g[e.open:e.close]
        birth = _field(body, b"birth")
        b, d = _ymd(birth), self.date
        age = (d[0] - b[0] - ((d[1], d[2]) < (b[1], b[2]))) if (b and d) else None
        house = _field(body, b"dynasty_house")
        father, mother = self.parents.get(cid, (None, None))
        return Character(cid, _field(body, b"first_name"), bool(_FEMALE.search(body)), birth, age, house,
                         self.houses.get(house, ""), father, mother, tuple(self.titles.get(cid, ())), e.open, e.close)

    def describe(self, c: Character) -> str:
        """One candidate line: id, sex, age, house, parents, titles."""
        def parent(p):
            return f"{p} {self.shown(self.first_names.get(p, '')) or '?'}" if p is not None else "-"
        house = f"{c.house_id} {self.shown(c.house)}".strip() if c.house_id else "-"
        titles = ", ".join(self.shown(t) for t in c.titles) or "-"
        age = f"age {c.age}" if c.age is not None else "age ?"
        return (f"{c.id:>10}  {self.shown(c.first_name)} ({'F' if c.female else 'M'}, {age}, born {c.birth or '?'})  "
                f"house {house}  father {parent(c.father)}  mother {parent(c.mother)}  titles {titles}")

    def _narrowers(self, c: Character) -> set:
        """The folded names that narrow a query to `c`: a parent's first name, the house, a title."""
        out: set = set()
        for p in (c.father, c.mother):
            if p is not None:
                out |= self._forms(self.first_names.get(p, ""))
        for key in (c.house, *c.titles):
            out |= self._forms(key, prefixed=True)
        return out

    @staticmethod
    def _covered(words: list[str], forms: set) -> bool:
        """Whether `words` can be cut into runs that each name something in `forms` ("Ui Neill" is one run for the
        house "Uí Néill"): the grouping of the generic parser's longest-match, where any covering reading counts."""
        n = len(words)
        ok = [False] * n + [True]
        for i in range(n - 1, -1, -1):
            ok[i] = any(ok[j] and norm(" ".join(words[i:j])) in forms for j in range(i + 1, n + 1))
        return ok[0]

    def find(self, text: str) -> list[Character]:
        """The living characters answering to ``text``: an id, or a first name and narrowing words. The first name
        is one word or more ("Iomaíocht Máel-Mórda"), the narrowing words a parent's first name, the house or a title,
        each one word or more; particles ("nic", "of") are skipped; accents and case never matter."""
        pieces = text.split()
        if not pieces:
            return []
        if len(pieces) == 1 and pieces[0].isdigit():
            c = self.character(int(pieces[0]))
            return [c] if c else []
        found: dict = {}
        for k in range(1, len(pieces) + 1):
            rest = [p for p in pieces[k:] if p.lower() not in PARTICLES]
            for cid in self.first_name_index.get(norm(" ".join(pieces[:k])), ()):
                if cid in found:
                    continue
                c = self.character(cid)
                if self._covered(rest, self._narrowers(c)):
                    found[cid] = c
        return list(found.values())


def resolve_character(gamestate: bytes, text: str, index: CharacterIndex | None = None) -> Character:
    """Exactly one living character for ``text``, or a CharacterError saying what matched and how to narrow it.
    The door passes its context's index, so resolving and the edit that follows read the characters once."""
    ix = index or CharacterIndex(gamestate)
    found = ix.find(text)
    if len(found) == 1:
        return found[0]
    text = " ".join(text.split())
    if not found:
        if text.isdigit():
            raise CharacterError(f"no living character has the id {text}")
        raise CharacterError(f"no living character answers to {text!r} (a first name, then a parent's first name, "
                             "the house's name or a title held)")
    found.sort(key=lambda c: (c.age if c.age is not None else 999, c.id))
    lines = [ix.describe(c) for c in found[:CANDIDATES_SHOWN]]
    more = len(found) - CANDIDATES_SHOWN
    if more > 0:
        lines.append(f"  ... and {more} more")
    raise CharacterError(f"{text!r} matches {len(found)} living characters; give the id, or add a parent's first "
                         "name, the house's name or a title:\n" + "\n".join(lines))
