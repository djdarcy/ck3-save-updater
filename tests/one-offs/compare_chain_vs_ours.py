"""The engine's own conversion (the U13 chain: 1.8.1 -> 1.18.4 -> 1.19.0 -> 1.20.1.2) against ours, on content.

LEFT = the chain's 1.20 save; RIGHT = our migration output after one 1.20 save-and-reload. Both are 1.20 text saves.
  1. Titles: how many landed titles each holds, how many are held (have holder=), and of the titles LEFT added
     beyond the original, how many are held in LEFT and in RIGHT.
  2. Rites: for every character id living in both, the rite each save gives it, compared by the rite's TEMPLATE name
     (rite ids are indices into each save's own rites database, so ids alone do not compare).
  3. Faiths likewise, through rites/database -> faith -> faiths/database template.

Usage: python -I tests/one-offs/compare_chain_vs_ours.py <base 1.8.1.ck3> <left 1.20.ck3> <right 1.20.ck3>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(p):
    raw = Path(p).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(p).gamestate


def field(blob, name):
    m = re.search(rb"[\n\t]" + name + rb"=(\"[^\"]*\"|[^\s{}]+)", blob)   # 1.20 writes some fields after a tab
    return m.group(1).strip(b'"') if m else None


def db(g, path):
    b = gs.locate(g, path)
    return {e.key: g[e.start:e.end] for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}


def titles(g):
    t = db(g, "landed_titles/landed_titles")
    return {field(v, b"key"): (field(v, b"holder") is not None) for v in t.values()}


def rite_names(g):
    rites = db(g, "rites/database")
    faiths = db(g, "faiths/database")
    fname = {k: (field(v, b"faith_type") or field(v, b"tag")) for k, v in faiths.items()}   # built-in: faith_type; custom: tag
    return {k: (field(v, b"rite_type"), fname.get(field(v, b"faith"))) for k, v in rites.items()}


def living(g):
    b = gs.locate(g, "living")
    return {e.key: field(g[e.start:e.end], b"rite") for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()}


def main():
    base, left, right = (load(p) for p in sys.argv[1:4])
    tb, tl, tr = titles(base), titles(left), titles(right)
    added = [k for k in tl if k not in tb]
    print(f"TITLES: base {len(tb):,}  left {len(tl):,} (held {sum(tl.values()):,})  "
          f"right {len(tr):,} (held {sum(tr.values()):,})")
    print(f"  titles the engine added: {len(added):,}; held in left {sum(tl[k] for k in added):,}; "
          f"present in right {sum(1 for k in added if k in tr):,}, held in right {sum(1 for k in added if tr.get(k)):,}")
    only_r = [k for k in tr if k not in tl]
    print(f"  titles only in right: {len(only_r):,} {[k.decode() if k else None for k in only_r[:8]]}")
    only_l = [k for k in tl if k not in tr]
    print(f"  titles only in left: {len(only_l):,} {[k.decode() if k else None for k in only_l[:8]]}")

    rl, rr = rite_names(left), rite_names(right)
    ll, lr = living(left), living(right)
    both = [k for k in ll if k in lr]
    c, faith_c, examples = Counter(), Counter(), []
    for k in both:
        a, b = rl.get(ll[k], (None, None)), rr.get(lr[k], (None, None))
        c["same rite" if a[0] == b[0] else "different rite"] += 1
        faith_c["same faith" if a[1] == b[1] else "different faith"] += 1
        if a[0] != b[0]:
            examples.append((a, b))
    print(f"\nRITES: characters living in both: {len(both):,}")
    print(f"  {dict(c)}   {dict(faith_c)}")
    pairs = Counter((a[0], b[0]) for a, b in examples)
    print("  most common (engine rite -> our rite):")
    for (a, b), n in pairs.most_common(12):
        print(f"    {n:>6,}  {a!s:>32} -> {b!s}")
    fpairs = Counter((a[1], b[1]) for a, b in examples if a[1] != b[1])
    print("  faith disagreements (engine faith -> our faith):")
    for (a, b), n in fpairs.most_common(10):
        print(f"    {n:>6,}  {a!s:>32} -> {b!s}")


if __name__ == "__main__":
    main()
