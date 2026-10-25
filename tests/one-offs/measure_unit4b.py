"""Unit 4b measurements: what R8-R12 depend on.

Usage: python tests/one-offs/measure_unit4b.py   (from the project root)
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "one-offs"))
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from measure_unit4a_lib import REL, strip_comments  # noqa: E402

OLD = ROOT / "private/data/extracted/987_10_27_husband_died/gamestate"
REF = ROOT / "private/data/extracted/ref_1_20_persia_867/gamestate"
old = OLD.read_bytes()
ref = REF.read_bytes()


def walk(data, block, path=(), out=None, depth=0, maxdepth=6):
    """Yield (path, Child) for every scalar child under block, recursively."""
    for c in gs.iter_children(data, *block.body):
        k = (c.key or b"{}").decode(errors="replace")
        if c.block is not None:
            if depth < maxdepth:
                yield from walk(data, c.block, path + (k,), out, depth + 1, maxdepth)
        else:
            yield path + (k,), c


print("== 1. numeric fields in the reference religion / faiths / rites")
id_like = defaultdict(Counter)
samples = {}
for sec in ("religion", "faiths", "rites"):
    blk = gs.find_section(ref, sec)
    for path, c in walk(ref, blk):
        v = ref[c.value_start:c.value_end]
        if re.fullmatch(rb"-?\d+", v) and c.key not in (None,):
            # collapse numeric ids in the path (database ids) to '#'
            p = "/".join("#" if x.isdigit() else x for x in (sec,) + path)
            id_like[p][v.decode()] += 1
            samples.setdefault(p, v.decode())
        elif c.key is None and re.fullmatch(rb"\d+", v):
            p = "/".join("#" if x.isdigit() else x for x in (sec,) + path[:-1]) + "/[list]"
            id_like[p][v.decode()] += 1
for p, cnt in sorted(id_like.items()):
    vals = sorted(cnt, key=lambda x: int(x))
    print(f"  {p:70} n={sum(cnt.values()):>5} distinct={len(cnt):>4} range={vals[0]}..{vals[-1]}")

ref_living = {e.key.decode() for e in gs.iter_entries(ref, *gs.find_section(ref, "living").body)}
ref_dead = {e.key.decode() for e in gs.iter_entries(ref, *gs.find_section(ref, "dead_unprunable").body)}
ref_titles = {e.key.decode() for e in gs.iter_entries(ref, *gs.locate(ref, "landed_titles/landed_titles").body)}
print(f"  (reference: {len(ref_living):,} living ids, {len(ref_dead):,} dead ids, {len(ref_titles):,} title ids)")
for p, cnt in sorted(id_like.items()):
    vals = [v for v in cnt if v not in ("4294967295", "0", "1")]
    if not vals:
        continue
    as_char = sum(1 for v in vals if v in ref_living or v in ref_dead)
    as_title = sum(1 for v in vals if v in ref_titles)
    if as_char or as_title:
        print(f"    {p:68} char-ids {as_char}/{len(vals)}  title-ids {as_title}/{len(vals)}")

print("\n== 2. the dynamic rites (no rite_type)")
rdb = gs.locate(ref, "rites/database")
for r in gs.iter_entries(ref, *rdb.body):
    kids = [c.key for c in gs.iter_children(ref, *r.body)]
    if b"rite_type" not in kids:
        txt = ref[r.start:r.end].decode(errors="replace")
        print(f"  rite {r.key.decode()}: top keys {[k.decode() for k in kids]}")
        print("   " + txt[:1400].replace("\n", "\n   "))
        break
print("  rites/database ids:", sorted(int(r.key) for r in gs.iter_entries(ref, *rdb.body))[-4:])
typed = next(r for r in gs.iter_entries(ref, *rdb.body) if r.key == b"1")
print(f"  a typed rite (1) top keys: {[c.key.decode() for c in gs.iter_children(ref, *typed.body)]}")
data1 = gs.find_keys(ref, typed, "data")[0].block
print(f"  its data keys: {[c.key.decode() if c.key else '?' for c in gs.iter_children(ref, *data1.body)]}")

print("\n== 3. doctrine / tenet keys defined by the 1.20 game")
defined = set()
for folder in ("doctrine_types", "tenet_types"):
    for f in (REL / folder).glob("*.txt"):
        txt = strip_comments(f.read_bytes())
        defined.update(m.group(1).decode() for m in re.finditer(rb"(?m)^\s*([a-z][a-z0-9_]*)\s*=\s*\{", txt))
fb = gs.locate(old, "religion/faiths")
f102 = next(f for f in gs.iter_entries(old, *fb.body) if f.key == b"102")
d102 = [(c.key.decode(), old[c.value_start:c.value_end].decode().strip('"')) for c in gs.iter_children(old, *f102.body)
        if c.key in (b"doctrine", b"tenet")]
kept = [v for _, v in d102 if v in defined]
gone = [v for _, v in d102 if v not in defined]
print(f"  game defines {len(defined):,} doctrine/tenet-ish keys; faith 102 has {len(d102)}: kept {len(kept)}, gone {len(gone)}: {gone}")
print("  faith 102 block keys:", [c.key.decode() for c in gs.iter_children(old, *f102.body) if c.key])

print("\n== 4. every faith reference in the 1.8.1 save (keys faith / secret_faith / religion with integer values)")
faith_ids = {f.key.decode() for f in gs.iter_entries(old, *fb.body)}
hits = Counter()
for m in re.finditer(rb"(?m)^(\t*)(faith|secret_faith|faiths|faith_id|target_faith|religion)=(\d+)\b", old):
    pos = m.start() + len(m.group(1))
    hits[(m.group(2).decode(), len(m.group(1)))] += 1
for (k, ind), n in sorted(hits.items(), key=lambda kv: -kv[1]):
    print(f"  {k:14} indent {ind}: {n:>7,}")
sample_pos = defaultdict(list)
for m in re.finditer(rb"(?m)^(\t*)(faith|secret_faith)=(\d+)\b", old):
    key = (m.group(2).decode(), len(m.group(1)))
    if len(sample_pos[key]) < 40:
        sample_pos[key].append(m.start() + len(m.group(1)))
allpos = [p for v in sample_pos.values() for p in v]
res = gs.child_at(old, allpos)
parents = defaultdict(Counter)
for key, ps in sample_pos.items():
    for p in ps:
        if p in res:
            parents[key][(res[p][0].key or b"{}").decode(errors="replace")] += 1
for key, cnt in parents.items():
    print(f"  parents of {key} (sample of 40): {dict(cnt.most_common(6))}")
tops = defaultdict(Counter)
toplist = [(m.start(), m.group(1).decode()) for m in re.finditer(rb"(?m)^([A-Za-z_][\w.]*)\s*=\s*\{", old)]
import bisect
starts = [s for s, _ in toplist]
for m in re.finditer(rb"(?m)^\t*(faith|secret_faith)=\d+", old):
    i = bisect.bisect_right(starts, m.start()) - 1
    tops[m.group(1).decode()][toplist[i][1] if i >= 0 else "?"] += 1
print("  by top-level section:", {k: dict(v.most_common(10)) for k, v in tops.items()})

print("\n== 5. rite / faith references in the 1.20 reference, by top-level section")
starts_r = [(m.start(), m.group(1).decode()) for m in re.finditer(rb"(?m)^([A-Za-z_][\w.]*)\s*=\s*\{", ref)]
ss = [s for s, _ in starts_r]
rt = defaultdict(Counter)
for m in re.finditer(rb"(?m)^\t*(rite|faith|secret_faith|secret_rite)=\d+", ref):
    i = bisect.bisect_right(ss, m.start()) - 1
    rt[m.group(1).decode()][starts_r[i][1] if i >= 0 else "?"] += 1
print("  ", {k: dict(v.most_common(10)) for k, v in rt.items()})
dead_with_rite = sum(1 for e in gs.iter_entries(ref, *gs.find_section(ref, "dead_unprunable").body)
                     if gs.find_keys(ref, e, "rite"))
print(f"  reference dead_unprunable with rite=: {dead_with_rite:,} of {len(ref_dead):,}")
print("  old religion section children:", [c.key.decode() for c in gs.iter_children(old, *gs.find_section(old, 'religion').body) if c.key])
print("  ref religion section children:", [c.key.decode() for c in gs.iter_children(ref, *gs.find_section(ref, 'religion').body) if c.key])
