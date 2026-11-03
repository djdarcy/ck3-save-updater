"""An index of every block in a gamestate, built in one pass: where each ``{`` opens and closes, and the key before it.

``paths.resolve`` uses it to find a candidate's ancestors without descending from the top-level section through
every enclosing body: the blocks that contain a position are exactly the index's open blocks at that position, so a
sweep over the sorted candidates with a stack yields each one's ancestor chain, and only its innermost block (the
parent) is then read to find the child itself. On the founding 1.8.1 save (222 MB, 4.4 M blocks) the index builds
in about 11 s and R11's 1.29 M candidates resolve in about 35 s, against about 100 s by descent (measured
2026-11-02, equal on every candidate: tests/one-offs/thinking/poc-block-index/).

The index belongs to one gamestate object. ``index_for`` keeps the last one built and rebuilds whenever it is asked
about another object, so an edit (which makes a new gamestate) can never be answered from moved positions; it is
never keyed by content or by file path.
"""

from __future__ import annotations

import re
from array import array

from .. import gamestate as gs

# a quoted string (skipped whole, so a brace inside one is not a block) or a brace
_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}]')
# the key before a "{": a token, "=", spaces and tabs, on the brace's own line and within 200 bytes of it; a value
# word the child reader treats as a block's prefix (`color=rgb { ... }`) may stand between "=" and "{", and the
# block then carries the child's key, as gamestate.iter_children gives it
_PREFIX = b"|".join(re.escape(p) for p in sorted(gs._VALUE_PREFIXES, key=len, reverse=True))
_KEY_BEFORE = re.compile(rb'([^\s{}=]+)[ \t]*=[ \t]*(?:(?:' + _PREFIX + rb')[ \t]*)?$')


class BlockIndex:
    """Every block of ``data`` in file order: ``opens``, ``closes``, and the key's span (``key_starts``,
    ``key_ends``; -1 when the block is anonymous)."""

    def __init__(self, data: bytes):
        self.data = data
        opens, closes, ks, ke = array("q"), array("q"), array("q"), array("q")
        stack: list[int] = []
        for m in _TOKEN.finditer(data):
            p = m.start()
            c = data[p]
            if c == 0x7B:                               # {
                opens.append(p)
                closes.append(-1)
                line = data.rfind(b"\n", 0, p) + 1
                k = _KEY_BEFORE.search(data, max(line, p - 200), p)
                ks.append(k.start(1) if k else -1)
                ke.append(k.end(1) if k else -1)
                stack.append(len(opens) - 1)
            elif c == 0x7D and stack:                   # }
                closes[stack.pop()] = p
        self.opens, self.closes, self.key_starts, self.key_ends = opens, closes, ks, ke
        # a "{" never closed: the descent raised on it, and so does any resolve over this index
        self.unclosed = [opens[i] for i in stack]

    def block(self, i: int) -> gs.Block:
        k0 = self.key_starts[i]
        key = self.data[k0:self.key_ends[i]] if k0 >= 0 else None
        return gs.Block(key, k0 if k0 >= 0 else self.opens[i], self.opens[i], self.closes[i])

    def enclosing(self, positions: list[int]) -> dict[int, list[int]]:
        """For each position inside at least one block: the indices of the blocks containing it, outermost first.
        One sweep over the sorted positions with a stack of the blocks open at each. Raises GamestateError, as the
        descent did, when a "{" in the gamestate is never closed."""
        if self.unclosed:
            raise gs.GamestateError(f"unbalanced '{{' at offset {self.unclosed[0]} (never closed)")
        opens, closes = self.opens, self.closes
        n, ptr = len(opens), 0
        stack: list[int] = []
        out: dict[int, list[int]] = {}
        for p in sorted(set(positions)):
            while ptr < n and opens[ptr] < p:
                while stack and closes[stack[-1]] < opens[ptr]:
                    stack.pop()
                stack.append(ptr)
                ptr += 1
            while stack and closes[stack[-1]] <= p:
                stack.pop()
            if stack:
                out[p] = list(stack)
        return out


_LAST: list = []        # [the BlockIndex built last]: one gamestate's index at a time


def index_for(data: bytes) -> BlockIndex:
    """The index of exactly this gamestate object, built once and reused while the same object is asked about."""
    if not _LAST or _LAST[0].data is not data:
        _LAST[:] = [BlockIndex(data)]
    return _LAST[0]


def forget() -> None:
    """Drop the kept index (and the gamestate it holds)."""
    _LAST.clear()
