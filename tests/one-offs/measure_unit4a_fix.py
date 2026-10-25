"""Unit 4a follow-ups: faith 102's nearest 1.20 rite/faith by doctrine overlap, rite id order,
dynasty template keys, and living characters without faith=.

Usage: python tests/one-offs/measure_unit4a_fix.py   (from the project root)
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "one-offs"))
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from measure_unit4a_lib import REL, script_blocks, tokens_in, val  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
REF = ROOT / "private/data/extracted/ref_1_20_persia_867/gamestate"

defs = {}   # key -> (kind, parent faith, doctrine+tenet set)
for kind, folder in (("faith", "faith_types"), ("rite", "rite_types")):
    for fname, key, data, b in script_blocks(REL / folder):
        parent = val(data, b, "faith") if kind == "rite" else key
        defs[(kind, key)] = (parent, set(tokens_in(data, b, "doctrines")) | set(tokens_in(data, b, "tenets")))

old = OLD.read_bytes()
fb = gs.locate(old, "religion/faiths")
f102 = next(f for f in gs.iter_entries(old, *fb.body) if f.key == b"102")
d102 = {old[c.value_start:c.value_end].decode().strip('"') for c in gs.iter_children(old, *f102.body)
        if c.key in (b"doctrine", b"tenet")}
print(f"faith 102: {len(d102)} doctrines/tenets")
scores = sorted(((len(d102 & s) / len(d102 | s) if s else 0, kind, key, parent, sorted(d102 & s))
                 for (kind, key), (parent, s) in defs.items()), reverse=True)
for sc, kind, key, parent, common in scores[:10]:
    print(f"  {kind:5} {key:26} (faith {parent:18}) jaccard {sc:.2f}  shared {len(common)}: {', '.join(common)}")
christ = [(sc, kind, key, common) for sc, kind, key, parent, common in scores if parent == "christian_faith"]
print("  best within christian_faith rites:", [(k, round(s, 2)) for s, _, k, _ in christ[:5]])

ref = REF.read_bytes()
rites = sorted((int(r.key), val(ref, r, "rite_type"), val(ref, r, "faith"))
               for r in gs.iter_entries(ref, *gs.locate(ref, "rites/database").body))
fseq = [int(f) for _, _, f in rites if f and f.isdigit()]
print(f"\nrite ids grouped by faith id order: {fseq == sorted(fseq)}; first 12 (id, rite_type, faith): {rites[:12]}")
print(f"  rites without rite_type: {[r for r in rites if not r[1]]}")
fdb = {f.key.decode(): (val(ref, f, "faith_type"), val(ref, f, "main_rite")) for f in gs.iter_entries(ref, *gs.locate(ref, "faiths/database").body)}
mr = Counter((fid, mrite) for fid, (_, mrite) in fdb.items())
print(f"  faiths with main_rite: {sum(1 for v in fdb.values() if v[1])}/{len(fdb)}; "
      f"christian_faith = {next(((k, v) for k, v in fdb.items() if v[0] == 'christian_faith'), None)}")

dyn = gs.locate(old, "dynasties/dynasties")
keys = Counter(val(old, d, "key") for d in gs.iter_entries(old, *dyn.body))
print(f"\ndynasties: {sum(keys.values()):,}; key=None {keys.get(None, 0):,}; key='' {keys.get('', 0)}; "
      f"duplicated keys: {[(k, n) for k, n in keys.items() if k and n > 1][:10]}")
houses = gs.locate(old, "dynasties/dynasty_house")
hk = Counter()
for h in gs.iter_entries(old, *houses.body):
    for c in gs.iter_children(old, *h.body):
        if c.key in (b"key", b"name", b"localized_name"):
            hk[c.key.decode()] += 1
print(f"houses: child key counts {dict(hk)}")

living = gs.find_section(old, "living")
nofaith = 0
sample = None
keyset = Counter()
for e in gs.iter_entries(old, *living.body):
    kids = [c.key for c in gs.iter_children(old, *e.body)]
    if b"faith" not in kids:
        nofaith += 1
        keyset[b"dynasty_house" in kids] += 1
        if sample is None:
            sample = old[e.start:min(e.end, e.start + 500)]
print(f"\nliving without faith=: {nofaith:,}; of them with dynasty_house: {keyset[True]:,}")
print(sample.decode(errors="replace"))
