"""Unit 1 schema discovery: which fields of which kind of block hold ids, and of which id space.

Walks every entry of every numbered database ("kind") in the migrated save and in the 1.20 reference, and
collects each integer-valued field by its normalised path inside the entry (numeric keys -> '#', date keys ->
'<date>', anonymous blocks -> '[]', bare list values -> '*'). Then classifies each (kind, path):

* in the SAVE, ids carry generations (top byte), so a value >= 2^24 is sparse in the 32-bit range; the share of
  such values found in each space's full-id set names the space with little ambiguity ("save best");
* in the REFERENCE, ids are generation 0 and dense from 0, so only consistency can be stated: the spaces whose
  id sets hold >= 99% of the path's values ("ref consistent").

Characters are one space (living + dead_unprunable + characters/dead_prunable, measured as one index space).
Output: a text table per kind, and a JSON file for building the schema.

Usage: python -I tests/one-offs/measure_unit1_field_spaces.py <migrated save gamestate> <reference gamestate> <out.json>
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402

DATE = re.compile(rb"^-?\d+\.\d+\.\d+$")
CHAR_SECTIONS = {"living", "dead_unprunable", "characters/dead_prunable"}
CAP = 300_000   # distinct values kept per path


def databases(g: bytes) -> dict[str, gs.Block]:
    """kind path -> block, for every block whose direct children are mostly numbered entries (2 levels)."""
    idx = L.SectionIndex(g)
    out = {}
    for name, b in idx.top.items():
        cands = [(name, b)]
        try:
            for c in gs.iter_entries(g, *b.body):
                if c.key and not c.key.isdigit():
                    cands.append((f"{name}/{c.key.decode()}", c))
        except gs.GamestateError:
            pass
        for path, blk in cands:
            n = 0
            try:
                for e in gs.iter_entries(g, *blk.body):
                    if e.key and e.key.isdigit():
                        n += 1
                        if n >= 3:
                            break
            except gs.GamestateError:
                continue
            if n >= 3:
                out[path] = blk
    return out


def norm(key: bytes) -> str:
    if key.isdigit():
        return "#"
    if DATE.match(key):
        return "<date>"
    return key.decode("utf-8", "replace")


def walk(g: bytes, start: int, end: int, prefix: str, vals, counts) -> None:
    for c in gs.iter_children(g, start, end):
        if c.key is None:
            key = "[]" if c.block is not None else "*"
        else:
            key = norm(c.key) if c.key else "="
        path = f"{prefix}/{key}" if prefix else key
        if c.block is not None:
            walk(g, *c.block.body, path, vals, counts)
            continue
        tok = g[c.value_start:c.value_end]
        if tok.isdigit():
            counts[path] += 1
            s = vals[path]
            if len(s) < CAP:
                s.add(int(tok))


def collect(g: bytes, dbs: dict[str, gs.Block]):
    """kind -> (entry ids, path -> values, path -> count)."""
    out = {}
    seen_dead = set()
    for kind, blk in dbs.items():
        ids, vals, counts = set(), defaultdict(set), defaultdict(int)
        for e in gs.iter_entries(g, *blk.body):
            if not (e.key and e.key.isdigit()):
                continue
            i = int(e.key)
            if kind == "dead_unprunable":          # 1.20 writes each entry twice; walk one copy
                if i in seen_dead:
                    continue
                seen_dead.add(i)
            ids.add(i)
            walk(g, *e.body, "", vals, counts)
        k = "characters" if kind in CHAR_SECTIONS else kind
        if k in out:
            out[k][0].update(ids)
            for p, v in vals.items():
                out[k][1][p].update(v)
            for p, n in counts.items():
                out[k][2][p] += n
        else:
            out[k] = (ids, vals, counts)
    return out


def main():
    t0 = time.time()
    save_g = Path(sys.argv[1]).read_bytes()
    ref_g = Path(sys.argv[2]).read_bytes()
    save = collect(save_g, databases(save_g))
    print(f"save walked: {len(save)} kinds, {time.time() - t0:.0f}s", flush=True)
    ref = collect(ref_g, databases(ref_g))
    print(f"ref walked: {len(ref)} kinds, {time.time() - t0:.0f}s", flush=True)
    save_ids = {k: v[0] for k, v in save.items()}
    ref_ids = {k: v[0] for k, v in ref.items()}
    report = {}
    for kind in sorted(set(save) | set(ref)):
        sv = save.get(kind, (set(), {}, {}))
        rv = ref.get(kind, (set(), {}, {}))
        paths = sorted(set(sv[1]) | set(rv[1]))
        rows = []
        for p in paths:
            s_vals = sv[1].get(p, set())
            r_vals = rv[1].get(p, set())
            gen = [v for v in s_vals if v >= 1 << 24 and v != 0xFFFFFFFF]
            best = []
            if gen:
                for sp, ids in save_ids.items():
                    h = sum(1 for v in gen if v in ids)
                    if h:
                        best.append((h / len(gen), sp))
                best.sort(reverse=True)
            rc = []
            rr = [v for v in r_vals if v != 0xFFFFFFFF]
            if rr:
                for sp, ids in ref_ids.items():
                    h = sum(1 for v in rr if v in ids)
                    if h / len(rr) >= 0.99:
                        rc.append(sp)
            row = {
                "path": p, "save_n": sv[2].get(p, 0), "ref_n": rv[2].get(p, 0),
                "save_distinct": len(s_vals), "ref_distinct": len(r_vals),
                "save_gen_values": len(gen),
                "save_best": [(round(r, 3), sp) for r, sp in best[:2]],
                "ref_max": max(rr) if rr else None,
                "ref_consistent": rc[:8], "ref_consistent_n": len(rc),
                "ref_sample": sorted(r_vals)[:4],
            }
            rows.append(row)
        report[kind] = rows
        print(f"\n## {kind}  (save entries {len(sv[0]):,}, ref entries {len(rv[0]):,})")
        for r in rows:
            sb = ", ".join(f"{sp} {x:.0%}" for x, sp in r["save_best"]) or "-"
            rc = ",".join(r["ref_consistent"][:4]) + ("..." if r["ref_consistent_n"] > 4 else "")
            print(f"  {r['path'][:58]:58} s={r['save_n']:>8,} r={r['ref_n']:>8,} gen={r['save_gen_values']:>6,}"
                  f"  save:[{sb}]  refmax={r['ref_max']}  ref:[{rc}]")
    Path(sys.argv[3]).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"\nwritten {sys.argv[3]} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
