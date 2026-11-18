"""F1, the faces control (goal 2026-11-18__17-11-09): does the reference's version change the campaign's faces?

The same chain (the founding 1.8.1 save through `migrate`, v17's portrait mods and pack) was run twice, differing only
in the reference: 1.20 and 1.21. A campaign character is one alive in the original save; the reference's own characters
(transplanted) are counted apart. Prints how many campaign faces are identical, differ, or are missing on one side,
with examples. Read only.
Run: python -I -X utf8 tests/one-offs/thinking/f1_faces_control.py <original.ck3> <chain_ref120.ck3> <chain_ref121.ck3>
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DNA = re.compile(rb'\n\t+dna="?([^"\s]+)"?')


def faces(path):
    g = read_save(path).gamestate
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "living").body):
        if e.key:
            m = DNA.search(g[e.open:e.close])
            out[e.key.decode()] = m.group(1) if m else None
    return out


def main(orig, a, b):
    campaign = set(faces(orig))
    fa, fb = faces(a), faces(b)
    same = diff = only_a = only_b = 0
    examples = []
    for c in sorted(campaign):
        x, y = fa.get(c), fb.get(c)
        if c not in fa and c not in fb:
            continue
        if c not in fb:
            only_a += 1
        elif c not in fa:
            only_b += 1
        elif x == y:
            same += 1
        else:
            diff += 1
            if len(examples) < 5:
                examples.append((c, (x or b"")[:24], (y or b"")[:24]))
    print(f"campaign characters alive in the original: {len(campaign):,}")
    print(f"  faces identical between the 1.20- and 1.21-reference chains: {same:,}")
    print(f"  faces differ: {diff:,}   only in the 1.20 chain: {only_a:,}   only in the 1.21 chain: {only_b:,}")
    for ex in examples:
        print("   ", ex)
    print(f"reference characters (not campaign): 1.20 chain {len(set(fa) - campaign):,}, "
          f"1.21 chain {len(set(fb) - campaign):,}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
