"""/measure: would a cached block tree pay for R11's `**` resolution? (2026-11-02; director's ruling on djdarcy's idea
of keeping the resolved tree as an object, maybe pickled to a temp folder between runs.)

DECISION: whether the speed-up unit adds a disk cache (keyed by the input gamestate's sha256 and the resolver's
version, under a temp folder `ck3update cache clear` empties), or stays in memory (steps 1-2 of the signed unit).

PREDICTIONS (written before running):
  P1  today's resolve for R11's three edits, without the profiler: about 100 s in all (it was 105.6 s in status).
  P2  (A) pickling those three resolve() results: tens of MB, dump and load a few seconds each; a hit saves ~100 s.
  P3  (B) a full block index (every block's open, close, parent, key span) built in one regex pass: 20-40 s in pure
      Python, a few million blocks; as arrays it pickles to ~100-200 MB and loads in 1-3 s.
  P4  sha256 of the 222 MB gamestate (the cache key): under 1 s.
  P5  known answer: for a sample of resolve() results, the index's ancestor key chain equals resolve's, every time.

Read only: reads one save; writes pickles only under the scratch folder given, and removes them at the end.
Run:  python -I tests/one-offs/thinking/measure_tree_cache.py <save.ck3> <scratch folder>
"""

import bisect
import hashlib
import os
import pickle
import random
import re
import sys
import time
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.patches import paths as P  # noqa: E402

T = time.perf_counter


def r11_positions(d: bytes) -> dict[str, list[int]]:
    """The positions R11's three edits hand to resolve (engine._prefiltered, R11's patch.toml)."""
    return {
        "edit1 modifier= at line start": [m.start(1) for m in P.key_regex("modifier", line_start=True).finditer(d)],
        'edit2 "" values': [m.start(1) for m in P.value_regex('""').finditer(d)],
        "edit3 type= at line start": [m.start(1) for m in P.key_regex("type", line_start=True).finditer(d)],
    }


_TOK = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}]')
_KEY_BEFORE = re.compile(rb'([^\s{}=]+)[ \t]*=[ \t]*$')


def build_index(d: bytes):
    """Every block: open, close, parent (-1 at top level), key start/end (-1 when anonymous); file order."""
    opens, closes, parents, ks, ke = (array("q") for _ in range(5))
    stack: list[int] = []
    for m in _TOK.finditer(d):
        c = d[m.start()]
        if c == 0x7B:                                   # {
            i = len(opens)
            opens.append(m.start()); closes.append(-1); parents.append(stack[-1] if stack else -1)
            ls = d.rfind(b"\n", 0, m.start()) + 1
            km = _KEY_BEFORE.search(d, max(ls, m.start() - 200), m.start())
            if km:
                ks.append(km.start(1)); ke.append(km.end(1))
            else:
                ks.append(-1); ke.append(-1)
            stack.append(i)
        elif c == 0x7D:                                 # }
            if stack:
                closes[stack.pop()] = m.start()
    return opens, closes, parents, ks, ke, len(stack)


def chain_at(d: bytes, idx, pos: int) -> list[bytes | None]:
    """Keys of the blocks containing pos, outermost first (from the index)."""
    opens, closes, parents, ks, ke = idx[:5]
    i = bisect.bisect_left(opens, pos) - 1
    while i >= 0 and not (opens[i] < pos < closes[i]):
        i = parents[i] if opens[i] < pos else i - 1
    out = []
    while i >= 0:
        out.append(d[ks[i]:ke[i]] if ks[i] >= 0 else None)
        i = parents[i]
    return out[::-1]


def size_mb(path: Path) -> float:
    return path.stat().st_size / 1e6


def main() -> int:
    save, scratch = sys.argv[1], Path(sys.argv[2])
    scratch.mkdir(parents=True, exist_ok=True)
    t = T(); d = sf.read_save(save).gamestate; t_read = T() - t
    t = T(); key = hashlib.sha256(d).hexdigest(); t_sha = T() - t
    print(f"gamestate {len(d) / 1e6:.1f} MB, read {t_read:.1f} s; sha256 {key[:12]} in {t_sha:.2f} s   [P4]")

    # ---- (A) today's resolve, per edit, and its results pickled
    results, t_resolve = {}, {}
    for name, pos in r11_positions(d).items():
        t = T(); results[name] = P.resolve(d, pos); t_resolve[name] = T() - t
        print(f"(A) {name}: {len(pos):,} positions -> {len(results[name]):,} resolved in {t_resolve[name]:.1f} s")
    print(f"(A) resolve total {sum(t_resolve.values()):.1f} s   [P1]")
    pa = scratch / "resolved.pkl"
    t = T(); pa.write_bytes(pickle.dumps(results, protocol=5)); t_dump = T() - t
    t = T(); back = pickle.loads(pa.read_bytes()); t_load = T() - t
    same = all(set(back[n]) == set(results[n]) and all(
        [b.key for b in back[n][p][0]] == [b.key for b in results[n][p][0]] for p in random.sample(
            sorted(results[n]), min(2000, len(results[n])))) for n in results)
    print(f"(A) pickle {size_mb(pa):.1f} MB, dump {t_dump:.1f} s, load {t_load:.1f} s; round trip equal: {same}   [P2]")

    # ---- (B) a full block index, as arrays
    t = T(); idx = build_index(d); t_build = T() - t
    n, unclosed = len(idx[0]), idx[5]
    print(f"(B) index: {n:,} blocks in {t_build:.1f} s; unclosed at end: {unclosed}   [P3]")
    pb = scratch / "index.pkl"
    t = T(); pb.write_bytes(pickle.dumps(idx[:5], protocol=5)); t_dump = T() - t
    t = T(); idx2 = pickle.loads(pb.read_bytes()); t_load = T() - t
    print(f"(B) pickle {size_mb(pb):.1f} MB, dump {t_dump:.1f} s, load {t_load:.1f} s; arrays equal: "
          f"{all(a == b for a, b in zip(idx[:5], idx2))}")

    # ---- known answer: the index's chains equal resolve's, on a sample of each edit's results
    ok = total = 0
    mism = []
    random.seed(7)
    for name, res in results.items():
        for p in random.sample(sorted(res), min(3000, len(res))):
            anc, child = res[p]
            want = [b.key for b in anc]
            got = chain_at(d, idx2, child.key_start)
            total += 1
            if got == want:
                ok += 1
            elif len(mism) < 5:
                mism.append((name, p, want[-3:], got[-3:]))
    print(f"known answer: index chain == resolve chain on {ok:,} of {total:,} sampled positions   [P5]")
    for m in mism:
        print("  mismatch:", m)
    t = T()
    for name, res in results.items():
        for p in sorted(res)[:20000]:
            chain_at(d, idx2, res[p][1].key_start)
    print(f"(B) lookup speed: 60,000 chains from the index in {T() - t:.1f} s")
    for f in (pa, pb):
        f.unlink()
    print("pickles removed:", not pa.exists() and not pb.exists())
    return 0


if __name__ == "__main__":
    sys.exit(main())
