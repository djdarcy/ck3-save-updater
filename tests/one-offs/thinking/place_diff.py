"""place_diff: which gene places differ between two migrated saves, over every character's face? (#40 unit W)

For each character in both saves whose dna= decodes to the same length, compares the faces 4 bytes (one gene
place) at a time and tallies the places that differ. A face change that is meant to touch one gene (the rename
moves gene_bs_head_shape, place 117) should show that place and no other.

With --witness <967.ck3> it also prints the named characters' witness face at a source place (default 119,
head_round_shape in layout (a)), so a value at place 117 can be traced to where it came from.

Usage: python -I tests/one-offs/thinking/place_diff.py <a.ck3> <b.ck3> [--witness W.ck3 --ids 28792,50822 --src 119]
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))
import dna_whole_save as W  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    a_p, b_p = sys.argv[1:3]
    a = W.people(sf.read_save(a_p).gamestate)
    b = W.people(sf.read_save(b_p).gamestate)
    places, faces, changed, skipped = Counter(), 0, 0, 0
    for cid, ra in a.items():
        rb = b.get(cid)
        if not (rb and ra["dna"] and rb["dna"]):
            continue
        da, db = W.b64d(ra["dna"]), W.b64d(rb["dna"])
        if len(da) != len(db):
            skipped += 1
            continue
        faces += 1
        diff = [i // 4 for i in range(0, len(da), 4) if da[i:i + 4] != db[i:i + 4]]
        if diff:
            changed += 1
            places.update(diff)
    print(f"faces compared {faces}, changed {changed}, length differs {skipped}")
    print("places differing (place: faces):", dict(sorted(places.items())))
    ids = arg("--ids", "28792,50822").split(",")
    for cid in ids:
        for tag, d in (("a", a), ("b", b)):
            r = d.get(cid)
            if r and r["dna"]:
                raw = W.b64d(r["dna"])
                print(f"{tag} {cid} {r['name']} place117 {tuple(raw[117 * 4:118 * 4])}")
    wit = arg("--witness")
    if wit:
        src = int(arg("--src", "119"))
        w = W.people(sf.read_save(wit).gamestate)
        for cid in ids:
            r = w.get(cid)
            if r and r["dna"]:
                raw = W.b64d(r["dna"])
                print(f"witness {cid} {r['name']} len {len(r['dna'])} place{src} {tuple(raw[src * 4:src * 4 + 4])}")


if __name__ == "__main__":
    main()
