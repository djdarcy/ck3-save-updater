"""eye_fold_census: how many 2023 faces use both eye-fold genes? (#40 S5b, measure before the merge rule)

Layout (a) has gene_bs_eye_fold_shape at place 44 (templates eye_fold_shape_neg 0, eye_fold_shape_pos 1) and
gene_bs_eye_fold_2 at place 116 (vanilla_eye_fold_2 0 = moves nothing, eye_fold_2 1 = bs_eye_fold_2 at 0..1.0).
Today's EPE merged them: gene_bs_eye_fold_shape gained eye_fold_shape_neg_02 (index 2, bs_eye_fold_2 at 0..0.95)
and eye_fold_shape_02_neg (index 3). One gene holds one template per allele, so a face that used both old genes
cannot keep both. This counts, per allele (dominant, recessive), the faces in each case and the value spread.

Usage: python -I tests/one-offs/thinking/eye_fold_census.py <save.ck3> [<save.ck3> ...]
  Faces of 700 or 712 characters are read in layout (a)'s first 130 places; others are skipped.
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

FOLD, FOLD2 = 44, 116


def main():
    for path in sys.argv[1:]:
        ppl = W.people(sf.read_save(path).gamestate)
        cases, f2vals, fvals, faces = Counter(), Counter(), Counter(), 0
        for r in ppl.values():
            if not r["dna"] or len(r["dna"]) not in (700, 712):
                continue
            d = W.b64d(r["dna"])
            faces += 1
            for k, allele in ((0, "dom"), (2, "rec")):
                ft, fv = d[FOLD * 4 + k], d[FOLD * 4 + k + 1]
                t2, v2 = d[FOLD2 * 4 + k], d[FOLD2 * 4 + k + 1]
                uses2 = t2 == 1 and v2 > 0
                fvals[(ft, fv // 32 * 32)] += 1
                if t2 == 1:
                    f2vals[v2 // 32 * 32] += 1
                cases[(allele, "fold_2 used" if uses2 else "fold_2 unused",
                       f"fold_shape t{ft}")] += 1
        print(f"== {Path(path).name}: {faces} faces")
        for k, n in sorted(cases.items()):
            print(f"   {k}: {n}")
        print("   fold_2 template 1 values (bucket of 32):", dict(sorted(f2vals.items())))
        print("   fold_shape (template, value bucket):", dict(sorted(fvals.items())))


if __name__ == "__main__":
    main()
