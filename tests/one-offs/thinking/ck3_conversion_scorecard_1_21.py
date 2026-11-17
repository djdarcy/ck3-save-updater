"""How well does Crusader Kings III convert a save itself? A scorecard of one save against the game's own re-save.

djdarcy 2026-11-17 ~17:25: "How good of a job did CK3 do migrating the v17 golden or did it not really do anything?
Or did it break things in the process that we are now having to fix?" -- a /test-stats for the game's own upgrade.

Unrestricted (the Director's rule, 16:58: never only where we thought to look): every top-level section, every
database with >= 20 entries, read by key and then by depth-1 field. For ids present in both: identical body, or
changed; per field: equal, changed, dropped (in old, gone in new), added. Nested shapes (a holding's buildings) are
below depth 1 and are covered by the earlier probes (buildings_three_way_1_21.py), not here.

CONTROL: run it on v17 against v17-edits (two 1.20 saves our tool wrote, differing only by djdarcy's edits). Predicted:
every database >= 99% identical by id, no section added or removed. If not, the reader is wrong (ordering, ids),
and the 1.21 numbers mean nothing.

Run: python -I -X utf8 tests/one-offs/thinking/ck3_conversion_scorecard_1_21.py <old save> <new save> [sample]
Reads only; writes nothing.
"""
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator._vendor.savediff import keys as K  # noqa: E402
from ck3_save_migrator._vendor.savediff import text as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def entries(g, idx, path):
    b = T.locate(idx, path)
    if b is None:
        return {}
    try:
        return {e.key.decode(): e for e in K._entries(g, b) if e.key}
    except T.SaveTextError:
        return {}


def fields(g, e):
    out = {}
    try:
        for c in T.iter_children(g, *e.body):
            if c.key:
                out.setdefault(c.key.decode("utf-8", "replace"), []).append(g[c.value_start:c.value_end])
    except T.SaveTextError:
        return None
    return out


def main(old, new, sample="3000"):
    sample = int(sample)
    go, gn = read_save(old).gamestate, read_save(new).gamestate
    io, inn = T.SectionIndex(go), T.SectionIndex(gn)
    so, sn = set(io.top), set(inn.top)
    print(f"sections: old {len(so)}, new {len(sn)}; removed {sorted(so - sn)}; added {sorted(sn - so)}")
    for s in sorted(so & sn):
        a, b = io.top[s], inn.top[s]
        lo, ln = a.close - a.open, b.close - b.open
        if lo and abs(ln - lo) / lo > 0.25 and max(lo, ln) > 20000:
            print(f"   size {s}: {lo:,} -> {ln:,} bytes")

    paths = sorted(set(K.database_paths(go, io)) | set(K.database_paths(gn, inn)))
    print(f"\ndatabases (>= 20 entries in either): {len(paths)}")
    print("path | old n -> new n | ids kept | of kept: identical / changed | fields dropped | fields added | "
          "most-changed fields (share of kept ids, sampled)")
    total = collections.Counter()
    for p in paths:
        eo, en = entries(go, io, p), entries(gn, inn, p)
        kept = [k for k in eo if k in en]
        same = sum(1 for k in kept if go[eo[k].open:eo[k].close] == gn[en[k].open:en[k].close])
        fo, fn = K.field_coverage(go, io, p)["fields"], K.field_coverage(gn, inn, p)["fields"]
        dropped = sorted(f for f in fo if f not in fn)
        added = sorted(f for f in fn if f not in fo)
        changed = collections.Counter()
        step = max(1, len(kept) // sample) if kept else 1
        n_s = 0
        for k in kept[::step]:
            a, b = fields(go, eo[k]), fields(gn, en[k])
            if a is None or b is None:
                continue
            n_s += 1
            for f in set(a) & set(b):
                if a[f] != b[f]:
                    changed[f] += 1
        top = ", ".join(f"{f} {c / n_s:.0%}" for f, c in changed.most_common(4)) if n_s else "-"
        print(f"{p} | {len(eo)} -> {len(en)} | {len(kept)} | {same} / {len(kept) - same} | "
              f"{', '.join(dropped[:6]) or '-'}{' +' + str(len(dropped) - 6) if len(dropped) > 6 else ''} | "
              f"{', '.join(added[:6]) or '-'}{' +' + str(len(added) - 6) if len(added) > 6 else ''} | {top}")
        total["old"] += len(eo)
        total["new"] += len(en)
        total["kept"] += len(kept)
        total["same"] += same
    print(f"\nall databases: {total['old']:,} -> {total['new']:,} entries; kept by id {total['kept']:,}; "
          f"identical {total['same']:,} ({total['same'] / max(1, total['kept']):.1%} of kept)")


if __name__ == "__main__":
    main(*sys.argv[1:4])
