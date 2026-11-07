"""Write a names-only gene table from a portrait-mod build (or a game's own genes), for R19's built-in tables.

A table keeps exactly what R19 reads from a build (``dna.load_genes``): every ``common/genes/*.txt`` file name (a
later folder's file of the same name replaces an earlier one whole, so even a file left empty is kept), and in each
file the gene categories, the genes in their order (special genes included: a later gene of the same name takes the
earlier one's place), and each template's name and ``index``. Nothing else: no blendshapes, colours, settings or
art, so the mod authors' work is not copied (djdarcy 2026-11-03, on the first such table: "we just want the smallest
piece to make epe and cfp reusable for the future as essentially a patch").

Usage:
    python scripts/gene_table.py <build folder> <out folder> --name "Community Flavor Pack" --version 3.1.11
        [--workshop 2220098919] [--stands-in mod/cfp_3.1.5.mod,mod/cfp_3.1.11.mod] [--game-line 1.8]
        [--source "where the build was read"]

The out folder gets ``common/genes/<the same file names>`` and ``table.toml`` (the provenance).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ck3_save_migrator.dna import CATS, genes_dir, parse, template_indexes, tokens  # noqa: E402

HEADER = ("# Names only, written by scripts/gene_table.py: the gene categories, gene names in their order, and each "
          "template's\n# name and index, as R19 reads them. No settings, blendshapes, colours or art.\n")


def _genes(blk: list, tab: str) -> list[str]:
    """The genes of one category block, each indented by ``tab``, its templates one level deeper."""
    out = []
    for gname, gval in blk:
        if gname is None or not isinstance(gval, list):
            continue
        tpl = list(template_indexes(gval).items())     # exactly what R19 reads (dna.load_genes)
        if tpl:
            inner = "".join(f"{tab}\t{k} = {{ index = {i} }}\n" for k, i in tpl)
            out.append(f"{tab}{gname} = {{\n{inner}{tab}}}\n")
        else:
            out.append(f"{tab}{gname} = {{ }}\n")
    return out


def names_only(text: str) -> str:
    """One genes file, reduced to what R19 reads."""
    body, _ = parse(tokens(text))
    out = [HEADER]
    for key, val in body:
        if key in CATS and isinstance(val, list):
            out.append(f"{key} = {{\n" + "".join(_genes(val, "\t")) + "}\n")
        elif key == "special_genes" and isinstance(val, list):
            inner = "".join(f"\t{k} = {{\n" + "".join(_genes(v, "\t\t")) + "\t}\n" for k, v in val
                            if k in CATS and isinstance(v, list))
            out.append(f"special_genes = {{\n{inner}}}\n")
    return "".join(out)


def write_table(build: Path, out: Path, provenance: dict) -> int:
    src = genes_dir(build)
    dst = out / "common" / "genes"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.glob("*.txt")):
        (dst / f.name).write_text(names_only(f.read_text(encoding="utf-8-sig", errors="replace")), encoding="utf-8")
        n += 1
    lines = [f'{k} = "{v}"' for k, v in provenance.items() if isinstance(v, str) and v]
    lines += [f'{k} = [{", ".join(chr(34) + x + chr(34) for x in v)}]' for k, v in provenance.items()
              if isinstance(v, list) and v]
    (out / "table.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("build")
    ap.add_argument("out")
    ap.add_argument("--name", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--workshop", default="")
    ap.add_argument("--stands-in", default="", help="launcher entries (mod/x.mod) this table may stand in for")
    ap.add_argument("--game-line", default="", help="for the game's own genes: the version line, e.g. 1.8")
    ap.add_argument("--source", default="")
    a = ap.parse_args(argv)
    prov = {"name": a.name, "version": a.version, "workshop": a.workshop, "game_line": a.game_line,
            "source": a.source, "stands_in": [x.strip() for x in a.stands_in.split(",") if x.strip()]}
    n = write_table(Path(a.build), Path(a.out), prov)
    print(f"wrote {n} genes file(s) and table.toml to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
