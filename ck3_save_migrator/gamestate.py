"""Locate, iterate and edit a CK3 gamestate as raw bytes -- no full parse, no copies of 222 MB.

The gamestate is Paradox "Clausewitz" text: ``key=value``, ``key={ ... }``, anonymous
``{ ... }`` list items, quoted strings with backslash escapes. This module works on
byte offsets into that text:

* ``find_section`` / ``find_sections`` -- top-level ``key={`` blocks. Measured on the
  1.8.1 and 1.20 saves: every non-numeric key at column 0 is top-level, and a
  top-level key may repeat (``triggered_event`` appears 2,123-12,293 times), so
  the plural form exists.
* ``find_child`` -- a named block at depth 0 of another block's body (the guard that
  keeps a ``faiths={ 0 }`` id list inside ``religions`` from being mistaken for the
  ``faiths`` database).
* ``iter_entries`` -- the direct child blocks of a body, keyed (``123={``) or
  anonymous (``{``), lazily: a 125 MB ``living`` section streams.
* ``iter_children`` -- every direct child of a (small) body, scalars included, with
  exact key and value spans; the basis of the edits.
* ``EditPass`` -- delete a key and its value (line-aware), rename a key token, insert
  bytes at a block's start or end. Edits are collected with the rule that made
  them and applied in one splice; everything outside them stays byte-identical.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

# braces and whole quoted strings (escapes honoured); everything else is skipped in C
_BRACE_OR_STRING = re.compile(rb'[{}]|"(?:[^"\\]|\\.)*"')
# full tokens: quoted string, a structural char, or a bare word
_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}=]|[^\s{}="]+')
# bare words that prefix a block value: color=rgb { 1 2 3 }
_VALUE_PREFIXES = {b"rgb", b"hsv", b"hsv360", b"LIST"}
_WS = b" \t\r\n"


class GamestateError(ValueError):
    """The bytes do not have the structure an operation expected."""


@dataclass(frozen=True)
class Block:
    """A ``key={...}`` or anonymous ``{...}`` block. Offsets index the gamestate bytes."""
    key: bytes | None   # None for an anonymous list item
    start: int          # start of the key token, or of "{" when anonymous
    open: int           # index of "{"
    close: int          # index of the matching "}"

    @property
    def end(self) -> int:
        return self.close + 1

    @property
    def body(self) -> tuple[int, int]:
        return self.open + 1, self.close


@dataclass(frozen=True)
class Child:
    """A direct child of a body: ``key=value``, ``key={...}``, ``{...}``, or a bare list value."""
    key: bytes | None   # None for an anonymous block or a bare value; b"" for "=value"
    key_start: int      # start of the key token (or of the value when key is None)
    key_end: int
    value_start: int
    value_end: int      # exclusive
    block: Block | None  # set when the value is (or ends in) a {...} block

    @property
    def start(self) -> int:
        return self.key_start

    @property
    def end(self) -> int:
        return self.value_end


# --------------------------------------------------------------------------- #
# scanning
# --------------------------------------------------------------------------- #
def match_brace(data: bytes, open_pos: int, limit: int | None = None) -> int:
    """Index of the "}" matching the "{" at ``open_pos``, skipping quoted strings."""
    if data[open_pos:open_pos + 1] != b"{":
        raise GamestateError(f"no '{{' at offset {open_pos}")
    depth = 0
    end = len(data) if limit is None else limit
    for m in _BRACE_OR_STRING.finditer(data, open_pos, end):
        t = m.group()
        if t == b"{":
            depth += 1
        elif t == b"}":
            depth -= 1
            if depth == 0:
                return m.start()
    raise GamestateError(f"unbalanced '{{' at offset {open_pos}")


def _key_before(data: bytes, open_pos: int, floor: int) -> tuple[bytes | None, int]:
    """The key of a block whose "{" is at ``open_pos``: (key, key_start) or (None, open_pos)."""
    i = open_pos - 1
    while i >= floor and data[i] in _WS:
        i -= 1
    if i < floor or data[i] != 0x3D:  # "="
        return None, open_pos
    i -= 1
    while i >= floor and data[i] in b" \t":
        i -= 1
    end = i + 1
    while i >= floor and data[i] not in _WS and data[i] not in b"{}=":
        i -= 1
    return data[i + 1:end], i + 1


def iter_entries(data: bytes, start: int, end: int) -> Iterator[Block]:
    """Yield the direct child blocks of the body ``data[start:end]``, lazily.

    Keyed (``id={``) and anonymous (``{``) blocks both; scalar children are skipped.
    Copes with the game's ``}\\n {`` list layout and with braces inside strings.
    """
    depth = 0
    open_pos = -1
    for m in _BRACE_OR_STRING.finditer(data, start, end):
        t = m.group()
        if t == b"{":
            if depth == 0:
                open_pos = m.start()
            depth += 1
        elif t == b"}":
            depth -= 1
            if depth == 0:
                key, key_start = _key_before(data, open_pos, start)
                yield Block(key, key_start, open_pos, m.start())
            elif depth < 0:
                raise GamestateError(f"unbalanced '}}' at offset {m.start()}")
    if depth != 0:
        raise GamestateError(f"unclosed '{{' at offset {open_pos}")


_TOP_INDEX: list[tuple[bytes, dict[bytes, list[Block]] | None]] = []   # the last few gamestates' sections


def _top_index(data: bytes) -> dict[bytes, list[Block]] | None:
    """key -> top-level blocks, from one walk that jumps from each section's end to the next (a 220 MB gamestate
    was being rescanned once per lookup: 174 lookups, 148 of a transplant's 217 seconds). None when a section
    does not close (the caller then scans the old way). Cached for the last 4 gamestates, by identity."""
    for d, idx in _TOP_INDEX:
        if d is data:
            return idx
    idx: dict[bytes, list[Block]] | None = {}
    pos = 0
    while (m := _TOP_KEY.search(data, pos)) is not None:
        op = m.end() - 1
        try:
            close = match_brace(data, op)
        except GamestateError:
            idx = None
            break
        idx.setdefault(m.group(1), []).append(Block(m.group(1), m.start(), op, close))
        pos = close + 1
    _TOP_INDEX.insert(0, (data, idx))
    del _TOP_INDEX[4:]
    return idx


def find_sections(data: bytes, key: str | bytes) -> Iterator[Block]:
    """Every top-level ``key={`` block, in file order (top-level keys may repeat)."""
    k = key.encode() if isinstance(key, str) else key
    idx = _top_index(data)
    if idx is not None:
        yield from idx.get(k, [])
        return
    for m in re.finditer(rb"(?m)^" + re.escape(k) + rb"[ \t]*=[ \t]*\{", data):
        open_pos = m.end() - 1
        yield Block(k, m.start(), open_pos, match_brace(data, open_pos))


def find_section(data: bytes, key: str | bytes) -> Block:
    """The first top-level ``key={`` block; GamestateError if absent."""
    for b in find_sections(data, key):
        return b
    raise GamestateError(f"top-level section {key!r} not found")


def find_child(data: bytes, parent: Block, key: str | bytes) -> Block:
    """The first block named ``key`` at depth 0 of ``parent``'s body; GamestateError if absent."""
    k = key.encode() if isinstance(key, str) else key
    for b in iter_entries(data, *parent.body):
        if b.key == k:
            return b
    raise GamestateError(f"child block {k!r} not found at depth 0 of {parent.key!r}")


def locate(data: bytes, path: str) -> Block:
    """``"landed_titles/landed_titles"`` -> the inner block; the first component is top-level."""
    parts = path.split("/")
    block = find_section(data, parts[0])
    for p in parts[1:]:
        block = find_child(data, block, p)
    return block


def iter_children(data: bytes, start: int, end: int) -> Iterator[Child]:
    """Yield every direct child of the body ``data[start:end]`` with exact spans.

    Tokenises the whole body, so use it on entry-sized bodies (a character, a
    title), not on a 125 MB section -- ``iter_entries`` is the streaming form.
    """
    toks = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(data, start, end)]
    n = len(toks)
    i = 0

    def skip_block(j: int) -> int:
        """toks[j] is "{": index of its matching "}" token."""
        depth = 0
        while j < n:
            t = toks[j][2]
            if t == b"{":
                depth += 1
            elif t == b"}":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        raise GamestateError(f"unclosed '{{' at offset {toks[-1][0] if toks else start}")

    while i < n:
        s, e, t = toks[i]
        if t == b"}":
            raise GamestateError(f"unbalanced '}}' at offset {s}")
        if t == b"{":                                   # anonymous block
            j = skip_block(i)
            blk = Block(None, s, s, toks[j][0])
            yield Child(None, s, s, s, toks[j][1], blk)
            i = j + 1
            continue
        if t == b"=":                                   # "=value" with an empty key
            key, ks, ke, vi = b"", s, s, i + 1
        elif i + 1 < n and toks[i + 1][2] == b"=":
            key, ks, ke, vi = t, s, e, i + 2
        else:                                           # bare list value
            yield Child(None, s, s, s, e, None)
            i += 1
            continue
        if vi >= n:
            raise GamestateError(f"key {key!r} at offset {ks} has no value")
        vs, ve, vt = toks[vi]
        if vt == b"{":
            j = skip_block(vi)
            yield Child(key, ks, ke, vs, toks[j][1], Block(key, ks, vs, toks[j][0]))
            i = j + 1
        elif vt in _VALUE_PREFIXES and vi + 1 < n and toks[vi + 1][2] == b"{":
            j = skip_block(vi + 1)
            yield Child(key, ks, ke, vs, toks[j][1], Block(key, ks, toks[vi + 1][0], toks[j][0]))
            i = j + 1
        else:
            yield Child(key, ks, ke, vs, ve, None)
            i = vi + 1


_TOP_KEY = re.compile(rb"(?m)^([A-Za-z_][\w.]*)[ \t]*=[ \t]*\{")


_SMALL_BLOCK = 256 * 1024   # bodies up to this size are tokenised; larger ones are streamed


def child_at(data: bytes, positions: list[int]) -> dict[int, tuple[Block, Child]]:
    """For each offset that is the start of a child (``key=``, ``=value``...), its (parent block, child).

    Resolves all offsets in grouped passes: each block is scanned once for every
    offset inside it -- tokenised with ``iter_children`` when its body is small,
    streamed with ``iter_entries`` when large, the offsets handed down to the child
    block that contains them. Work is proportional to the bytes scanned, not to
    bytes x offsets (the first version re-tokenised a 6 MB ``artifacts`` entry once
    per offset and ran for hours on the 1.8.1 save). Offsets that are not a child
    start (inside a string, mid value) are absent from the result; so are scalar
    children at depth 0 of a block larger than 256 KB, which a stream cannot see.
    """
    wanted = sorted(set(positions))
    if not wanted:
        return {}
    out: dict[int, tuple[Block, Child]] = {}

    def resolve(block: Block, poss: list[int]) -> None:
        if block.close - block.open <= _SMALL_BLOCK:
            i = 0
            for c in iter_children(data, *block.body):
                while i < len(poss) and poss[i] < c.start:
                    i += 1                                   # between children: not a child start
                if i >= len(poss):
                    return
                inner = []
                while i < len(poss) and poss[i] < c.end:
                    p = poss[i]
                    if p == c.key_start:
                        out[p] = (block, c)
                    elif c.block is not None and c.block.open < p < c.block.close:
                        inner.append(p)
                    i += 1
                if inner:
                    resolve(c.block, inner)
            return
        i = 0
        for e in iter_entries(data, *block.body):
            while i < len(poss) and poss[i] < e.start:
                i += 1                                       # depth-0 scalar of a large block: not seen
            if i >= len(poss):
                return
            inner = []
            while i < len(poss) and poss[i] < e.end:
                p = poss[i]
                if p == e.start and e.key is not None:       # the entry's own key
                    out[p] = (block, Child(e.key, e.start, e.start + len(e.key), e.open, e.end, e))
                elif e.open < p < e.close:
                    inner.append(p)
                i += 1
            if inner:
                resolve(e, inner)

    tops = [(m.group(1), m.start(), m.end() - 1) for m in _TOP_KEY.finditer(data)]
    j = 0
    by_section: dict[int, list[int]] = {}
    for pos in wanted:
        while j + 1 < len(tops) and tops[j + 1][1] <= pos:
            j += 1
        if tops and tops[j][1] <= pos:
            by_section.setdefault(j, []).append(pos)
    for idx, poss in by_section.items():
        key, key_start, open_pos = tops[idx]
        section = Block(key, key_start, open_pos, match_brace(data, open_pos))
        inside = [p for p in poss if section.open < p < section.close]
        if inside:
            resolve(section, inside)
    return out


def parent_cycles(parent: dict) -> list[list]:
    """Every cycle of a parent map (each node has at most one parent), a self-parent included. A walk up such a
    chain ends only at a node with no parent; on a cycle it never ends (the 8 November 987 freeze, 2026-10-27)."""
    state, found = {}, []
    for start in parent:
        if start in state:
            continue
        path, pos, n = [], {}, start
        while n in parent and n not in state:
            state[n] = 1
            pos[n] = len(path)
            path.append(n)
            n = parent[n]
        if n in pos:
            found.append(path[pos[n]:])
        for p in path:
            state[p] = 2
    return found


def find_keys(data: bytes, parent: Block, key: str | bytes) -> list[Child]:
    """Children of ``parent`` named ``key`` at depth 0 (repeats included, e.g. spouse=)."""
    k = key.encode() if isinstance(key, str) else key
    return [c for c in iter_children(data, *parent.body) if c.key == k]


# --------------------------------------------------------------------------- #
# edits
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: bytes
    rule: str
    note: str = ""


@dataclass
class RuleCount:
    matched: int = 0    # entries the rule looked at and found applicable
    edited: int = 0     # edits the rule produced


def removal_span(data: bytes, start: int, end: int) -> tuple[int, int]:
    """Widen ``[start, end)`` so deleting it leaves tidy text.

    Alone on its line: take the whole line, newline included. First on a line with
    more after it: take the trailing spaces/tabs too. After other content: take the
    leading spaces/tabs instead.
    """
    line_start = data.rfind(b"\n", 0, start) + 1
    nl = data.find(b"\n", end)
    line_end = len(data) if nl < 0 else nl
    before_blank = data[line_start:start].strip(b" \t") == b""
    after_blank = data[end:line_end].strip(b" \t\r") == b""
    if before_blank and after_blank:
        return line_start, (line_end + 1 if nl >= 0 else line_end)
    if before_blank:
        j = end
        while j < line_end and data[j] in b" \t":
            j += 1
        return start, j
    i = start
    while i > line_start and data[i - 1] in b" \t":
        i -= 1
    return i, end


@dataclass
class EditPass:
    """Edits collected from one pass of rules, applied together in one splice."""
    edits: list[Edit] = field(default_factory=list)
    counts: dict[str, RuleCount] = field(default_factory=dict)

    def count(self, rule: str) -> RuleCount:
        return self.counts.setdefault(rule, RuleCount())

    def add(self, edit: Edit) -> None:
        self.edits.append(edit)
        self.count(edit.rule).edited += 1

    # -- the three primitives ------------------------------------------------
    def delete_key(self, data: bytes, parent: Block, key: str | bytes, rule: str, note: str = "") -> int:
        """Delete every depth-0 ``key=value`` / ``key={...}`` in ``parent``, line-aware. Returns the count."""
        hits = find_keys(data, parent, key)
        for c in hits:
            s, e = removal_span(data, c.start, c.end)
            self.add(Edit(s, e, b"", rule, note))
        return len(hits)

    def delete_block(self, data: bytes, block: Block, rule: str, note: str = "") -> None:
        """Delete a whole block (an entry from ``iter_entries``), line-aware."""
        s, e = removal_span(data, block.start, block.end)
        self.add(Edit(s, e, b"", rule, note))

    def rename_key(self, data: bytes, parent: Block, old: str | bytes, new: str | bytes, rule: str,
                   note: str = "") -> int:
        """Rename the key token of every depth-0 ``old=`` in ``parent``. Returns the count."""
        n = new.encode() if isinstance(new, str) else new
        hits = find_keys(data, parent, old)
        for c in hits:
            self.add(Edit(c.key_start, c.key_end, n, rule, note))
        return len(hits)

    def insert(self, block: Block, position: str, payload: bytes, rule: str, note: str = "") -> None:
        """Insert ``payload`` just inside ``block``: ``position`` is "start" (after "{") or "end" (before "}")."""
        if position == "start":
            at = block.open + 1
        elif position == "end":
            at = block.close
        else:
            raise ValueError(f"position must be 'start' or 'end', not {position!r}")
        self.add(Edit(at, at, payload, rule, note))

    # -- application ----------------------------------------------------------
    def ordered(self) -> list[Edit]:
        """Edits in file order (stable for inserts at one offset); GamestateError on overlap."""
        eds = sorted(self.edits, key=lambda e: (e.start, e.end))
        prev = None
        for e in eds:
            if e.end < e.start:
                raise GamestateError(f"edit with end before start: {e}")
            if prev is not None and e.start < prev.end:
                raise GamestateError(f"overlapping edits: {prev.rule} {prev.start}:{prev.end} and "
                                     f"{e.rule} {e.start}:{e.end}")
            prev = e
        return eds

    def apply(self, data: bytes) -> bytes:
        """Return ``data`` with every edit applied in one pass; untouched bytes are copied unchanged."""
        pieces = []
        pos = 0
        for e in self.ordered():
            if e.end > len(data):
                raise GamestateError(f"edit {e.start}:{e.end} beyond the data ({len(data)} bytes)")
            pieces.append(data[pos:e.start])
            pieces.append(e.replacement)
            pos = e.end
        pieces.append(data[pos:])
        return b"".join(pieces)

    def apply_to(self, save) -> None:
        """Apply to a ``savefile.CK3Save``'s gamestate and log the edits on it.

        The plaintext meta block is re-derived from the gamestate when the save is
        written, so edits inside ``meta_data`` update both copies.
        """
        from .savefile import Edit as SaveEdit
        ordered = self.ordered()
        save.set_gamestate(self.apply(save.gamestate))
        save.edits.extend(SaveEdit(e.start, e.end, len(e.replacement)) for e in ordered)
