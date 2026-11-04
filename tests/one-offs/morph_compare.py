"""morph_compare: one character's face, blendshape by blendshape, old layout against new (#40 S7, "Beidh looks wider").

R19 carries each gene's (template, value) by name, so the same bytes arrive. A face can still draw differently when
a same-named template moves different blendshapes, or over a different range, in today's mod build, or when a gene
is new (defaulted) or gone (dropped). This reads every genes file of both layouts (later folders replace same-named
files, as the game loads them; @variables resolved per file), takes the character's dominant allele from each face,
and prints each blendshape attribute whose weight differs, largest difference first.

Weight of a setting = min + (max - min) * value / 255, from the sex block (female falls back to male when it says
"female = male"). The engine's clamping of a negative weight is not modelled: both raw weights are printed.

Usage: python -I tests/one-offs/morph_compare.py <old face b64> <new face b64> [--sex female|male] [--grep width]
       python -I tests/one-offs/morph_compare.py --ids 50822 --old-save <a.ck3> --new-save <b.ck3> [--sex female]
  The old face is read in layout (a) (1.8.2 + CFP 3.1.11 + EPE 1.6.0, + the tail layer when it is 712 characters),
  the new one in layout (c) (today's game + CFP, EPE, patch).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_whole_save as W  # noqa: E402
from ck3_save_migrator import dna  # noqa: E402

TAIL = HERE.parents[1] / "private" / "data" / "layers" / "epe_2022-12_tail"


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def num(s, var):
    s = var.get(s, s)
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def settings(spec, sex: str) -> dict:
    """gene -> template name -> [(attribute, min, max)] for one sex."""
    files = {}
    for _, d in spec:
        g = D.genes_dir(Path(d))
        if g.is_dir():
            for f in sorted(g.glob("*.txt")):
                files[f.name] = f
    out = {}
    for f in files.values():
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        var = dict(re.findall(r"(?m)^\s*(@\w+)\s*=\s*([-\d.]+)", text))
        body, _ = D.parse(D.tokens(text))
        for cat, genes in body:
            if not isinstance(genes, list):
                continue
            for gname, gbody in genes:
                if not isinstance(gbody, list):
                    continue
                for tname, tbody in gbody:
                    if not isinstance(tbody, list) or not any(k == "index" for k, _ in tbody):
                        continue
                    blocks = dict((k, v) for k, v in tbody if k in ("male", "female", "boy", "girl"))
                    blk = blocks.get(sex)
                    while isinstance(blk, str) and blk in blocks:   # "female = male"
                        blk = blocks[blk]
                    rows = []
                    for k, s in (blk if isinstance(blk, list) else []):
                        if k != "setting" or not isinstance(s, list):
                            continue
                        d = dict((a, b) for a, b in s if a)
                        v = d.get("value")
                        if isinstance(v, list):
                            vd = dict((a, b) for a, b in v if a)
                            rows.append((d.get("attribute", "").strip('"'), num(vd.get("min"), var),
                                         num(vd.get("max"), var)))
                    out.setdefault(gname, {})[tname] = rows
    return out


def weights(face: bytes, layout, defs) -> dict:
    """attribute -> (weight, gene, template) for the dominant allele."""
    out = {}
    for p, g in enumerate(layout.genes):
        if g["cat"] == "color_genes" or len(face) < p * 4 + 2:
            continue
        t, v = face[p * 4], face[p * 4 + 1]
        tname = next((n for n, i in g["tidx_by_name"].items() if i == t), None)
        for attr, lo, hi in defs.get(g["name"], {}).get(tname, []):
            if lo is None or hi is None:
                continue
            out[attr] = (lo + (hi - lo) * v / 255, g["name"], tname)
    return out


def compare(old_b64: bytes, new_b64: bytes, sex: str, grep: str | None):
    old, new = W.b64d(old_b64), W.b64d(new_b64)
    spec_a = W.LAYOUT_A + ([("tail", TAIL)] if len(old) >= 532 else [])
    la, lc = dna.build_layout("a", spec_a), dna.build_layout("c", W.LAYOUT_C)
    wa, wc = weights(old, la, settings(spec_a, sex)), weights(new, lc, settings(W.LAYOUT_C, sex))
    rows = []
    for attr in sorted(set(wa) | set(wc)):
        a, c = wa.get(attr), wc.get(attr)
        da, dc = (a[0] if a else 0.0), (c[0] if c else 0.0)
        if abs(da - dc) > 1e-6 and (not grep or grep in attr):
            rows.append((abs(da - dc), attr, a, c))
    rows.sort(reverse=True)
    print(f"{len(rows)} blendshape weights differ (dominant allele, {sex})")
    for d, attr, a, c in rows[:40]:
        fa = f"{a[0]:+.3f} {a[1]}/{a[2]}" if a else "  (not drawn)"
        fc = f"{c[0]:+.3f} {c[1]}/{c[2]}" if c else "  (not drawn)"
        print(f"  {d:.3f}  {attr:38s} old {fa:60s} new {fc}")


def main():
    sex, grep = arg("--sex", "female"), arg("--grep")
    if "--ids" in sys.argv:
        from ck3_save_migrator import savefile as sf
        old = W.people(sf.read_save(arg("--old-save")).gamestate)
        new = W.people(sf.read_save(arg("--new-save")).gamestate)
        for cid in arg("--ids").split(","):
            print(f"== {cid} {old[cid]['name']}")
            compare(old[cid]["dna"], new[cid]["dna"], sex, grep)
    else:
        compare(sys.argv[1].encode(), sys.argv[2].encode(), sex, grep)


if __name__ == "__main__":
    main()
