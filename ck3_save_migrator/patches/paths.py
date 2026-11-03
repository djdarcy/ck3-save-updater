"""Paths through a save's tree, and finding what they address quickly on a 200 MB gamestate.

A path is segments joined by ``/``. The first names top-level sections (every one of that name: the game writes some
twice); a later name matches every child BLOCK with that key (all of them, not the first); ``*`` matches any one
child block, keyed or anonymous; ``**`` matches any depth, including none.

A path without ``**`` is walked directly, block by block (``walk``). A path with ``**`` is never walked through the
whole tree in Python: the candidates are found with a byte regex on the last thing the edit names (a block key, a
child key, a value), resolved to their place in the tree in grouped passes (``resolve``, the same method as
``gamestate.child_at``, which also records each candidate's ancestors), and kept when their ancestry matches the
path. Like ``child_at``, this does not see a scalar at depth 0 of a block larger than 256 KB.
"""

from __future__ import annotations

import re

from .. import gamestate as gs

_SMALL_BLOCK = gs._SMALL_BLOCK


def segments(path: str) -> list[str]:
    return path.split("/")


def has_globstar(path: str) -> bool:
    return "**" in segments(path)


# --------------------------------------------------------------------------- direct walk
def _top_blocks(data: bytes, name: str) -> list[gs.Block]:
    if name == "**":
        raise ValueError("'**' paths are resolved by prefilter, not walked")
    return list(gs.find_sections(data, name))


def walk(data: bytes, path: str) -> list[gs.Block]:
    """Every block a path without ``**`` addresses, in file order."""
    segs = segments(path)
    level = _top_blocks(data, segs[0])
    for seg in segs[1:]:
        nxt = []
        want = seg.encode()
        for b in level:
            for e in gs.iter_entries(data, *b.body):
                if seg == "*" or e.key == want:
                    nxt.append(e)
        level = nxt
    return level


# --------------------------------------------------------------------------- ancestry match
def matches(pattern: list[str], chain: list[bytes | None]) -> bool:
    """Does a chain of block keys (top-level section first) fit the pattern? ``*`` is one block, ``**`` any depth."""
    memo: dict = {}

    def go(i: int, j: int) -> bool:
        if (i, j) in memo:
            return memo[(i, j)]
        if i == len(pattern):
            r = j == len(chain)
        elif pattern[i] == "**":
            r = go(i + 1, j) or (j < len(chain) and go(i, j + 1))
        elif j == len(chain):
            r = False
        elif pattern[i] == "*":
            r = go(i + 1, j + 1)
        else:
            r = chain[j] == pattern[i].encode() and go(i + 1, j + 1)
        memo[(i, j)] = r
        return r
    return go(0, 0)


# --------------------------------------------------------------------------- prefilter + grouped resolve
def key_regex(key: str, *, line_start: bool, block: bool = False) -> re.Pattern:
    """Candidates for a child keyed ``key`` (group 1 starts at the key; for the empty key, at the ``=``)."""
    k = re.escape(key.encode())
    tail = rb"[ \t]*=[ \t]*\{" if block else rb"[ \t]*="
    if line_start:
        return re.compile(rb"(?m)^[ \t]*(" + k + rb")" + tail)
    if not key:                                     # the empty key: the "=" itself, right after a boundary
        return re.compile(rb"(?<![^\s{}])()=" + (rb"[ \t]*\{" if block else b""))
    return re.compile(rb"(?<![^\s{}])(" + k + rb")" + tail)


def value_regex(value: str) -> re.Pattern:
    """Candidates for a bare list value equal to ``value``."""
    return re.compile(rb"(?<![^\s{}])(" + re.escape(value.encode()) + rb")(?=[\s}])")


