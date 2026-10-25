"""U5 Unit 1 input: every numbered database in a save (an id space): section path, entry count, min/max id,
for the old save and the 1.20 reference side by side, with the offset K the design's rule gives
(the next power of ten above the save's max, at least the reference's max) and the 32-bit check.

A "database" is a block whose direct children are mostly `<number>={` entries; paths go two levels deep.

Usage: python -I tests/one-offs/measure_unit5_id_spaces.py <old gamestate> <1.20 reference gamestate>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402

NUM_ENTRY = re.compile(rb"(?m)^\t{0,3}(\d+)=\{")


def spaces(g: bytes) -> dict[str, tuple[int, int, int]]:
    idx = L.SectionIndex(g)
    out = {}
    for name, b in idx.top.items():
        cands = [(name, b)]
        try:
            for c in gs.iter_entries(g, *b.body):
                if c.key and not c.key.isdigit():
                    cands.append((f"{name}/{c.key.decode()}", c))
        except gs.GamestateError:
            pass
        for path, blk in cands:
            ids = []
            try:
                ids = [int(e.key) for e in gs.iter_entries(g, *blk.body) if e.key and e.key.isdigit()]
            except gs.GamestateError:
                continue
            if len(ids) >= 3:
                out[path] = (len(ids), min(ids), max(ids))
    return out


def main():
    old = spaces(Path(sys.argv[1]).read_bytes())
    ref = spaces(Path(sys.argv[2]).read_bytes())
    print(f"{'space (section path)':48} {'save n':>8} {'save max':>14} {'ref n':>8} {'ref max':>10} {'K':>14} {'top':>14} ok")
    for path in sorted(set(old) | set(ref)):
        on, _, omax = old.get(path, (0, 0, 0))
        rn, _, rmax = ref.get(path, (0, 0, 0))
        k = 10 ** len(str(max(omax, rmax, 1)))       # next power of ten above both maxima
        top = rmax + k
        print(f"{path:48} {on:>8,} {omax:>14,} {rn:>8,} {rmax:>10,} {k:>14,} {top:>14,} {'yes' if top < 2**32 else 'NO'}")


if __name__ == "__main__":
    main()
