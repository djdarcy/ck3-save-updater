"""How well does Crusader Kings III convert a save itself? A scorecard of a save against the game's own re-save of it.

The standing first step of every big game update (the Director, 2026-11-17): before any design, load the current
golden save in the new game version, save it, and score the pair. Every top-level section and every database of 20 or
more entries is read by id and by depth-1 field, and each database is put in one of four classes:

  kept        the entries are byte-identical (at least 99% of those in both saves)
  re-encoded  the entries are all still there with the same fields, but written differently (the game renumbering an
              index after its definitions moved: a field changed in nearly every entry is usually this)
  dropped     entries or fields the old save had are gone (more than 1% of the ids, or any field): the work list
  built new   a database the old save did not have: what the new version scaffolds by itself

Nested shapes below depth 1 (a holding's buildings) are not read here; probe them separately.

Run a control pair first: two saves that differ in a few known entries (e.g. a save and the same save after one
`ck3update edit`). Its scorecard must show those entries and nothing else, or the numbers mean nothing.

djdarcy 2026-11-17: "How good of a job did CK3 do migrating the v17 golden or did it not really do anything? Or did it
break things in the process that we are now having to fix?" First run (1.20.1.2 -> 1.21.0): 98.6% of ids kept, 19 new
sections, the player's built state dropped. Notes: the vault's measure note 2026-11-17__17-43-59.

Run: python -I -X utf8 scripts/conversion_scorecard.py <old save> <new save> [--sample N]
Reads only; writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator._vendor.savediff import keys as K  # noqa: E402
from ck3_save_migrator._vendor.savediff import text as T  # noqa: E402

KEPT, REENCODED, DROPPED, NEW = "kept", "re-encoded", "dropped", "built new"


def _entries(g: bytes, idx, path: str) -> dict:
    b = T.locate(idx, path)
    if b is None:
        return {}
    try:
        return {e.key.decode(): e for e in K._entries(g, b) if e.key}
    except T.SaveTextError:
        return {}


def _fields(g: bytes, e) -> dict | None:
    out: dict = {}
    try:
        for c in T.iter_children(g, *e.body):
            if c.key:
                out.setdefault(c.key.decode("utf-8", "replace"), []).append(g[c.value_start:c.value_end])
    except T.SaveTextError:
        return None
    return out


def score(go: bytes, gn: bytes, sample: int = 3000) -> dict:
    """The scorecard of two gamestates: sections removed and added, and one row per database."""
    io, inn = T.SectionIndex(go), T.SectionIndex(gn)
    so, sn = set(io.top), set(inn.top)
    rows = []
    for p in sorted(set(K.database_paths(go, io)) | set(K.database_paths(gn, inn))):
        eo, en = _entries(go, io, p), _entries(gn, inn, p)
        kept = [k for k in eo if k in en]
        same = sum(1 for k in kept if go[eo[k].open:eo[k].close] == gn[en[k].open:en[k].close])
        fo, fn = K.field_coverage(go, io, p)["fields"], K.field_coverage(gn, inn, p)["fields"]
        changed: collections.Counter = collections.Counter()
        n_s = 0
        for k in kept[::max(1, len(kept) // sample) if kept else 1]:
            a, b = _fields(go, eo[k]), _fields(gn, en[k])
            if a is None or b is None:
                continue
            n_s += 1
            changed.update(f for f in set(a) & set(b) if a[f] != b[f])
        dropped_fields = sorted(f for f in fo if f not in fn)
        gone = len(eo) - len(kept)
        if not eo:
            cls = NEW
        elif dropped_fields or gone > 0.01 * len(eo):
            cls = DROPPED
        elif same >= 0.99 * len(kept):
            cls = KEPT
        else:
            cls = REENCODED
        rows.append({"path": p, "old": len(eo), "new": len(en), "kept": len(kept), "identical": same,
                     "gone": gone, "added": len(en) - len(kept), "fields_dropped": dropped_fields,
                     "fields_added": sorted(f for f in fn if f not in fo), "class": cls,
                     "changed": [(f, c / n_s) for f, c in changed.most_common(4)] if n_s else []})
    return {"sections_removed": sorted(so - sn), "sections_added": sorted(sn - so), "databases": rows}


def verdict(card: dict) -> str:
    """One line for release notes: what the game keeps, re-encodes, drops and builds."""
    rows = card["databases"]
    by = collections.Counter(r["class"] for r in rows)
    old = sum(r["old"] for r in rows)
    kept = sum(r["kept"] for r in rows if r["old"])
    drops = [r["path"] for r in rows if r["class"] == DROPPED]
    drops += [s for s in card["sections_removed"] if s not in drops]      # a removed section may be a dropped db too
    return (f"the game's own conversion keeps {kept / max(1, old):.1%} of entries by id; databases: {by[KEPT]} kept, "
            f"{by[REENCODED]} re-encoded, {by[DROPPED]} dropping something, {by[NEW]} built new "
            f"(+{len(card['sections_added'])} new sections); drops: {', '.join(drops) or 'none'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("old", help="the save before the game converted it")
    ap.add_argument("new", help="the game's own re-save of it, in the new version")
    ap.add_argument("--sample", type=int, default=3000, help="ids per database read field by field (default 3000)")
    a = ap.parse_args(argv)
    from ck3_save_migrator.savefile import read_save
    card = score(read_save(a.old).gamestate, read_save(a.new).gamestate, a.sample)
    print(f"sections removed: {card['sections_removed'] or '-'}")
    print(f"sections added:   {card['sections_added'] or '-'}")
    print("\nclass | path | old -> new | kept (identical) | gone / added | fields dropped | fields added | "
          "most-changed fields")
    order = {DROPPED: 0, NEW: 1, REENCODED: 2, KEPT: 3}
    for r in sorted(card["databases"], key=lambda r: (order[r["class"]], r["path"])):
        ch = ", ".join(f"{f} {s:.0%}" for f, s in r["changed"]) or "-"
        print(f"{r['class']} | {r['path']} | {r['old']} -> {r['new']} | {r['kept']} ({r['identical']}) | "
              f"{r['gone']} / {r['added']} | {', '.join(r['fields_dropped']) or '-'} | "
              f"{', '.join(r['fields_added']) or '-'} | {ch}")
    print("\n" + verdict(card))
    return 0


if __name__ == "__main__":
    sys.exit(main())
