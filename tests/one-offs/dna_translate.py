"""DNA translation between two layouts, by gene NAME and template NAME (U7 decode and POC helper).

A source place is copied into the target place of the gene with the same name. Its template bytes (byte 0 and 2)
are remapped by template name: the source template's name is looked up in the target gene's templates, and the
target's own `index` for that name is written. Values (bytes 1 and 3) are copied as they are. Colour genes (the
first places, category color_genes) are copied whole.

A target gene missing from the source is DEFAULTED: template 0 and value 128 for morph and accessory genes (the
middle of the range), and for colour genes the bytes of the target layout's first gene default (here: 128s).
Source places past the source layout's length (genes the layout does not know) are dropped and counted.

As a library: build(src_order, dst_order) -> Plan; plan.apply(dna_bytes) -> bytes.
As a script: prints the plan's counts for two layouts.
  python -I tests/one-offs/dna_translate.py SRC=label:dir;... DST=label:dir;... [--src-drop name,name]
"""
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dna_layout as D  # noqa: E402


def template_index(gene_file_genes: dict, name: str) -> dict[str, int]:
    return gene_file_genes[name].get("tidx_by_name", {})


@dataclass
class Plan:
    src_len: int
    dst: list
    moves: list = field(default_factory=list)     # (dst place, src place or None, template map or None)
    kept: int = 0
    remapped: int = 0
    defaulted: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    lost_templates: int = 0

    def apply(self, dna: bytes, extra: int = 0) -> bytes:
        out = bytearray()
        for p, sp, tmap in self.moves:
            if sp is None:
                out += bytes([0, 128, 0, 128])
                continue
            b = dna[sp * 4: sp * 4 + 4]
            if tmap is not None:
                b = bytes([tmap.get(b[0], 0), b[1], tmap.get(b[2], 0), b[3]])
            out += b
        return bytes(out)


def build(src: list, dst: list, src_names: dict | None = None) -> Plan:
    plan = Plan(src_len=len(src), dst=dst)
    pos = {g["name"]: i for i, g in enumerate(src)}
    for p, g in enumerate(dst):
        sp = pos.get(g["name"])
        if sp is None:
            plan.defaulted.append(g["name"])
            plan.moves.append((p, None, None))
            continue
        s = src[sp]
        if g["cat"] == "color_genes":
            plan.moves.append((p, sp, None))
            plan.kept += 1
            continue
        smap, dmap = s.get("tidx_by_name", {}), g.get("tidx_by_name", {})
        tmap = {}
        for tname, si in smap.items():
            if tname in dmap:
                tmap[si] = dmap[tname]
            else:
                plan.lost_templates += 1
        if all(k == v for k, v in tmap.items()) and len(tmap) == len(smap):
            plan.kept += 1
        else:
            plan.remapped += 1
        plan.moves.append((p, sp, tmap))
    names = {g["name"] for g in dst}
    plan.dropped = [g["name"] for g in src if g["name"] not in names]
    return plan


def layout(arg: str) -> list:
    name, rest = arg.split("=", 1)
    spec = []
    for part in rest.split(";"):
        label, d = part.split(":", 1) if not re.match(r"^[A-Za-z]:[\\/]", part) else ("vanilla", part)
        spec.append((label, Path(d)))
    return D.dna_order(D.load_layout(spec))


def main():
    specs = [a for a in sys.argv[1:] if "=" in a and not a.startswith("--")]
    src, dst = layout(specs[0]), layout(specs[1])
    if "--src-drop" in sys.argv:
        drop = set(sys.argv[sys.argv.index("--src-drop") + 1].split(","))
        src = [g for g in src if g["name"] not in drop]
    plan = build(src, dst)
    print(f"source {len(src)} genes -> target {len(dst)} genes")
    print(f"  same gene, same templates: {plan.kept}; same gene, templates remapped: {plan.remapped}; "
          f"templates with no target (fall to 0): {plan.lost_templates}")
    print(f"  target genes defaulted (not in source): {len(plan.defaulted)} {plan.defaulted}")
    print(f"  source genes dropped (not in target): {len(plan.dropped)} {plan.dropped}")


if __name__ == "__main__":
    main()
