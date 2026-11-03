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

import hashlib
import mmap
import os
import re
import tempfile
import time
from array import array
from pathlib import Path

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

# ---- the on-disk cache ([cache] index = true; off by default: the tool writes nothing the player did not ask for)
CACHE_VERSION = 1                  # bump when the index's layout, its key reading or its file format changes
SWEEP_SECONDS = 24 * 3600          # entries older than this are removed when a new one is written
KEEP = 2                           # at most this many saves' indexes are kept (the newest; djdarcy, 2026-11-02)
LAST_EVENT: list = []              # ["wrote", path, bytes] or ["read", path, bytes]: what the plan tells the player
_MAGIC = b"CK3IDX"


def cache_dir() -> Path:
    """The folder the tool names for its index cache: ``CK3UPDATE_CACHE_DIR``, else ``<temp>/ck3-save-updater/index``."""
    given = os.environ.get("CK3UPDATE_CACHE_DIR")
    return Path(given) if given else Path(tempfile.gettempdir()) / "ck3-save-updater" / "index"


def _cache_file(data: bytes) -> Path:
    """Keyed by the gamestate's sha256 and the cache version: the same bytes and the same reader, or no hit."""
    return cache_dir() / f"{hashlib.sha256(data).hexdigest()}-v{CACHE_VERSION}.idx"


def _load(path: Path, data: bytes) -> "BlockIndex | None":
    """The index stored at ``path`` for ``data``, read through a memory map and copied out (the map is closed at
    once, so `cache clear` can always remove the file); None when absent or not a whole, matching file."""
    try:
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            if m[:6] != _MAGIC or int.from_bytes(m[6:14], "little") != len(data):
                return None
            n = int.from_bytes(m[14:22], "little")
            tail = 22 + 32 * n                          # after the header and the four columns: the unclosed count
            if len(m) < tail + 8:
                return None
            u = int.from_bytes(m[tail:tail + 8], "little")
            if len(m) != tail + 8 + 8 * u:
                return None
            cols = []
            for k in range(4):
                a = array("q")
                a.frombytes(m[22 + 8 * n * k:22 + 8 * n * (k + 1)])
                cols.append(a)
            unclosed = array("q")
            unclosed.frombytes(m[tail + 8:tail + 8 + 8 * u])
    except (OSError, ValueError):
        return None
    idx = BlockIndex.__new__(BlockIndex)
    idx.data = data
    idx.opens, idx.closes, idx.key_starts, idx.key_ends = cols
    idx.unclosed = list(unclosed)
    return idx


def _save(path: Path, idx: BlockIndex) -> None:
    """Write the index beside the others, atomically (a temp name, then a rename), and sweep old entries."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = len(idx.opens)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(_MAGIC + len(idx.data).to_bytes(8, "little") + n.to_bytes(8, "little"))
            for a in (idx.opens, idx.closes, idx.key_starts, idx.key_ends):
                a.tofile(f)
            f.write(len(idx.unclosed).to_bytes(8, "little"))
            array("q", idx.unclosed).tofile(f)
        os.replace(tmp, path)
        now = time.time()
        others = sorted((p for p in path.parent.glob("*.idx") if p != path), key=lambda p: p.stat().st_mtime,
                        reverse=True)
        for i, old in enumerate(others):
            if i >= KEEP - 1 or now - old.stat().st_mtime > SWEEP_SECONDS:
                old.unlink(missing_ok=True)
        LAST_EVENT[:] = ["wrote", path, path.stat().st_size]
    except OSError:
        pass                                            # a cache that cannot be written only costs the next build


def clear_cache() -> tuple[int, int]:
    """Remove every cached index (and a leftover partial write); returns (files, bytes) removed."""
    files = size = 0
    for p in list(cache_dir().glob("*.idx")) + list(cache_dir().glob("*.tmp")):
        size += p.stat().st_size
        p.unlink(missing_ok=True)
        files += 1
    return files, size


def index_for(data: bytes) -> BlockIndex:
    """The index of exactly this gamestate object, built once and reused while the same object is asked about; with
    ``[cache] index = true``, read from (or written to) the on-disk cache keyed by the bytes' sha256."""
    if _LAST and _LAST[0].data is data:
        return _LAST[0]
    from ..config import index_cache_on
    use_cache = index_cache_on()
    idx = _load(_cache_file(data), data) if use_cache else None
    if idx is not None:
        LAST_EVENT[:] = ["read", _cache_file(data), _cache_file(data).stat().st_size]
    if idx is None:
        idx = BlockIndex(data)
        if use_cache:
            _save(_cache_file(data), idx)
    _LAST[:] = [idx]
    return idx


def forget() -> None:
    """Drop the kept index (and the gamestate it holds)."""
    _LAST.clear()
