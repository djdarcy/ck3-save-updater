"""Unit 5 measurement: does a province number mean the same place in 1.8.1 and 1.20?

WRONG TURN, kept on record: a title's `capital=` in a save is a TITLE id in that save's own numbering
(b_aachen -> its county c_aachen), not a province id. Title ids shift because 1.20 inserts thousands of titles,
so the first section below ("same capital 0") says nothing about provinces. It is still useful for the title
diff (titles only in 1.20 / only in 1.8.1).

The two checks that answer the question:
- holding_types(): the same province id carries the same holding type in both saves for 83% of provinces,
  against 27% by chance and 36-39% at offsets of +-15/+-26.
- barony_provinces(): a full 2022 vanilla landed_titles copy vs 1.20's own: 8,502 of 8,512 baronies (99.9%)
  keep their `province =` number; 10 moved (Hartlepool/Darlington swap, 8 on the old Chinese frontier).
Result: numbering preserved, new provinces appended (max 9,659 -> 13,159).

Usage: python -I tests/one-offs/measure_unit5_provinces.py <old gamestate or .ck3> <1.20 reference gamestate or .ck3>
       [<old landed_titles file> <new game/common/landed_titles folder>]
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(p: str) -> bytes:
    return sf.read_save(p).gamestate if p.endswith(".ck3") else Path(p).read_bytes()


def capitals(g: bytes) -> dict[str, str | None]:
    lt = gs.locate(g, "landed_titles/landed_titles")
    out = {}
    for t in gs.iter_entries(g, *lt.body):
        body = g[t.open:t.close]
        k = re.search(rb'\n\tkey="?([\w\-\']+)', body)
        if not k:
            continue
        c = re.search(rb"\n\tcapital=(\d+)", body)
        out[k.group(1).decode()] = c.group(1).decode() if c else None
    return out


def holding_types(old_g: bytes, new_g: bytes) -> None:
    def types(g):
        pr = gs.locate(g, "provinces")
        out = {}
        for e in gs.iter_entries(g, *pr.body):
            m = re.search(rb'holding=\{[^}]*?\btype="?(\w+)', g[e.open:e.close])
            out[int(e.key)] = m.group(1).decode() if m else None
        return out
    a, b = types(old_g), types(new_g)
    both = [i for i in a if i in b and a[i] and b[i]]
    print(f"holding type, same id: {sum(a[i] == b[i] for i in both) / len(both):.1%} of {len(both):,}")
    for k in (-26, -15, 15, 26):
        pairs = [(i, i + k) for i in both if b.get(i + k)]
        print(f"  offset {k:+d}: {sum(a[x] == b[y] for x, y in pairs) / len(pairs):.1%}")


def barony_provinces(old_file: str, new_dir: str) -> None:
    def read(paths):
        out = {}
        for p in paths:
            t = Path(p).read_bytes().removeprefix(b"\xef\xbb\xbf")
            for m in re.finditer(rb"(b_[\w\-']+)\s*=\s*\{\s*(?:#[^\n]*\n\s*)*province\s*=\s*(\d+)", t):
                out[m.group(1).decode()] = int(m.group(2))
        return out
    a, b = read([old_file]), read(sorted(Path(new_dir).glob("*.txt")))
    both = [k for k in a if k in b]
    moved = [(k, a[k], b[k]) for k in both if a[k] != b[k]]
    print(f"baronies in both: {len(both):,}; same province {len(both) - len(moved):,} "
          f"({(len(both) - len(moved)) / len(both):.1%}); moved: {moved}")
    print(f"max province: old {max(a.values())}, new {max(b.values())}")


def main():
    old_g, new_g = load(sys.argv[1]), load(sys.argv[2])
    holding_types(old_g, new_g)
    if len(sys.argv) > 4:
        barony_provinces(sys.argv[3], sys.argv[4])
    old, new = capitals(old_g), capitals(new_g)
    both = sorted(set(old) & set(new))
    tiers = Counter()
    same, diff, nocap = Counter(), Counter(), Counter()
    diffs = []
    for k in both:
        if k.startswith("x_"):
            continue
        tier = k[:2]
        tiers[tier] += 1
        a, b = old[k], new[k]
        if a is None or b is None:
            nocap[tier] += 1
        elif a == b:
            same[tier] += 1
        else:
            diff[tier] += 1
            diffs.append((k, a, b))
    print(f"titles: 1.8.1 {len(old):,}, 1.20 {len(new):,}, in both {len(both):,}  "
          "(capital = title id, NOT a province: see the docstring)")
    for t in ("e_", "k_", "d_", "c_", "b_", "h_"):
        if tiers[t]:
            print(f"  {t}: {tiers[t]:>6,} in both | same capital {same[t]:>6,} | different {diff[t]:>5,} | no capital {nocap[t]:>5,}")
    print(f"different capitals, examples: {diffs[:15]}")
    big = [d for d in diffs if int(d[2]) > 9660]
    print(f"  of which the 1.20 capital is a new province (> 9,660): {len(big)}; e.g. {big[:8]}")
    only_new = Counter(k[:2] for k in set(new) - set(old) if not k.startswith("x_"))
    only_old = Counter(k[:2] for k in set(old) - set(new) if not k.startswith("x_"))
    print(f"only in 1.20 by tier: {dict(only_new)}")
    print(f"only in 1.8.1 by tier: {dict(only_old)}; e.g. {sorted(k for k in set(old) - set(new) if not k.startswith('x_'))[:12]}")


if __name__ == "__main__":
    main()
