"""POC: how to build the block index fastest (director's ruling 2026-11-02, after djdarcy's push-back on three
negatives: threads, processes, vectorising). Measurement only; production code untouched.

Every arm builds the same five arrays over the founding save's gamestate -- open, close, parent (-1 at top level),
key start, key end (-1 when anonymous), one row per `{`, in file order -- and is checked EQUAL to arm 1 on every row.

PREDICTIONS (the director's, recorded before running; the lead's in brackets):
  arm 1  single-process pure Python: ~10.6 s (the /measure baseline).
  arm 2  threads, 4 and 8 workers over chunks split at top-level sections: no gain under the GIL; a gain over 1.5x
         refutes it. [lead: 0.9-1.1x]
  arm 3  processes, the text in shared memory, N chunks at top-level section boundaries, merged with an offset
         fix-up: 3-5x on this 16-core machine; the merge cost recorded separately. [lead: 3-4x, the merge < 1 s]
  arm 4  numpy, vectorised: braces and quotes by byte comparison, strings masked by quote parity, depth by a
         cumulative sum, pairing by sorting events per depth, parents per depth by searchsorted, keys by searching
         the previous non-blank byte: under 2 s. [lead: 2-4 s, the keys the slow part; a quote escaped inside a
         string may break equality, and the fallback is the regex's string skip for those rows]
  mmap   the five arrays written as raw int64 and reopened with numpy.memmap: under 0.1 s warm.
  CONTROL  arm 4 with the string mask turned off must NOT equal arm 1 (the save has braces inside quoted strings);
           if it does, the equality check cannot see string handling and the arm-4 result is not trusted.
Fallback if no arm beats arm 1 by 1.5x: arm 1 stays the build; the disk cache carries the rest.

Run:  python -I tests/one-offs/thinking/poc_index_build.py <save.ck3> <scratch folder>
Reads one save; writes only the mmap file under the scratch folder and removes it.
"""

import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

T = time.perf_counter
_TOK = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}]')
_KEY_BEFORE = re.compile(rb'([^\s{}=]+)[ \t]*=[ \t]*$')


# --------------------------------------------------------------------------- arm 1 (and each chunk of arms 2, 3)
def index_py(d, base: int = 0, start: int = 0, end: int | None = None):
    end = len(d) if end is None else end
    opens, closes, parents, ks, ke = [], [], [], [], []
    stack: list[int] = []
    for m in _TOK.finditer(d, start, end):
        p = m.start()
        c = d[p]
        if c == 0x7B:
            i = len(opens)
            opens.append(p); closes.append(-1); parents.append(stack[-1] + base if stack else -1)
            ls = d.rfind(b"\n", 0, p) + 1
            km = _KEY_BEFORE.search(d, max(ls, p - 200), p)
            ks.append(km.start(1) if km else -1); ke.append(km.end(1) if km else -1)
            stack.append(i)
        elif c == 0x7D and stack:
            closes[stack.pop()] = p
    return [np.asarray(x, dtype=np.int64) for x in (opens, closes, parents, ks, ke)]


def chunks(d, n: int) -> list[tuple[int, int]]:
    """n ranges of about equal size, each starting at a top-level section (depth 0, outside any string)."""
    starts = [0] + [m.start() for m in gs._TOP_KEY.finditer(d)]
    cuts, want = [0], len(d) / n
    for s in starts:
        if s - cuts[-1] >= want and len(cuts) < n:
            cuts.append(s)
    return list(zip(cuts, cuts[1:] + [len(d)]))


def merge(parts):
    """Concatenate chunk results; a chunk's parents were numbered from 0, so add the rows before it."""
    out, base = [[], [], [], [], []], 0
    for opens, closes, parents, ks, ke in parts:
        out[0].append(opens); out[1].append(closes)
        out[2].append(np.where(parents >= 0, parents + base, -1))
        out[3].append(ks); out[4].append(ke)
        base += len(opens)
    return [np.concatenate(x) for x in out]


# --------------------------------------------------------------------------- arm 3 worker
def _proc_chunk(args):
    name, size, a, b = args
    shm = shared_memory.SharedMemory(name=name)
    try:
        d = bytes(shm.buf[:size])
        return index_py(d, 0, a, b)
    finally:
        shm.close()


