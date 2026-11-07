"""poc for the built-in gene tables: the layout R19 builds from names-only tables must equal the layout from the
real build folders (gene names, DNA order, category, every template's index). Usage: python -I gene_table_poc.py
<tables folder> (holding vanilla_1.8.2, cfp_3.1.11, epe_1.6.0 written by scripts/gene_table.py)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import dna

T = Path(sys.argv[1])
D = ROOT / "private" / "data"
real = {"vanilla": D / "versions/1.8.2/game", "cfp": D / "originals/mods-2023/cfp_3.1.11",
        "epe": D / "originals/mods-2023/epe_1.6.0"}
tab = {"vanilla": T / "vanilla_1.8.2", "cfp": T / "cfp_3.1.11", "epe": T / "epe_1.6.0"}
fails = 0
for arm in (["vanilla"], ["vanilla", "cfp", "epe"], ["vanilla", "epe"]):
    a = dna.build_layout("real", [(k, real[k]) for k in arm])
    b = dna.build_layout("table", [(k, tab[k]) for k in arm])
    key = lambda L: [(g["name"], g["cat"], sorted(g["tidx_by_name"].items())) for g in L.genes]
    ka, kb = key(a), key(b)
    diff = [i for i, (x, y) in enumerate(zip(ka, kb)) if x != y]
    ok = ka == kb
    fails += not ok
    print(f"{'+'.join(arm):18} real {a.places} genes, table {b.places} genes, templates "
          f"{sum(len(g['tidx_by_name']) for g in a.genes)}/{sum(len(g['tidx_by_name']) for g in b.genes)}: "
          f"{'IDENTICAL' if ok else f'DIFFER at {diff[:5]}'}")
# known-answer control: a deliberately wrong table must be caught
c = dna.build_layout("ctl", [("vanilla", tab["vanilla"]), ("epe", tab["epe"])])
r = dna.build_layout("real", [("vanilla", real["vanilla"]), ("cfp", real["cfp"]), ("epe", real["epe"])])
print("control (table without CFP vs real with CFP):", "caught" if [g["name"] for g in c.genes] != [g["name"] for g in r.genes]
      or any(x["tidx_by_name"] != y["tidx_by_name"] for x, y in zip(c.genes, r.genes)) else "NOT CAUGHT")
sys.exit(1 if fails else 0)