def resolve(data: bytes, positions: list[int]) -> dict[int, tuple[list[gs.Block], gs.Child]]:
    """For each offset that starts a child: (its ancestors, top-level section first and parent last; the child).

    The ancestors come from the gamestate's block index (``blockindex``, built once per gamestate object); only each
    candidate's innermost block is read, with the same child reader ``resolve_by_descent`` uses at that depth
    (tokenised when small, streamed when large), so the answer is the same object for object."""
    from .blockindex import index_for
    idx = index_for(data)
    by_parent: dict[int, tuple[list[int], list[int]]] = {}
    for p, chain in idx.enclosing(positions).items():
        top = chain[-1]
        if top not in by_parent:
            by_parent[top] = (chain, [])
        by_parent[top][1].append(p)
    out: dict[int, tuple[list[gs.Block], gs.Child]] = {}
    for top, (chain, poss) in by_parent.items():
        here = [idx.block(i) for i in chain]
        parent, want = here[-1], set(poss)
        if parent.close - parent.open <= _SMALL_BLOCK:
            for c in gs.iter_children(data, *parent.body):
                if c.key_start in want:
                    out[c.key_start] = (here, c)
        else:
            for e in gs.iter_entries(data, *parent.body):
                if e.start in want and e.key is not None:
                    out[e.start] = (here, gs.Child(e.key, e.start, e.start + len(e.key), e.open, e.end, e))
    return out


def resolve_by_descent(data: bytes, positions: list[int]) -> dict[int, tuple[list[gs.Block], gs.Child]]:
    """``resolve`` by descending from each top-level section through every enclosing body: the resolver before the
    block index (2026-11-02), kept as the reference the index is tested against.

    Grouped passes, as in ``gamestate.child_at``: each block is scanned once for all offsets inside it, tokenised
    when small and streamed when large, so the work is proportional to the bytes scanned, not to the offsets."""
    wanted = sorted(set(positions))
    out: dict[int, tuple[list[gs.Block], gs.Child]] = {}
    if not wanted:
        return out

    def go(block: gs.Block, poss: list[int], chain: list[gs.Block]) -> None:
        here = chain + [block]
        if block.close - block.open <= _SMALL_BLOCK:
            i = 0
            for c in gs.iter_children(data, *block.body):
                while i < len(poss) and poss[i] < c.start:
                    i += 1
                if i >= len(poss):
                    return
                inner = []
                while i < len(poss) and poss[i] < c.end:
                    p = poss[i]
                    if p == c.key_start:
                        out[p] = (here, c)
                    elif c.block is not None and c.block.open < p < c.block.close:
                        inner.append(p)
                    i += 1
                if inner:
                    go(c.block, inner, here)
            return
        i = 0
        for e in gs.iter_entries(data, *block.body):
            while i < len(poss) and poss[i] < e.start:
                i += 1
            if i >= len(poss):
                return
            inner = []
            while i < len(poss) and poss[i] < e.end:
                p = poss[i]
                if p == e.start and e.key is not None:
                    out[p] = (here, gs.Child(e.key, e.start, e.start + len(e.key), e.open, e.end, e))
                elif e.open < p < e.close:
                    inner.append(p)
                i += 1
            if inner:
                go(e, inner, here)

    tops = [(m.group(1), m.start(), m.end() - 1) for m in gs._TOP_KEY.finditer(data)]
    j = 0
    by_section: dict[int, list[int]] = {}
    for pos in wanted:
        while j + 1 < len(tops) and tops[j + 1][1] <= pos:
            j += 1
        if tops and tops[j][1] <= pos:
            by_section.setdefault(j, []).append(pos)
    for idx, poss in by_section.items():
        key, key_start, open_pos = tops[idx]
        section = gs.Block(key, key_start, open_pos, gs.match_brace(data, open_pos))
        inside = [p for p in poss if section.open < p < section.close]
        if inside:
            go(section, inside, [])
    return out


def chain_keys(blocks: list[gs.Block]) -> list[bytes | None]:
    return [b.key for b in blocks]


def at_line_start(data: bytes, pos: int) -> bool:
    """Only spaces and tabs before ``pos`` on its line."""
    ls = data.rfind(b"\n", 0, pos) + 1
    return data[ls:pos].strip(b" \t") == b""