# --------------------------------------------------------------------------- arm 4
def index_np(d, mask_strings: bool = True):
    a = np.frombuffer(d, dtype=np.uint8)
    ob = np.flatnonzero(a == 0x7B)
    cb = np.flatnonzero(a == 0x7D)
    if mask_strings:
        q = np.flatnonzero(a == 0x22)
        q = q[(q == 0) | (a[np.maximum(q - 1, 0)] != 0x5C)]          # a quote after a backslash is escaped
        ob = ob[np.searchsorted(q, ob) % 2 == 0]
        cb = cb[np.searchsorted(q, cb) % 2 == 0]
    pos = np.concatenate([ob, cb])
    kind = np.concatenate([np.ones(len(ob), np.int64), -np.ones(len(cb), np.int64)])
    order = np.argsort(pos, kind="stable")
    pos, kind = pos[order], kind[order]
    depth_after = np.cumsum(kind)
    level = np.where(kind > 0, depth_after, depth_after + 1)            # an open's own depth; a close's, before it
    o = np.lexsort((pos, level))
    lp, lk, ll = pos[o], kind[o], level[o]
    is_open = lk > 0
    pair_ok = is_open[:-1] & ~is_open[1:] & (ll[:-1] == ll[1:])
    open_rows = np.flatnonzero(is_open)
    close_of = np.full(len(open_rows), -1, np.int64)
    nxt = open_rows + 1
    has = nxt < len(lp)
    good = np.zeros(len(open_rows), bool)
    good[has] = pair_ok[open_rows[has]]
    close_of[good] = lp[nxt[good]]
    opens_pos, opens_lvl = lp[open_rows], ll[open_rows]
    f = np.argsort(opens_pos, kind="stable")                            # back to file order
    opens = opens_pos[f]; closes = close_of[f]; lvl = opens_lvl[f]
    parents = np.full(len(opens), -1, np.int64)
    for L in range(2, int(lvl.max()) + 1 if len(lvl) else 1):
        child = np.flatnonzero(lvl == L)
        par = np.flatnonzero(lvl == L - 1)
        j = np.searchsorted(opens[par], opens[child]) - 1
        parents[child] = np.where(j >= 0, par[np.maximum(j, 0)], -1)
    # keys: '{' preceded (on its line, over spaces and tabs only) by '=', preceded the same way by a key token
    blank = (a == 0x20) | (a == 0x09)
    nb = np.flatnonzero(~blank)
    pe = nb[np.searchsorted(nb, opens) - 1]                              # the byte before '{', blanks skipped
    is_eq = a[pe] == 0x3D
    pk = nb[np.searchsorted(nb, pe) - 1]                                # the byte before '=', blanks skipped
    delim = blank | (a == 0x0A) | (a == 0x0D) | (a == 0x7B) | (a == 0x7D) | (a == 0x3D)
    tokchar = ~delim[pk]
    dl = np.flatnonzero(delim)
    kstart = dl[np.maximum(np.searchsorted(dl, pk) - 1, 0)] + 1
    keyed = is_eq & tokchar & (opens - kstart <= 200)
    ks = np.where(keyed, kstart, -1)
    ke = np.where(keyed, pk + 1, -1)
    return [opens, closes, parents, ks, ke]


def equal(x, y) -> tuple[bool, str]:
    names = ("open", "close", "parent", "key start", "key end")
    for n, a, b in zip(names, x, y):
        if len(a) != len(b):
            return False, f"{n}: {len(a):,} rows against {len(b):,}"
        diff = np.flatnonzero(a != b)
        if len(diff):
            return False, f"{n}: {len(diff):,} rows differ, first at row {diff[0]:,} ({a[diff[0]]} vs {b[diff[0]]})"
    return True, "equal on every row"


def main() -> int:
    save, scratch = sys.argv[1], Path(sys.argv[2])
    scratch.mkdir(parents=True, exist_ok=True)
    d = sf.read_save(save).gamestate
    rows = []

    t = T(); base = index_py(d); t1 = T() - t
    rows.append(("1 pure Python", f"{t1:.1f} s, {len(base[0]):,} blocks", "baseline", "1.0x"))

    for n in (4, 8):
        t = T()
        with ThreadPoolExecutor(n) as ex:
            parts = list(ex.map(lambda r: index_py(d, 0, *r), chunks(d, n)))
        t_idx = T() - t; t = T(); got = merge(parts); t_m = T() - t
        ok, why = equal(base, got)
        rows.append((f"2 threads x{n}", f"{t_idx:.1f} s + merge {t_m:.2f} s", why, f"{t1 / (t_idx + t_m):.2f}x"))

    shm = shared_memory.SharedMemory(create=True, size=len(d))
    try:
        shm.buf[:len(d)] = d
        for n in (4, 8):                                # each worker copies the 222 MB text: 8 is ~1.8 GB
            t = T()
            with ProcessPoolExecutor(n) as ex:
                parts = list(ex.map(_proc_chunk, [(shm.name, len(d), a, b) for a, b in chunks(d, n)]))
            t_idx = T() - t; t = T(); got = merge(parts); t_m = T() - t
            ok, why = equal(base, got)
            rows.append((f"3 processes x{n}", f"{t_idx:.1f} s (pool start included) + merge {t_m:.2f} s", why,
                         f"{t1 / (t_idx + t_m):.2f}x"))
    finally:
        shm.close(); shm.unlink()

    t = T(); got = index_np(d); t4 = T() - t
    ok4, why = equal(base, got)
    rows.append(("4 numpy", f"{t4:.2f} s", why, f"{t1 / t4:.1f}x"))

    t = T(); ctl = index_np(d, mask_strings=False); tc = T() - t
    okc, whyc = equal(base, ctl)
    rows.append(("CONTROL numpy, strings not masked", f"{tc:.2f} s", whyc,
                 "FAILED as designed" if not okc else "PASSED: method blind to strings"))

    f = scratch / "index.i64"
    arr = np.stack(base)
    t = T(); arr.tofile(f); tw = T() - t
    t = T(); mm = np.memmap(f, dtype=np.int64, mode="r", shape=arr.shape); _ = int(mm[0, -1]); tm = T() - t
    t = T(); full = np.fromfile(f, dtype=np.int64).reshape(arr.shape); tf = T() - t
    rows.append(("mmap", f"write {tw:.2f} s ({f.stat().st_size / 1e6:.0f} MB); memmap open {tm * 1000:.1f} ms; "
                         f"read all {tf:.2f} s (warm)", "equal" if np.array_equal(full, arr) else "DIFFER", "--"))
    del mm
    f.unlink()

    print("\n| arm | time | equality to arm 1 | speed |\n|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
