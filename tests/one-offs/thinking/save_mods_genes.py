"""Which of a save's listed mods ship face genes, by name and version, from a Workshop snapshot folder (read only).
For the gene-table goal (S1): the builds the face recovery must cover. Usage:
python -I save_mods_genes.py <save.ck3> <workshop snapshot folder> [<local mods folder> ...]"""
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import dna, savefile as sf

meta = sf.read_save(sys.argv[1]).meta
snap = Path(sys.argv[2])
local = [Path(p) for p in sys.argv[3:]]
for e in dna.mods_listed(meta):
    m = re.fullmatch(r"mod/ugc_(\d+)\.mod", e)
    cands = [snap / m.group(1)] if m else [p / Path(e).stem for p in local] + [p / Path(e).stem.split("_")[0] for p in local]
    d = next((c for c in cands if c.is_dir()), None)
    if d is None:
        print(f"{e:28} not in the archive")
        continue
    desc = d / "descriptor.mod"
    t = desc.read_text(encoding="utf-8-sig", errors="replace") if desc.is_file() else ""
    name = re.search(r'name\s*=\s*"([^"]*)"', t)
    ver = re.search(r'\bversion\s*=\s*"([^"]*)"', t)
    g = len(dna.load_genes([(d.name, d)])) if dna.has_genes(d) else 0
    print(f"{e:28} {name.group(1) if name else '?':40.40} v{ver.group(1) if ver else '?':10} genes {g:4} {d}")
