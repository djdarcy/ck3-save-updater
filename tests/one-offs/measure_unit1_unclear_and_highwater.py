"""Unit 1: settle the unclear fields, and look for an allocator high-water mark.

1. diplo_centers values: title ids (what kind of title) or province ids?
2. culture_marker: equal to the culture's own id, or something else?
3. vassal contract allegiance: distinct values, and do they look like characters (same as liege/vassal)?
4. High-water marks (director 07:40): every scalar `key=<int>` in the save whose value equals, for some
   id space, its max full id, max index, max index + 1, or entry count. Reported with the key and
   where it sits; a real allocator counter would show up as one key hitting one space.

Usage: python -I tests/one-offs/measure_unit1_unclear_and_highwater.py <migrated save gamestate> <ref gamestate>
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402

LOW = 0xFFFFFF
SPACES = {
    "character": ["living", "dead_unprunable", "characters/dead_prunable"],
    "title": ["landed_titles/landed_titles"],
    "dynasty": ["dynasties/dynasties"], "house": ["dynasties/dynasty_house"],
    "artifact": ["artifacts/artifacts"], "memory": ["character_memory_manager/database"],
    "council_task": ["council_task_manager/active"], "court_position": ["court_positions/database"],
    "coat_of_arms": ["coat_of_arms/coat_of_arms_manager_database"], "regiment": ["armies/regiments"],
    "army_regiment": ["armies/army_regiments"], "army": ["armies/armies"], "unit": ["units"],
    "secret": ["secrets/secrets"], "scheme": ["schemes/active"], "war": ["wars/active_wars"],
    "vassal_contract": ["vassal_contracts/active", "vassal_contracts/database"],
    "faction": ["faction_manager/factions"], "story": ["stories/active"],
    "important_action": ["important_action_manager/active"], "activity": ["activities"],
    "mercenary": ["mercenary_company_manager/mercenary_companies"], "culture": ["culture_manager/cultures"],
    "inspiration": ["inspirations_manager/database"], "sieges": ["sieges/sieges"],
}


def ids(g, paths):
    out = set()
    for p in paths:
        try:
            b = gs.locate(g, p)
        except gs.GamestateError:
            continue
        out |= {int(e.key) for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}
    return out


def title_keys(g):
    b = gs.locate(g, "landed_titles/landed_titles")
    out = {}
    for e in gs.iter_entries(g, *b.body):
        if e.key and e.key.isdigit():
            m = re.search(rb'\n\tkey="?([\w\-]+)', g[e.open:e.open + 300])
            out[int(e.key)] = m.group(1).decode() if m else "?"
    return out


def main():
    S = Path(sys.argv[1]).read_bytes()
    R = Path(sys.argv[2]).read_bytes()

    print("== 1. diplo_centers")
    for name, g in (("save", S), ("ref", R)):
        tk = title_keys(g)
        vals = [int(v) for m in re.finditer(rb"diplo_centers=\{([^}]*)\}", g) for v in m.group(1).split()]
        kinds = Counter(tk.get(v, "<not a title>")[:2] for v in vals)
        print(f"  {name}: {len(vals)} values; as title ids their key prefixes: {dict(kinds.most_common(6))}")

    print("== 2. culture_marker vs own id")
    for name, g in (("save", S), ("ref", R)):
        b = gs.locate(g, "culture_manager/cultures")
        eq = tot = 0
        for e in gs.iter_entries(g, *b.body):
            if e.key and e.key.isdigit():
                m = re.search(rb"\n\t+culture_marker=(\d+)", g[e.open:e.close])
                if m:
                    tot += 1
                    eq += int(m.group(1)) == int(e.key)
        print(f"  {name}: culture_marker present {tot}, equal to own id {eq}")

    print("== 3. allegiance")
    vals = Counter(int(m.group(1)) for m in re.finditer(rb"\n\t+allegiance=(\d+)", R))
    print(f"  ref: {sum(vals.values())} values, distinct {len(vals)}: {vals.most_common(8)}")
    chars = ids(R, SPACES["character"])
    print(f"  of distinct values, character ids: {sum(1 for v in vals if v in chars)}")

    print("== 4. high-water marks in the save")
    marks = defaultdict(list)
    for sp, paths in SPACES.items():
        s = ids(S, paths)
        if not s:
            continue
        mx = max(s)
        mi = max(i & LOW for i in s)
        for label, v in (("max id", mx), ("max index", mi), ("max index+1", mi + 1), ("count", len(s))):
            if v > 2000:                     # small numbers match ids of other spaces by coincidence
                marks[v].append(f"{sp} {label}")
    hits = defaultdict(Counter)
    for m in re.finditer(rb"(?m)^\t*([A-Za-z_][\w]*)=(\d+)\s*$", S):
        v = int(m.group(2))
        if v in marks:
            hits[(m.group(1).decode(), v)][m.start() // 10_000_000] += 1
    if not hits:
        print("  no scalar key equals any space's max id, max index, max index+1 or count")
    for (k, v), where in sorted(hits.items(), key=lambda x: -sum(x[1].values()))[:40]:
        print(f"  {k}={v}  x{sum(where.values())}  matches {marks[v]}  (at ~{sorted(where)[:5]} x10MB)")


if __name__ == "__main__":
    main()
