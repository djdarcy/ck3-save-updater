"""Names a player types and names the tool prints: accent folding, and output that never dies on a character.

The game's display names carry accents ("Ise Jingū", "Ásatrú", "Jórvík"); a Windows console that is piped or
redirected writes cp1252, which cannot hold some of them. Design: 2026-11-17__01-12-44__dev-workflow-process__name-
lists-and-the-games-display-names.md; goal 2026-11-17__01-24-33__goal__multi-word-names-across-the-tool.md.
"""
from __future__ import annotations

import codecs
import re
import sys
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

FOLD_ERRORS = "ck3fold"
SIGNS = "+-"


class NameListError(LookupError):
    """A list a player typed cannot be read: words nothing matches, or two ways to read it. The message says which."""


@dataclass
class Item:
    """One item of a list: what was typed (sign removed), its sign ("+", "-", or None, which a caller reads as add),
    and what the resolver made of it, if one was given."""
    text: str
    sign: str | None = None
    value: object = None


def norm(text: str) -> str:
    """The form names are compared in: accents off, lowercase, letters and digits only. "Ise Jingū", "ise-jingu" and
    the key "ise_jingu" all give "isejingu"; the save's own key "GabrA_n" and "Gabrán" both give "gabran"."""
    return re.sub(r"[^a-z0-9]", "", fold_accents(text).lower())


def split_qualifier(text: str) -> tuple[str | None, str]:
    """ "Pilgrimage Attitude: Encouraged" -> ("Pilgrimage Attitude", "Encouraged"); text without a colon -> (None,
    text). What a qualifier means (a doctrine's group, say) is the resolver's business."""
    if ":" in text:
        q, n = text.split(":", 1)
        return (q.strip() or None), n.strip()
    return None, text.strip()


def _chunks(text: str, modifiers: bool) -> tuple[list[str], bool]:
    """The list's items as typed, and whether they came from explicit boundaries (commas, or signs) rather than
    from single words."""
    if "," in text:
        return [c.strip() for c in text.split(",") if c.strip()], True
    words = text.split()
    if modifiers and any(w[0] in SIGNS for w in words):
        out: list[str] = []
        for w in words:
            if w[0] in SIGNS or not out:
                out.append(w)
            else:
                out[-1] += " " + w
        return out, True
    return words, False


def _group(words: list[str], resolve) -> list:
    """Every way of cutting `words` into runs that `resolve` accepts; exactly one is returned as (text, value) pairs,
    else NameListError names the uncovered words or the competing readings."""
    n = len(words)

    @lru_cache(maxsize=None)
    def span(i: int, j: int):
        try:
            return True, resolve(" ".join(words[i:j]))
        except LookupError:
            return False, None

    @lru_cache(maxsize=None)
    def parses(i: int) -> tuple:              # at most two readings of words[i:], each a tuple of (i, j) spans
        if i == n:
            return ((),)
        out = []
        for j in range(n, i, -1):             # longer runs first, so the first reading is the longest-first one
            if span(i, j)[0]:
                out += [((i, j),) + rest for rest in parses(j)]
                if len(out) > 1:
                    break
        return tuple(out[:2])

    found = parses(0)
    if not found:
        covered = {k for i in range(n) for j in range(i + 1, n + 1) if span(i, j)[0] for k in range(i, j)}
        missing = [w for k, w in enumerate(words) if k not in covered]
        raise NameListError(f"nothing answers to {', '.join(repr(w) for w in missing)}" if missing else
                            f"{' '.join(words)!r} cannot be read as names; separate them with commas")
    if len(found) > 1:
        readings = [" | ".join(" ".join(words[i:j]) for i, j in p) for p in found]
        raise NameListError(f"{' '.join(words)!r} can be read more than one way ({'; '.join(readings)}); "
                            "separate the names with commas")
    return [(" ".join(words[i:j]), span(i, j)[1]) for i, j in found[0]]


def parse_list(text: str, *, resolve=None, longest: bool = False, modifiers: bool = False) -> list[Item]:
    """A list a player typed, read one generic way for the whole tool.

    - With a comma, the items are the comma-separated parts ("Bodh Gaya, Jerusalem, Iona").
    - Otherwise, with ``modifiers`` and a word starting with + or -, each such word starts an item
      ("+Christian Syncretism -Jewish Syncretism"); otherwise each word is an item ("jerusalem rome iona").
    - ``modifiers``: a leading + or - is taken off into ``Item.sign`` (no sign means add, as in --rules).
    - ``resolve(text) -> value`` (raising LookupError for "no") fills ``Item.value``; its error propagates.
    - ``longest`` (needs ``resolve``): words are grouped into the runs the resolver accepts, trying every grouping;
      one reading wins, and none or several is refused (NameListError). Within commas it groups each part.
    Design: 2026-11-17__01-57-40__dev-workflow-process__one-grammar-for-names-across-the-tool.md.
    """
    if longest and resolve is None:
        raise ValueError("parse_list: longest needs a resolver")
    chunks, bounded = _chunks(text.strip(), modifiers)
    items: list[Item] = []
    if longest and not bounded:
        chunks = [" ".join(chunks)] if chunks else []
    for c in chunks:
        sign = None
        if modifiers and c[0] in SIGNS:
            sign, c = c[0], c[1:].strip()
        if not c:
            raise NameListError(f"a {sign} with no name after it")
        if longest:
            items += [Item(t, sign, v) for t, v in _group(c.split(), resolve)]
        else:
            items.append(Item(c, sign, resolve(c) if resolve else None))
    return items


def fold_accents(text: str) -> str:
    """The same text with accents taken off the letters: "Ise Jingū" -> "Ise Jingu", "Ásatrú" -> "Asatru".
    Letters with no plain form (伊勢, ß) are kept as they are."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _fold_handler(err: UnicodeEncodeError):
    """Codec error handler: what an encoding cannot hold is written accent-folded, and as '?' when even that fails."""
    out = []
    for c in fold_accents(err.object[err.start:err.end]):
        try:
            c.encode(err.encoding)
            out.append(c)
        except (UnicodeEncodeError, LookupError):
            out.append("?")
    return "".join(out), err.end


codecs.register_error(FOLD_ERRORS, _fold_handler)


def safe_output(*streams) -> None:
    """Make each text stream (stdout and stderr by default) write accent-folded text instead of raising when its
    encoding cannot hold a character. An interactive Windows console, which takes any character, is unchanged in
    effect; a pipe or a redirect in cp1252 gets "Shinto Way" where it would have crashed on "Shintō Way"."""
    for s in streams or (sys.stdout, sys.stderr):
        # a Windows pipe measured 2026-11-17: cp1252 with errors="surrogateescape", which still raises on a real
        # character the encoding lacks (it only round-trips undecodable bytes)
        if getattr(s, "errors", None) in ("strict", "surrogateescape") and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(errors=FOLD_ERRORS)
            except (ValueError, OSError):       # a stream that cannot be reconfigured keeps its behaviour
                pass
