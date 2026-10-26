"""DNA layout decode (U7 measurement): which gene sits at which place in a save's DNA string, per game version
and mod set, and where each gene comes from.

A layout is built from one or more `common/genes` folders in load order (vanilla first). Files with the same name
in a later folder replace the earlier file whole (the engine's file override); genes with the same name in a later
file replace the earlier gene. Each gene's own `index = N` (its direct child, not a template's) is its place in
the DNA; every place is 4 bytes (dominant template, dominant value, recessive template, recessive value).

Prints, per layout: gene count, highest index, the byte length that implies, gaps and clashes in the index space,
and a table of index -> gene, category, template count, source. With two layouts, prints the translation: genes
kept at the same index, moved, only in one layout, and template lists that changed.

Usage:
  python -I tests/one-offs/dna_layout.py LAYOUT [LAYOUT ...] [--table]
  LAYOUT = name=label:dir1;label:dir2;...   (each dir is a folder holding common/genes, or a genes folder)
"""
import re
import sys
from pathlib import Path

CATS = ("color_genes", "morph_genes", "accessory_genes")


def tokens(text: str):
    text = re.sub(r"#[^\n]*", "", text)
    return re.findall(r'"[^"]*"|[{}=]|[^\s{}="]+', text)


def parse(tok, i=0):
    """Parse a block body into a list of (key, value); value is a list (block) or a string."""
    out = []
    while i < len(tok):
        t = tok[i]
        if t == "}":
            return out, i + 1
        if i + 1 < len(tok) and tok[i + 1] == "=":
            key = t
            v = tok[i + 2]
            if v == "{":
                val, i = parse(tok, i + 3)
            else:
                val, i = v, i + 3
            out.append((key, val))
        elif t == "{":
            val, i = parse(tok, i + 1)
            out.append((None, val))
        else:
            out.append((None, t))
            i += 1
    return out, i


def genes_dir(d: Path) -> Path:
    return d if d.name == "genes" else d / "common" / "genes"


def load_layout(spec: list[tuple[str, Path]]) -> dict:
    files: dict[str, tuple[str, Path]] = {}
    for label, d in spec:
        g = genes_dir(d)
        if not g.is_dir():
            print(f"  (no genes folder: {g})")
            continue
        for f in sorted(g.glob("*.txt")):
            files[f.name] = (label, f)
    genes: dict[str, dict] = {}
    for fname in sorted(files):
        label, f = files[fname]
        body, _ = parse(tokens(f.read_text(encoding="utf-8-sig", errors="replace")))
        for key, val in body:
            if key == "special_genes" and isinstance(val, list):
                blocks = [(k, v, True) for k, v in val if k in CATS]
            elif key in CATS:
                blocks = [(key, val, False)]
            else:
                continue
            for cat, blk, special in blocks:
                if not isinstance(blk, list):
                    continue
                for gname, gval in blk:
                    if not isinstance(gval, list) or gname is None:
                        continue
                    idx = next((v for k, v in gval if k == "index" and isinstance(v, str)), None)
                    templates = [k for k, v in gval if isinstance(v, list) and k not in (None, "ugliness_feature_categories")
                                 and any(kk == "index" for kk, _ in v)]
                    tidx = [int(vv) for k, v in gval if isinstance(v, list) for kk, vv in v
                            if kk == "index" and isinstance(vv, str) and vv.isdigit()]
                    tidx_by_name = {k: int(vv) for k, v in gval if isinstance(v, list) and k is not None
                                    for kk, vv in v if kk == "index" and isinstance(vv, str) and vv.isdigit()}
                    genes[gname] = {"name": gname, "cat": ("special " if special else "") + cat,
                                    "index": int(idx) if idx and idx.lstrip("-").isdigit() else None,
                                    "templates": templates, "tmax": max(tidx) if tidx else None,
                                    "tidx_by_name": tidx_by_name,
                                    "src": label, "file": fname, "order": len(genes)}
    return genes


def dna_order(genes: dict, mode: str = "file") -> list[dict]:
    """The genes stored in DNA (non-special), in DNA order.
    mode 'file': file-name order, declaration order inside a file (categories as they come);
    mode 'grouped': all color genes, then morph, then accessory, each in that file order."""
    ns = [g for g in genes.values() if not g["cat"].startswith("special")]
    ns.sort(key=lambda g: (g["file"], g["order"]))
    if mode == "grouped":
        rank = {"color_genes": 0, "morph_genes": 1, "accessory_genes": 2}
        ns.sort(key=lambda g: rank[g["cat"]])
    return ns


