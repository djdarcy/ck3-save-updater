"""Unit 4a: how the 1.8.1 save's 103 faiths resolve against CK3 1.20's religion data.

Usage: python tests/one-offs/measure_unit4a.py            (from the project root; ~1 min)
Writes the long outputs (parent-faith blocks, faith 102, the full table) to
private/data/probe/unit4a/ and prints the summaries.
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
REF = ROOT / "private/data/extracted/ref_1_20_persia_867/gamestate"
REL = Path(r"E:\SteamLibrary\steamapps\common\Crusader Kings III\game\common\religion")
OUT = ROOT / "private/data/probe/unit4a"
OUT.mkdir(parents=True, exist_ok=True)


def strip_comments(b: bytes) -> bytes:
    out = []
    for line in b.split(b"\n"):
        # a '#' outside quotes starts a comment
        q = False
        for i, ch in enumerate(line):
            if ch == 0x22:
                q = not q
            elif ch == 0x23 and not q:
                line = line[:i]
                break
        out.append(line)
    return b"\n".join(out)


def script_blocks(folder: Path):
    """(file, key, body bytes) for every top-level block in folder/*.txt."""
    for f in sorted(folder.glob("*.txt")):
        data = strip_comments(f.read_bytes().lstrip(b"\xef\xbb\xbf"))
        for b in gs.iter_entries(data, 0, len(data)):
            if b.key:
                yield f.name, b.key.decode(), data, b


def val(data, block, key):
    hits = gs.find_keys(data, block, key)
    return data[hits[0].value_start:hits[0].value_end].decode().strip('"') if hits else None


def tokens_in(data, block, key):
    hits = gs.find_keys(data, block, key)
    if not hits or hits[0].block is None:
        return []
    return [data[c.start:c.end].decode().strip('"') for c in gs.iter_children(data, *hits[0].block.body) if c.key is None]


# ------------------------------------------------------------------ 1.20 game data
faith_types, faith_order, faith_doctr = {}, [], {}
for fname, key, data, b in script_blocks(REL / "faith_types"):
    faith_types[key] = {"file": fname, "religion": None}
    faith_order.append(key)
    fd = gs.find_keys(data, b, "faith_details")
    if fd and fd[0].block:
        faith_types[key]["religion"] = val(data, fd[0].block, "religion")
    faith_doctr[key] = set(tokens_in(data, b, "doctrines")) | set(tokens_in(data, b, "tenets"))
rite_types, rite_order, rite_doctr = {}, [], {}
for fname, key, data, b in script_blocks(REL / "rite_types"):
    rite_types[key] = {"file": fname, "faith": val(data, b, "faith")}
    rite_order.append(key)
    rite_doctr[key] = set(tokens_in(data, b, "doctrines")) | set(tokens_in(data, b, "tenets"))
religion_types = {}
for fname, key, data, b in script_blocks(REL / "religion_types"):
    religion_types[key] = fname
print(f"1.20 game: {len(faith_types)} faith_types, {len(rite_types)} rite_types, {len(religion_types)} religion_types")

# ------------------------------------------------------------------ the 1.8.1 save
old = OLD.read_bytes()
faiths_blk = gs.locate(old, "religion/faiths")
religions_blk = gs.locate(old, "religion/religions")
rel_by_id = {r.key.decode(): val(old, r, "template") for r in gs.iter_entries(old, *religions_blk.body)}
faiths = []
for f in gs.iter_entries(old, *faiths_blk.body):
    faiths.append({"id": f.key.decode(), "template": val(old, f, "template"), "name": val(old, f, "name"),
                   "religion": rel_by_id.get(val(old, f, "religion") or "", val(old, f, "religion")),
                   "doctrines": tokens_in(old, f, "doctrine") or [old[c.value_start:c.value_end].decode()
                                                                 for c in gs.find_keys(old, f, "doctrine")],
                   "block": (f.start, f.end)})
living = gs.find_section(old, "living")
char_faith = Counter()
for e in gs.iter_entries(old, *living.body):
    for c in gs.find_keys(old, e, "faith"):
        char_faith[old[c.value_start:c.value_end].decode()] += 1
counties = gs.locate(old, "county_manager/counties")
county_faith = Counter()
for e in gs.iter_entries(old, *counties.body):
    for c in gs.find_keys(old, e, "faith"):
        county_faith[old[c.value_start:c.value_end].decode()] += 1


def classify(t: str):
    if t in faith_types:
        return "faith_type", t
    if t in rite_types:
        return "rite_type", rite_types[t]["faith"]
    if f"{t}_rite" in rite_types:
        return "_rite", rite_types[f"{t}_rite"]["faith"]
    return "none", None


rows = []
for f in faiths:
    cls, parent = classify(f["template"])
    rows.append({**{k: f[k] for k in ("id", "template", "name", "religion")}, "class": cls, "parent": parent,
                 "living": char_faith.get(f["id"], 0), "counties": county_faith.get(f["id"], 0)})
(OUT / "faith_table.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
print(f"\n1.8.1 save: {len(faiths)} faiths; living with faith= {sum(char_faith.values()):,}; counties with faith= {sum(county_faith.values()):,}")
print("class counts:", dict(Counter(r["class"] for r in rows)),
      "| living by class:", {k: sum(r["living"] for r in rows if r["class"] == k) for k in ("faith_type", "rite_type", "_rite", "none")},
      "| counties by class:", {k: sum(r["counties"] for r in rows if r["class"] == k) for k in ("faith_type", "rite_type", "_rite", "none")})
print(f"\n{'id':>4} {'template':24} {'class':10} {'parent / 1.20 key':22} {'living':>7} {'counties':>8}  religion / name")
for r in sorted(rows, key=lambda r: (-r["living"], r["id"])):
    print(f"{r['id']:>4} {r['template']:24} {r['class']:10} {str(r['parent'] if r['class'] != 'faith_type' else r['template']):22} "
          f"{r['living']:>7,} {r['counties']:>8,}  {r['religion']}{' / ' + r['name'] if r['name'] else ''}")

# ------------------------------------------------------------------ 2. missing parent faiths
templates = {r["template"] for r in rows}
needed = defaultdict(list)
for r in rows:
    if r["class"] in ("rite_type", "_rite") and r["parent"] not in templates:
        needed[r["parent"]].append(r["template"])
ref = REF.read_bytes()
ref_faiths = {val(ref, f, "tag"): (f.key.decode(), f) for f in gs.iter_entries(ref, *gs.locate(ref, "faiths/database").body)}
print(f"\n2. parent faiths needed by matched rites but absent from the save: {len(needed)}")
with (OUT / "parent_faith_blocks.txt").open("w", encoding="utf-8") as fh:
    for parent, kids in sorted(needed.items(), key=lambda kv: -len(kv[1])):
        refid, blk = ref_faiths.get(parent, (None, None))
        print(f"  {parent:22} <- {len(kids):>2} rites ({', '.join(kids[:6])}{'...' if len(kids) > 6 else ''}); "
              f"religion {faith_types.get(parent, {}).get('religion')}; reference id {refid}")
        if blk:
            fh.write(f"##### {parent} (reference faiths/database id {refid})\n")
            fh.write(ref[blk.start:blk.end].decode(errors="replace") + "\n\n")

# ------------------------------------------------------------------ 3. faith 102
f102 = next(f for f in faiths if f["id"] == "102")
(OUT / "faith_102.txt").write_text(old[f102["block"][0]:f102["block"][1]].decode(errors="replace"), encoding="utf-8")
d102 = set(f102["doctrines"])
print(f"\n3. faith 102: template {f102['template']}, name {f102['name']}, religion {f102['religion']}, "
      f"{len(d102)} doctrines/tenets; living {char_faith.get('102', 0):,}, counties {county_faith.get('102', 0):,}")
scores = []
for k, dset in list(rite_doctr.items()) + list(faith_doctr.items()):
    if dset:
        scores.append((len(d102 & dset) / len(d102 | dset), k, "rite" if k in rite_doctr else "faith", sorted(d102 & dset)))
for s, k, kind, common in sorted(scores, reverse=True)[:6]:
    print(f"   {kind:5} {k:28} jaccard {s:.2f}  shared {len(common)}: {', '.join(common[:8])}")
print("   faith 102 doctrines:", ", ".join(sorted(d102)))

# ------------------------------------------------------------------ 4. the four unmatched
print("\n4. unmatched templates in game/common/religion:")
for t in sorted(r["template"] for r in rows if r["class"] == "none"):
    hits = []
    for f in REL.rglob("*.txt"):
        for i, line in enumerate(f.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if re.search(rf"\b{re.escape(t)}\b", line):
                hits.append(f"{f.relative_to(REL)}:{i}: {line.strip()[:90]}")
    print(f"  {t}: {len(hits)} hits")
    for h in hits[:6]:
        print(f"     {h}")

# ------------------------------------------------------------------ 5. numbering
ref_ids = [(int(f.key), val(ref, f, "faith_type") or val(ref, f, "tag")) for f in gs.iter_entries(ref, *gs.locate(ref, "faiths/database").body)]
order_pos = {k: i for i, k in enumerate(faith_order)}
seq = [order_pos.get(k, -1) for _, k in sorted(ref_ids)]
print(f"\n5. reference faiths/database: {len(ref_ids)} ids {min(i for i, _ in ref_ids)}..{max(i for i, _ in ref_ids)}; "
      f"ids follow faith_types file order: {seq == sorted(seq)}; first ids: {[k for _, k in sorted(ref_ids)[:6]]}; "
      f"faith_types order: {faith_order[:6]}")
ref_rites = [(int(r.key), val(ref, r, "rite_type")) for r in gs.iter_entries(ref, *gs.locate(ref, "rites/database").body)]
rpos = {k: i for i, k in enumerate(rite_order)}
rseq = [rpos.get(k, -1) for _, k in sorted(ref_rites)]
print(f"   rites/database: {len(ref_rites)} ids {min(i for i, _ in ref_rites)}..{max(i for i, _ in ref_rites)}; "
      f"follow rite_types file order: {rseq == sorted(rseq)}; rites without rite_type: {sum(1 for _, k in ref_rites if not k)}")
rite_ids = {str(i) for i, _ in ref_rites}
ref_living = gs.find_section(ref, "living")
cr = Counter()
bad = 0
for e in gs.iter_entries(ref, *ref_living.body):
    for c in gs.find_keys(ref, e, "rite"):
        v = ref[c.value_start:c.value_end].decode()
        cr[v] += 1
        bad += v not in rite_ids
print(f"   reference living rite= values: {sum(cr.values()):,} on {len(cr)} distinct ids; not in rites/database: {bad}")
rc = Counter(ref[c.value_start:c.value_end].decode() for e in gs.iter_entries(ref, *gs.locate(ref, 'county_manager/counties').body)
             for c in gs.find_keys(ref, e, "rite"))
print(f"   reference counties: rite= {sum(rc.values()):,}; faith= "
      f"{sum(1 for e in gs.iter_entries(ref, *gs.locate(ref, 'county_manager/counties').body) for _ in gs.find_keys(ref, e, 'faith'))}")
customs = [(f.key.decode(), val(ref, f, "tag"), val(ref, f, "historical")) for f in gs.iter_entries(ref, *gs.locate(ref, "faiths/database").body)
           if val(ref, f, "historical") != "yes"]
print(f"   reference faiths not historical=yes: {customs[:5]}")

# ------------------------------------------------------------------ side: dynasty house template keys
houses = None
for path in ("dynasties/dynasty_house", "dynasties/houses"):
    try:
        houses = gs.locate(old, path)
        break
    except gs.GamestateError:
        continue
if houses:
    keys = Counter()
    for h in gs.iter_entries(old, *houses.body):
        k = val(old, h, "key")
        keys[k] += 1
    dup = {k: n for k, n in keys.items() if n > 1}
    print(f"\nside: {sum(keys.values()):,} dynasty houses; key=\"\" on {keys.get('', 0)}; "
          f"duplicate keys: {dict(list(dup.items())[:8])}")
print(f"\nfull outputs in {OUT}")
