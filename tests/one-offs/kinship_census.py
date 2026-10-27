"""U17 input: which kinship fields a save holds per character, by section, and how complete the family graph is.

Per section (living, dead_unprunable, characters/dead_prunable): entries; how many carry each field (the depth
of the field is reported: family_data/<f> or top level); and graph completeness:
  * parents: characters with at least one parent found through some character's child list (CK3 stores children,
    never father/mother), plus real_father;
  * dangling: ids a kinship field names that no character section holds (pruned people);
  * history ids: characters named in character_lookup.
Usage: python -I kinship_census.py <save.ck3> [<save.ck3> ...]
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import gamestate as gs, translate as T  # noqa: E402

FIELDS = (b"child", b"spouse", b"primary_spouse", b"former_spouses", b"concubine", b"concubinist", b"betrothed",
          b"real_father", b"dynasty_house", b"birth", b"date")       # "date" = dead_data/date, the death date
SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
FIELD_RX = {f: re.compile(rb"\n(\t+)" + f + rb"=(?:\{([^}]*)\}|\"?([\w.]+)\"?)") for f in FIELDS}


def census(path):
    g = load(path)
    chars, where = {}, {}
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except Exception:  # noqa: BLE001
            continue
        for e in gs.iter_entries(g, b.open + 1, b.close):
            if e.key and e.key.isdigit():
                i = int(e.key)
                chars.setdefault(i, g[e.start:e.end])
                where.setdefault(i, sec)
    lookup = set(T.character_lookup(g).values()) if hasattr(T, "character_lookup") else set()
    print(f"== {Path(path).name}: {len(chars):,} characters "
          f"({', '.join(f'{s} {sum(1 for v in where.values() if v == s):,}' for s in SECTIONS)}); "
          f"history ids {len(lookup):,}")
    have = defaultdict(Counter)
    depth = defaultdict(Counter)
    parents = defaultdict(set)
    named = Counter()
    dangling = Counter()
    for i, b in chars.items():
        sec = where[i]
        for f, rx in FIELD_RX.items():
            ms = list(rx.finditer(b))
            if f == b"date":
                ms = [m for m in ms if b"dead_data" in b[:m.start()][-400:]]
            if not ms:
                continue
            have[sec][f] += 1
            depth[f][len(ms[0].group(1))] += 1
            if f in (b"child", b"spouse", b"primary_spouse", b"former_spouses", b"concubine", b"concubinist",
                     b"betrothed", b"real_father"):
                ids = [int(x) for m in ms for x in (m.group(2) or m.group(3) or b"").split() if x.isdigit()]
                named[f] += len(ids)
                dangling[f] += sum(1 for x in ids if x not in chars)
                if f == b"child":
                    for k in ids:
                        parents[k].add(i)
                if f == b"real_father":
                    for x in ids:
                        parents[i].add(x)
    print(f"  {'field':16}" + "".join(f"{s.split('/')[-1]:>18}" for s in SECTIONS) + "   depth   named ids  dangling")
    for f in FIELDS:
        row = "".join(f"{have[s][f]:>18,}" for s in SECTIONS)
        d = ",".join(f"{k}" for k, _ in depth[f].most_common(2))
        print(f"  {f.decode():16}{row}   {d:>5} {named[f]:>11,} {dangling[f]:>9,}")
    with_parent = Counter(where[i] for i in chars if parents.get(i))
    print("  characters with a known parent: " + ", ".join(
        f"{s.split('/')[-1]} {with_parent[s]:,} of {sum(1 for v in where.values() if v == s):,}" for s in SECTIONS))
    return chars, where


for p in sys.argv[1:]:
    census(p)
