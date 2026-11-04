"""witness_tail_place: which gene is the 967 witness faces' extra place (index 130, the 131st)? (#40 S3)

Layout (a) has 130 places; the witness faces hold 131 (700 characters), the 1.8.1 faces 133 (712), whose places
130-132 are hair_aging, gene_bs_eye_lower_lid_size, gene_bs_eye_shape (the tail layer). For every character in
both saves, compares the witness's place 130 with each of the 1.8.1 face's places 130, 131, 132 and counts the
matches; the place it agrees with most is the gene it holds. Also tallies the witness's template bytes there.

Usage: python -I tests/one-offs/thinking/witness_tail_place.py <1.8.1 save.ck3> <967 witness.ck3>
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


def main():
    new = W.people(sf.read_save(sys.argv[1]).gamestate)
    wit = W.people(sf.read_save(sys.argv[2]).gamestate)
    agree, both, wt, nt = Counter(), 0, Counter(), {p: Counter() for p in (130, 131, 132)}
    diffp, shift1 = Counter(), Counter()
    for cid, w in wit.items():
        n = new.get(cid)
        if not (w["dna"] and n and n["dna"] and w["name"] == n["name"] and w["birth"] == n["birth"]):
            continue
        dw, dn = W.b64d(w["dna"]), W.b64d(n["dna"])
        if len(dw) != 524 or len(dn) != 532:
            continue
        both += 1
        x = dw[130 * 4:131 * 4]
        wt[(x[0], x[2])] += 1
        for p in (130, 131, 132):
            y = dn[p * 4:p * 4 + 4]
            nt[p][(y[0], y[2])] += 1
            if x == y:
                agree[p] += 1
                if x[0] or x[2]:
                    agree[f"{p} (witness template not 0)"] += 1
        if x[0] or x[2]:
            agree["witness template not 0"] += 1
        # does the rest of the face agree? (places 0-129, the shared layout)
        agree["places 0-129 identical"] += dw[:520] == dn[:520]
        for p in range(130):
            if dw[p * 4:p * 4 + 4] != dn[p * 4:p * 4 + 4]:
                diffp[p] += 1
            if dw[p * 4:p * 4 + 4] == dn[(p + 1) * 4:(p + 2) * 4]:
                shift1[p] += 1
    print(f"characters in both with 700/712 faces: {both}")
    print("witness place 130 equal to 1.8.1 place:", dict(agree))
    print("witness place 130 templates (dom, rec):", wt.most_common(8))
    for p in (130, 131, 132):
        print(f"1.8.1 place {p} templates:", nt[p].most_common(8))
    print("places differing (place: characters):", dict(sorted(diffp.items())))
    print("witness place p equal to 1.8.1 place p+1:", {p: c for p, c in sorted(shift1.items()) if c > both // 2})


if __name__ == "__main__":
    main()
