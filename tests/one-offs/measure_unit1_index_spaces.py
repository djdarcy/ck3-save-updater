"""Unit 1 checks (a) and (b) for the id structure (24-bit index + 8-bit generation in the top byte).

(a) Do the three character sections (living, dead_unprunable, characters/dead_prunable) form one index
    space? Duplicate full ids across sections, duplicate indices across sections, and for duplicate
    indices whether the generations differ (slot reuse) or match (a real clash).
(b) The same within each section: duplicate full ids (a parsing artifact or a repeat) vs. duplicate
    indices with different generations (slot reuse).

Prints, per save: per section n, distinct full ids, distinct indices, generation histogram head; then the
cross-section overlap table, with a few examples.

Usage: python -I tests/one-offs/measure_unit1_index_spaces.py <gamestate> [<gamestate> ...]
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402

SECTIONS = ["living", "dead_unprunable", "characters/dead_prunable"]
LOW = 0xFFFFFF


def ids_of(g: bytes, path: str) -> list[int]:
    try:
        blk = gs.locate(g, path)
    except gs.GamestateError:
        return []
    return [int(e.key) for e in gs.iter_entries(g, *blk.body) if e.key and e.key.isdigit()]


def report(name: str, g: bytes) -> None:
    print(f"== {name}")
    per = {p: ids_of(g, p) for p in SECTIONS}
    for p, ids in per.items():
        gens = Counter(i >> 24 for i in ids)
        idx = Counter(i & LOW for i in ids)
        dup_full = sum(1 for c in Counter(ids).values() if c > 1)
        dup_idx = [k for k, c in idx.items() if c > 1]
        print(f"  {p:28} n={len(ids):>7,} full-distinct={len(set(ids)):>7,} index-distinct={len(idx):>7,} "
              f"dup-full={dup_full} dup-index={len(dup_idx)} max-index={max(idx) if idx else 0:,} "
              f"gens={dict(sorted(gens.items())[:6])}{'...' if len(gens) > 6 else ''}")
        if dup_idx:
            by = defaultdict(list)
            for i in ids:
                if i & LOW in set(dup_idx[:5]):
                    by[i & LOW].append(i)
            for k, v in list(by.items())[:5]:
                print(f"      index {k:,}: ids {[(x >> 24, x) for x in v]}")
    # cross-section
    names = list(per)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            A, B = per[names[a]], per[names[b]]
            full = set(A) & set(B)
            ia = defaultdict(set)
            for i in A:
                ia[i & LOW].add(i >> 24)
            same_gen, diff_gen = 0, 0
            ex = []
            for i in B:
                gens_a = ia.get(i & LOW)
                if gens_a:
                    if (i >> 24) in gens_a:
                        same_gen += 1
                    else:
                        diff_gen += 1
                        if len(ex) < 3:
                            ex.append((i & LOW, sorted(gens_a), i >> 24))
            print(f"  {names[a]} x {names[b]}: shared full ids={len(full)}; shared index same-gen={same_gen}, "
                  f"diff-gen (slot reuse)={diff_gen}; e.g. (index, gens in first, gen in second) {ex}")
    allids = [i for v in per.values() for i in v]
    allidx = {i & LOW for i in allids}
    print(f"  union: n={len(allids):,} full-distinct={len(set(allids)):,} index-distinct={len(allidx):,} "
          f"max-index={max(allidx) if allidx else 0:,}")


def main():
    for p in sys.argv[1:]:
        report(Path(p).parent.name, Path(p).read_bytes())


if __name__ == "__main__":
    main()
