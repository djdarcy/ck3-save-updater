"""text: read a Paradox "Clausewitz" text save as raw bytes -- locate sections and iterate entries, no full parse.

Read-only: nothing here edits a save. Lifted from the host project's gamestate reader and its section index
(see ``_VENDORED.md`` for the exact ranges and every change made after the copy).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

# braces and whole quoted strings (escapes honoured); everything else is skipped in C
_BRACE_OR_STRING = re.compile(rb'[{}]|"(?:[^"\\]|\\.)*"')
# full tokens: quoted string, a structural char, or a bare word
_TOKEN = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}=]|[^\s{}="]+')
# bare words that prefix a block value: color=rgb { 1 2 3 }
_VALUE_PREFIXES = {b"rgb", b"hsv", b"hsv360", b"LIST"}
_WS = b" \t\r\n"


class SaveTextError(ValueError):
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
        raise SaveTextError(f"no '{{' at offset {open_pos}")
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
    raise SaveTextError(f"unbalanced '{{' at offset {open_pos}")


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
                raise SaveTextError(f"unbalanced '}}' at offset {m.start()}")
    if depth != 0:
        raise SaveTextError(f"unclosed '{{' at offset {open_pos}")


def find_child(data: bytes, parent: Block, key: str | bytes) -> Block:
    """The first block named ``key`` at depth 0 of ``parent``'s body; SaveTextError if absent."""
    k = key.encode() if isinstance(key, str) else key
    for b in iter_entries(data, *parent.body):
        if b.key == k:
            return b
    raise SaveTextError(f"child block {k!r} not found at depth 0 of {parent.key!r}")


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
        raise SaveTextError(f"unclosed '{{' at offset {toks[-1][0] if toks else start}")

    while i < n:
        s, e, t = toks[i]
        if t == b"}":
            raise SaveTextError(f"unbalanced '}}' at offset {s}")
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
            raise SaveTextError(f"key {key!r} at offset {ks} has no value")
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


class SectionIndex:
    """Top-level sections found in one walk: ``top`` maps each name to its FIRST block.

    The walk jumps from each section's closing brace to the next ``name={`` at a line start. At a section that does
    not close it stops quietly: the sections before it are kept, that one and everything after it are not.
    """

    def __init__(self, g: bytes):
        self.g, self.top, self._cache = g, {}, {}
        pos = 0
        while (m := _TOP_KEY.search(g, pos)) is not None:
            op = m.end() - 1
            try:
                close = match_brace(g, op)
            except SaveTextError:       # an unclosed section: stop, keeping what came before it
                break
            self.top.setdefault(m.group(1).decode(), Block(m.group(1), m.start(), op, close))
            pos = close + 1

    def block(self, path: str) -> Block | None:
        """``locate(self, path)``, cached per path."""
        if path not in self._cache:
            self._cache[path] = locate(self, path)
        return self._cache[path]


def locate(index: SectionIndex, path: str) -> Block | None:
    """``"a/b/c"`` -> the block: ``a`` from the index (its first occurrence), then each named child at depth 0 of
    the one before (``find_child``). None when any step is absent or does not parse."""
    parts = path.split("/")
    b = index.top.get(parts[0])
    try:
        for p in parts[1:]:
            if b is None:
                return None
            b = find_child(index.g, b, p)
    except SaveTextError:
        return None
    return b


def strip_text_header(raw: bytes) -> bytes:
    """The gamestate text of a plain-text save file: everything after its first line.

    A save file starts with a header line ``SAV`` + 2 bytes + a 2-byte kind + ... . Kind ``00`` is plain text, and
    its body follows the header line. Any other kind (a zip of text, or binary) raises ``SaveTextError`` naming
    the kind: decompressing is the caller's job. Bytes that do not start with ``SAV`` are returned unchanged
    (already a gamestate).
    """
    if raw[:3] != b"SAV":
        return raw
    kind = raw[5:7]
    if kind != b"00":
        raise SaveTextError(f"save header kind {kind.decode('ascii', 'replace')!r} is not plain text (00); "
                            "decompress it first")
    nl = raw.find(b"\n")
    if nl < 0:
        raise SaveTextError("plain-text save header has no end of line")
    return raw[nl + 1:]
