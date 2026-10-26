"""Fit candidate DNA layouts against a save's real DNA strings (U7 decode).

At each DNA place the template bytes (dominant and recessive) can never exceed that gene's highest template
index. A layout that fits has zero IMPOSSIBLE places; 'under' (the save never uses the top template) is allowed.
Tries both gene orders (file order, and grouped by category).

Usage: python -I tests/one-offs/dna_layout_fit.py <save.ck3> NAME=label:dir;label:dir ... [--detail NAME]
"""
import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import dna_layout as D  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    save = sys.argv[1]
    detail = sys.argv[sys.argv.index("--detail") + 1] if "--detail" in sys.argv else None
    specs = [a for a in sys.argv[2:] if "=" in a]
    g = sf.read_save(save).gamestate
    raw = re.findall(rb'[\n\t]dna="([^"]*)"', g)
    dnas = [base64.b64decode(s + b"=" * (-len(s) % 4)) for s in raw]
    print(f"{Path(save).name}: {len(dnas):,} DNA strings, byte lengths {sorted({len(d) for d in dnas})}")
    for a in specs:
        name, rest = a.split("=", 1)
        spec = []
        for part in rest.split(";"):
            label, d = part.split(":", 1) if not re.match(r"^[A-Za-z]:[\\/]", part) else ("vanilla", part)
            spec.append((label, Path(d)))
        genes = D.load_layout(spec)
        for mode in ("file", "grouped"):
            order = D.dna_order(genes, mode)
            bad, lines = D.fit(order, dnas)
            under = sum(1 for ln in lines if ln.endswith("under"))
            print(f"  {name:40} {mode:8} genes {len(order):4} ({4 * len(order)} B)  impossible {bad:3}  under {under:3}")
            if detail == name:
                print("\n".join(lines))


if __name__ == "__main__":
    main()
