"""savediff_real_lift: the vendored savediff against the probe it was lifted from, on real saves (the check the
cloud worker could not run: it has no saves).

For each save of the triple (ref, chain, ours): savediff.shape(g) against shape_diff.shape(g), every path and every
field (size, kinds, keys, repeats). Then the census numbers: the probe's keys() (title offset, character offset,
new-map titles, new-map characters) against the same numbers rebuilt from savediff's primitives.

Usage: python -I tests/one-offs/savediff_real_lift.py <ref.ck3> <chain.ck3> <ours.ck3>
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import shape_diff as P  # noqa: E402
from ck3_save_migrator._vendor.savediff import ids as I, keys as K, shape as S, text as T  # noqa: E402


def main():
    t0 = time.time()
    g3 = {n: P.load(p) for n, p in zip(("ref", "chain", "ours"), sys.argv[1:4])}
    print(f"loaded in {time.time() - t0:.0f}s")
    bad = 0
    for n, g in g3.items():
        a, b = P.shape(g), S.shape(g)
        diffs = [p for p in set(a) | set(b)
                 if p not in a or p not in b or (a[p].size, a[p].kinds, a[p].keys, a[p].repeats)
                 != (b[p].size, b[p].kinds, b[p].keys, b[p].repeats)]
        bad += len(diffs)
        print(f"{n}: {len(a)} paths (probe), {len(b)} (library); differing {len(diffs)} {sorted(diffs)[:8]}  "
              f"[{time.time() - t0:.0f}s]")
    pk = P.keys(g3)
    idx = {n: T.SectionIndex(g) for n, g in g3.items()}
    tk = {n: K.field_keys(g, idx[n], "landed_titles/landed_titles") for n, g in g3.items()}
    tid = {n: {k: i for i, k in m.items()} for n, m in tk.items()}
    toff, new_titles = I.offset_by_mode(tid["ref"], tid["ours"])
    paths = ("living", "dead_unprunable", "characters/dead_prunable")
    ch = {n: K.union_keys(g, idx[n], paths) for n, g in g3.items()}
    campaign = ch["ours"] & ch["chain"]
    coff = 1 + max(I.slot(i) for i in campaign)
    new_ref = {r for r in ch["ref"] if I.translate(r, coff) in ch["ours"]}
    rows = [("title offset", pk.title_offset, toff), ("new-map titles", len(pk.new_titles), len(new_titles)),
            ("character offset", pk.char_offset, coff), ("new-map characters", len(pk.new_chars_ref), len(new_ref)),
            ("title keys (ours)", len(pk.tkey["ours"]), len(tk["ours"]))]
    for name, p, l in rows:
        bad += p != l
        print(f"  {name:22} probe {p}  library {l}  {'OK' if p == l else 'DIFFERENT'}")
    print(f"{'ALL EQUAL' if not bad else f'{bad} DIFFERENCES'} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
