"""gene_cousins: for each gene the 2023 source layout has and today's target lacks, which target genes drive the same
blendshape attributes? (#40 S5: "the 6 EPE genes were renamed or merged, not removed")

A morph template's `setting = { attribute = "<name>" ... }` lines name the blendshapes it moves; two genes that move
the same attributes are the same control under two names, whatever they are called. Per dropped gene: its templates
and attributes in the 2023 layout, then every target gene sharing an attribute, with the shared ones and its
templates. Read-only.

Usage: python -I tests/one-offs/gene_cousins.py [gene ...]   (default: the six #40 names)
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dna_layout as D  # noqa: E402

P = HERE.parents[1] / "private" / "data"
M23 = P / "originals" / "mods-2023"
SOURCE = [("vanilla", P / "versions" / "1.8.2" / "game"), ("cfp", P / "mods-archive" / "cfp_3.1.5"),
          ("epe", M23 / "epe_1.6.0"), ("tail", P / "layers" / "epe_2022-12_tail")]
WS = Path(r"E:\SteamLibrary\steamapps\workshop\content\1158310")
TARGET = [("vanilla", Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game")),
          ("cfp", WS / "2220098919"), ("epe", WS / "2507209632"), ("patch", WS / "2996881191")]
SIX = ["gene_eye_size", "gene_eye_shut_top", "gene_eye_shut_bottom", "gene_forehead_inner_brow_width",
       "gene_bs_eye_fold_2", "gene_bs_head_round_shape"]


def attributes(spec) -> dict[str, dict[str, set[str]]]:
    """gene -> template -> the attribute names its settings move, from the raw text of every genes file in the
    layout (later folders replace same-named files, as the game loads them)."""
    files = {}
    for _, d in spec:
        g = D.genes_dir(d)
        if g.is_dir():
            for f in sorted(g.glob("*.txt")):
                files[f.name] = f
    out: dict[str, dict[str, set[str]]] = {}
    for f in files.values():
        text = f.read_text(encoding="utf-8-sig", errors="replace")
        for m in re.finditer(r"(?m)^\s*((?:gene_|hair_|eye_|skin_|complexion)\w*)\s*=\s*\{", text):
            gene, start = m.group(1), m.end()
            depth, i = 1, start
            while depth and i < len(text):
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            body = text[start:i]
            tmpl: dict[str, set[str]] = {}
            for t in re.finditer(r"(?m)^\s*(\w+)\s*=\s*\{\s*(?:#[^\n]*)?\n\s*index\s*=", body):
                tb_start = t.end()
                d2, j = 1, body.index("{", t.start()) + 1
                while d2 and j < len(body):
                    d2 += {"{": 1, "}": -1}.get(body[j], 0)
                    j += 1
                tmpl[t.group(1)] = set(re.findall(r'attribute\s*=\s*"([^"]+)"', body[tb_start:j]))
            if tmpl:
                out[gene] = tmpl
    return out


def main(names: list[str]):
    src, dst = attributes(SOURCE), attributes(TARGET)
    by_attr: dict[str, set[str]] = {}
    for gene, t in dst.items():
        for attrs in t.values():
            for a in attrs:
                by_attr.setdefault(a, set()).add(gene)
    for name in names:
        print(f"\n== {name}  (in target: {'YES' if name in dst else 'no'})")
        t = src.get(name)
        if not t:
            print("   not found in the 2023 source layout")
            continue
        all_attrs = set().union(*t.values())
        for tn, attrs in t.items():
            print(f"   2023 template {tn}: {sorted(attrs)}")
        cousins = sorted({g for a in all_attrs for g in by_attr.get(a, ())})
        if not cousins:
            print("   no target gene moves any of these attributes")
        for c in cousins:
            shared = sorted(all_attrs & set().union(*dst[c].values()))
            print(f"   target {c}: shares {shared}; templates {list(dst[c])}")


if __name__ == "__main__":
    main(sys.argv[1:] or SIX)
