"""POC (patch day, the Director's ruling 2026-11-17__15-13-04, class 1): can v17's 1.20 buildings be mapped to 1.21
buildings by rules read from the game files alone?

Prediction (written before running): of v17's 19,757 buildings, >= 80% by instance map by
  R1: the key is defined in 1.21's common/buildings (recursive), or
  R2: the key's family (the key without a trailing _<n>) equals a 1.21 key's family.
Negative control: the same rules against an unrelated key set (1.21's common/modifiers keys) -> near 0%.
Positive control: the same rules against 1.20.1.2's own common/buildings -> 100%.
Fallback: < 80% -> a hand successor table (R25's form, one citation per row), sized here by distinct types left.
Run: python -I -X utf8 tests/one-offs/thinking/poc-building-mapping/probe.py <v17.ck3>
"""
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "one-offs" / "thinking"))
from buildings_three_way_1_21 import old_buildings  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NEW = pathlib.Path("E:/SteamLibrary/steamapps/common/Crusader Kings III/game/common")
OLD = ROOT / "private" / "data" / "versions" / "1.20.1.2_public" / "game" / "common"
TOP = re.compile(r"(?m)^([a-z][a-z0-9_]*)\s*=\s*\{")
fam = lambda k: re.sub(r"_\d+$", "", k)  # noqa: E731


def keys(folder):
    return {m.group(1) for f in folder.rglob("*.txt") for m in TOP.finditer(f.read_text("utf-8-sig", "replace"))}


def score(counts, target):
    fams = {fam(k) for k in target}
    hit = collections.Counter()
    for t, n in counts.items():
        hit["R1 same key" if t in target else "R2 same family" if fam(t) in fams else "unmapped"] += n
    return hit


def main(v17):
    counts = collections.Counter(t for v in old_buildings(read_save(v17).gamestate).values() for t in v)
    total = sum(counts.values())
    print(f"v17: {total} buildings, {len(counts)} distinct types")
    for name, target in (("1.21 buildings (the test)", keys(NEW / "buildings")),
                         ("negative control: 1.21 modifiers", keys(NEW / "modifiers")),
                         ("positive control: 1.20.1.2 buildings", keys(OLD / "buildings"))):
        h = score(counts, target)
        mapped = h["R1 same key"] + h["R2 same family"]
        print(f"{name:40} keys={len(target):5}  mapped {mapped}/{total} = {mapped / total:.1%}  {dict(h)}")
    new = keys(NEW / "buildings")
    fams = {fam(k) for k in new}
    left = collections.Counter({t: n for t, n in counts.items() if t not in new and fam(t) not in fams})
    lf = collections.Counter()
    for t, n in left.items():
        lf[fam(t)] += n
    print(f"\nunmapped: {sum(left.values())} buildings, {len(left)} types, {len(lf)} families (the successor table's size)")
    print("largest unmapped families:", lf.most_common(15))
    print("mapped by family (old -> exists in 1.21):",
          sorted({fam(t) for t in counts if t not in new and fam(t) in fams})[:20])


if __name__ == "__main__":
    main(sys.argv[1])
