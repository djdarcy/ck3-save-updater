"""Unit 1 decisive probe (director 07:4x): how does the engine allocate ids between two saves of one campaign?

For an EARLIER and a LATER save (same campaign, same game version), per space:
  (1) new ids (in later, not in earlier): is their low-24 index above the earlier save's max index (fresh), or a
      reused hole (an index the earlier save had under another id, or had not at all), and is the top byte then
      the hole's previous top byte + 1?
  (2) ids present in both but in different sections, and indices present in both under a different top byte;
  (3) scalars (top-level or meta, `key=<int>` at depth <= 1) whose value changed by about the number of new ids;
  (4) the same for titles and houses.
Examples printed in hex.

Usage: python -I tests/one-offs/measure_unit1_id_allocation.py <earlier.ck3> <later.ck3>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

LOW = 0xFFFFFF
SPACES = {
    "character": ["living", "dead_unprunable", "characters/dead_prunable"],
    "title": ["landed_titles/landed_titles"],
    "house": ["dynasties/dynasty_house"],
    "dynasty": ["dynasties/dynasties"],
    "artifact": ["artifacts/artifacts"],
    "council_task": ["council_task_manager/active"],
}
SHALLOW = re.compile(rb"(?m)^\t?([A-Za-z_][\w.]*)=(-?\d+)\s*$")


def sections(g: bytes, paths: list[str]) -> dict[int, str]:
    out = {}
    for p in paths:
        try:
            b = gs.locate(g, p)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if e.key and e.key.isdigit():
                out[int(e.key)] = p
    return out


def h(i: int) -> str:
    return f"0x{i:08X}(g{i >> 24},i{i & LOW})"


def shallow_scalars(g: bytes) -> dict[str, int]:
    out = {}
    for m in SHALLOW.finditer(g):
        k = m.group(1).decode()
        if k not in out:
            out[k] = int(m.group(2))
    return out


def main():
    a_path, b_path = sys.argv[1], sys.argv[2]
    A = sf.read_save(a_path).gamestate
    B = sf.read_save(b_path).gamestate
    print(f"earlier: {Path(a_path).name}\nlater:   {Path(b_path).name}")
    new_total = {}
    for sp, paths in SPACES.items():
        a, b = sections(A, paths), sections(B, paths)
        a_idx = {}
        for i in a:
            a_idx.setdefault(i & LOW, []).append(i)
        amax = max((i & LOW for i in a), default=-1)
        new = [i for i in b if i not in a]
        gone = [i for i in a if i not in b]
        fresh = [i for i in new if (i & LOW) > amax]
        reuse_known = [i for i in new if (i & LOW) <= amax and (i & LOW) in a_idx]
        reuse_hole = [i for i in new if (i & LOW) <= amax and (i & LOW) not in a_idx]
        plus1 = [i for i in reuse_known if any((i >> 24) == (j >> 24) + 1 for j in a_idx[i & LOW])]
        moved = Counter((a[i], b[i]) for i in a if i in b and a[i] != b[i])
        new_total[sp] = len(new)
        print(f"\n== {sp}: earlier {len(a):,} (max index {amax:,}), later {len(b):,}; new {len(new):,}, gone {len(gone):,}")
        print(f"   new with index above earlier max (fresh): {len(fresh):,}; index reused from an earlier id: "
              f"{len(reuse_known):,} (top byte = earlier's +1: {len(plus1):,}); index in a hole absent earlier: "
              f"{len(reuse_hole):,}")
        print(f"   top bytes of new ids: {dict(Counter(i >> 24 for i in new).most_common(8))}")
        if fresh:
            print(f"   fresh e.g. {[h(i) for i in sorted(fresh)[:4]]}")
        if reuse_known:
            ex = sorted(reuse_known)[:4]
            print(f"   reused e.g. {[(h(i), [h(j) for j in a_idx[i & LOW]]) for i in ex]}")
        if reuse_hole:
            print(f"   hole e.g. {[h(i) for i in sorted(reuse_hole)[:4]]}")
        print(f"   ids in both, section moved: {dict(moved)}")
        if gone:
            print(f"   gone e.g. {[(h(i), a[i]) for i in sorted(gone)[:4]]}")
    sa, sb = shallow_scalars(A), shallow_scalars(B)
    print("\n== shallow scalars (depth <= 1) that changed")
    for k in sorted(set(sa) & set(sb)):
        if sa[k] != sb[k]:
            d = sb[k] - sa[k]
            near = [sp for sp, n in new_total.items() if n and abs(d - n) <= max(2, n // 10)]
            print(f"   {k}: {sa[k]} -> {sb[k]} (delta {d}){'  ~ new ' + ','.join(near) if near else ''}")


if __name__ == "__main__":
    main()
