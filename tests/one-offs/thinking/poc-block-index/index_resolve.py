"""A `**` resolver over an in-memory block index -- the POC's subject (2026-11-02), a drop-in for paths.resolve.

paths.resolve finds each candidate's ancestors by descending from the top-level section through every enclosing
body (iter_children on every ancestor: 9.4 M calls, ~100 s for R11 on the founding save). Here one pass builds an
index of every block (open, close, key span); a sweep over the sorted positions keeps a stack of the blocks that
contain the current position, which IS its ancestor chain; only the innermost block (the parent) is then scanned,
with the same child parser paths.resolve uses there, so the Child it returns is the same object shape.

The index belongs to one bytes object: `cached_for(d)` rebuilds it whenever the gamestate is a different object (a
splice makes a new one), so a stale index can never be used on moved positions. Proof-of-concept code: no error
handling beyond what the question needs.
"""

from __future__ import annotations

import re
from array import array

from ck3_save_migrator import gamestate as gs

_TOK = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}]')
_KEY_BEFORE = re.compile(rb'([^\s{}=]+)[ \t]*=[ \t]*$')
_SMALL = gs._SMALL_BLOCK


class Index:
    def __init__(self, d: bytes):
        self.d = d
        opens, closes, ks, ke = array("q"), array("q"), array("q"), array("q")
        stack: list[int] = []
        for m in _TOK.finditer(d):
            c = d[m.start()]
            if c == 0x7B:
                i = len(opens)
                opens.append(m.start()); closes.append(-1)
                ls = d.rfind(b"\n", 0, m.start()) + 1
                km = _KEY_BEFORE.search(d, max(ls, m.start() - 200), m.start())
                ks.append(km.start(1) if km else -1); ke.append(km.end(1) if km else -1)
                stack.append(i)
            elif c == 0x7D and stack:
                closes[stack.pop()] = m.start()
        self.opens, self.closes, self.ks, self.ke = opens, closes, ks, ke
        self._blocks: dict[int, gs.Block] = {}

    def block(self, i: int) -> gs.Block:
        b = self._blocks.get(i)
        if b is None:
            k0 = self.ks[i]
            key = self.d[k0:self.ke[i]] if k0 >= 0 else None
            b = gs.Block(key, k0 if k0 >= 0 else self.opens[i], self.opens[i], self.closes[i])
            self._blocks[i] = b
        return b


_CACHE: dict = {}


def cached_for(d: bytes) -> Index:
    """The index of exactly this bytes object; rebuilt when the gamestate is another object."""
    idx = _CACHE.get("idx")
    if idx is None or idx.d is not d:
        idx = Index(d)
        _CACHE["idx"] = idx
        _CACHE["builds"] = _CACHE.get("builds", 0) + 1
    return idx


def resolve(d: bytes, positions: list[int], idx: Index | None = None):
    """paths.resolve's contract: {offset that starts a child: (ancestors top-level first and parent last, child)}."""
    idx = idx or cached_for(d)
    opens, closes = idx.opens, idx.closes
    n = len(opens)
    out: dict = {}
    by_parent: dict[int, tuple[list[int], list[int]]] = {}     # parent index -> (its chain, positions)
    stack: list[int] = []
    ptr = 0
    for p in sorted(set(positions)):
        while ptr < n and opens[ptr] < p:
            while stack and closes[stack[-1]] < opens[ptr]:
                stack.pop()
            stack.append(ptr)
            ptr += 1
        while stack and closes[stack[-1]] <= p:
            stack.pop()
        if not stack:
            continue
        top = stack[-1]
        if top not in by_parent:
            by_parent[top] = (list(stack), [])
        by_parent[top][1].append(p)
    for top, (chain, poss) in by_parent.items():
        parent = idx.block(top)
        here = [idx.block(i) for i in chain]
        want = set(poss)
        if parent.close - parent.open <= _SMALL:
            for c in gs.iter_children(d, *parent.body):
                if c.key_start in want:
                    out[c.key_start] = (here, c)
        else:
            for e in gs.iter_entries(d, *parent.body):
                if e.start in want and e.key is not None:
                    out[e.start] = (here, gs.Child(e.key, e.start, e.start + len(e.key), e.open, e.end, e))
    idx._blocks.clear()          # the Block objects made for this call are not kept alive into the next rules
    return out