def fit(order: list[dict], dnas: list[bytes]) -> tuple[int, list[str]]:
    """Positions where the save's template bytes exceed the gene's highest template index (impossible) -- 0 is a fit.
    Returns (impossible positions, report lines)."""
    lines, bad = [], 0
    n = min(len(order), min(len(d) for d in dnas) // 4)
    for p in range(n):
        g = order[p]
        if g["cat"] == "color_genes":
            continue
        obs = max(max(d[p * 4], d[p * 4 + 2]) for d in dnas)
        tm = g["tmax"] if g["tmax"] is not None else -1
        flag = "IMPOSSIBLE" if obs > tm else ("" if obs == tm else "under")
        if obs > tm:
            bad += 1
        lines.append(f"   {p:4} {g['name']:44} tmax {tm:4} observed {obs:4} {flag}")
    return bad, lines


def summary(name: str, genes: dict) -> dict[int, list[dict]]:
    by_idx: dict[int, list[dict]] = {}
    for g in genes.values():
        if g["index"] is not None:
            by_idx.setdefault(g["index"], []).append(g)
    hi = max(by_idx) if by_idx else -1
    gaps = [i for i in range(hi + 1) if i not in by_idx]
    clash = {i: [g["name"] for g in gs] for i, gs in by_idx.items() if len(gs) > 1}
    noidx = [g["name"] for g in genes.values() if g["index"] is None]
    src = {}
    for g in genes.values():
        src[g["src"]] = src.get(g["src"], 0) + 1
    print(f"\n== {name}: {len(genes)} genes; highest index {hi}; implied DNA {4 * (hi + 1)} bytes "
          f"= {-(-4 * (hi + 1) // 3) * 4} base64 characters")
    print(f"   by source: {src}")
    print(f"   gaps in 0..{hi}: {gaps[:20]}{' ...' if len(gaps) > 20 else ''} ({len(gaps)})")
    print(f"   clashes (two genes, one index): {len(clash)} {list(clash.items())[:6]}")
    if noidx:
        print(f"   genes with no index: {len(noidx)} {noidx[:8]}")
    return by_idx


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    table = "--table" in sys.argv
    layouts = []
    for a in args:
        name, rest = a.split("=", 1)
        spec = []
        for part in rest.split(";"):
            label, d = part.split(":", 1) if ":" in part and not re.match(r"^[A-Za-z]:[\\/]", part) else ("vanilla", part)
            spec.append((label, Path(d)))
        genes = load_layout(spec)
        layouts.append((name, genes, summary(name, genes)))
        if table:
            for i, gs in sorted(layouts[-1][2].items()):
                for g in gs:
                    print(f"   {i:4} {g['name']:44} {g['cat']:26} t={len(g['templates']):<3} {g['src']}:{g['file']}")
    for (na, ga, _), (nb, gb, _) in zip(layouts, layouts[1:]):
        same = [n for n in ga if n in gb and ga[n]["index"] == gb[n]["index"]]
        moved = [(n, ga[n]["index"], gb[n]["index"]) for n in ga if n in gb and ga[n]["index"] != gb[n]["index"]]
        only_a = [n for n in ga if n not in gb]
        only_b = [n for n in gb if n not in ga]
        tchg = [n for n in ga if n in gb and ga[n]["templates"] != gb[n]["templates"]]
        print(f"\n== translation {na} -> {nb}")
        print(f"   same index: {len(same)}; moved: {len(moved)}; only in {na}: {len(only_a)}; only in {nb}: {len(only_b)}; "
              f"template list changed: {len(tchg)}")
        print(f"   moved (first 15): {moved[:15]}")
        print(f"   only in {na}: {[(n, ga[n]['index'], ga[n]['src']) for n in only_a][:25]}")
        print(f"   only in {nb}: {[(n, gb[n]['index'], gb[n]['src']) for n in only_b][:25]}")
        for n in tchg[:12]:
            a_t, b_t = ga[n]["templates"], gb[n]["templates"]
            print(f"   templates {n}: {len(a_t)} -> {len(b_t)}; dropped {[t for t in a_t if t not in b_t][:5]} "
                  f"added {[t for t in b_t if t not in a_t][:5]}")


if __name__ == "__main__":
    main()
