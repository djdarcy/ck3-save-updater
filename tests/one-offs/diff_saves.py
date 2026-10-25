"""U14 prototype: what does the game change in a save when it loads and re-saves it? (the save-aware difftool)

BASE is a save we wrote; LEFT is the game's own save of it some time later (an autosave). Optional RIGHT is
another output of ours, for the three-way question: for each section the game reshaped in LEFT, does RIGHT have
it in BASE's shape or in LEFT's?

Per top-level section: present in which; size; and for numbered databases (any block whose children are mostly
`<number>={`, two levels deep), entries ALIGNED by stable identity -- titles by key, cultures by
culture_template, everything else by id (the engine keeps a live object's id between saves of one campaign:
measured, translate.py) -- then added / removed / changed, and for the changed ones the top fields by count:
fields added, fields dropped, values changed.

Classification (a heuristic, printed with its reason):
  SCHEMA   a section that appears, disappears or changes shape; a field added to or dropped from at least 90%
           of a database's aligned entries; entries the game wrote twice;
  GAMEPLAY everything else -- births, deaths, values that moved with the calendar or the dice.

Usage: python -I tests/one-offs/diff_saves.py <base.ck3> <left.ck3> [<right.ck3>] [--json out.json]
"""
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import lint as L  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402

SCHEMA_SHARE = 0.9


def gamestate(path: str) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":            # plain-text save (debug-mode autosave)
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def databases(g: bytes, idx: L.SectionIndex) -> dict[str, gs.Block]:
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


def aligned(g: bytes, path: str, blk: gs.Block) -> tuple[dict, Counter]:
    """identity -> entry text, and how many ids appeared more than once (written twice)."""
    rx = {"landed_titles/landed_titles": T._KEY, "culture_manager/cultures": T._TEMPLATE}.get(path)
    out, seen = {}, Counter()
    for e in gs.iter_entries(g, *blk.body):
        if not (e.key and e.key.isdigit()):
            continue
        seen[e.key] += 1
        ident = None
        if rx is not None:
            k = T._depth0(g, e, rx)
            ident = k.decode() if k else None
        out[ident or f"#{e.key.decode()}"] = (e, g[e.start:e.end])
    return out, Counter({k: n for k, n in seen.items() if n > 1})


def fields(g: bytes, e: gs.Block) -> dict[bytes, bytes]:
    """The entry's direct fields: key -> value text (repeated keys joined)."""
    out = defaultdict(list)
    try:
        for c in gs.iter_children(g, e.open + 1, e.close):
            if c.key is not None:
                out[c.key].append(g[c.value_start:c.value_end])
    except gs.GamestateError:
        return {}
    return {k: b"\x00".join(v) for k, v in out.items()}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jpath = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    if jpath in args:
        args.remove(jpath)
    t0 = time.time()
    B, Lf = gamestate(args[0]), gamestate(args[1])
    Rt = gamestate(args[2]) if len(args) > 2 else None
    ib, il = L.SectionIndex(B), L.SectionIndex(Lf)
    ir = L.SectionIndex(Rt) if Rt else None
    report = {"sections": [], "databases": []}
    print(f"read in {time.time() - t0:.0f}s; base {len(B) / 1e6:.0f} MB, left {len(Lf) / 1e6:.0f} MB")

    print("\n== top-level sections")
    names = sorted(set(ib.top) | set(il.top))
    for n in names:
        a, b = ib.top.get(n), il.top.get(n)
        sa = (a.close - a.open) if a else None
        sb = (b.close - b.open) if b else None
        same = a is not None and b is not None and B[a.start:a.end] == Lf[b.start:b.end]
        kind = "SCHEMA: new in left" if a is None else "SCHEMA: gone in left" if b is None else \
            ("unchanged" if same else "changed")
        right = None
        if ir is not None and kind.startswith("SCHEMA"):
            right = "present" if n in ir.top else "absent"
        report["sections"].append({"section": n, "base_bytes": sa, "left_bytes": sb, "class": kind, "right": right})
        if kind != "unchanged":
            print(f"  {n:44} {sa if sa is not None else '-':>12} -> {sb if sb is not None else '-':>12}  {kind}"
                  + (f"  (right: {right})" if right else ""))

    print("\n== numbered databases, entries aligned by identity")
    db_b, db_l = databases(B, ib), databases(Lf, il)
    db_r = databases(Rt, ir) if Rt else {}
    for path in sorted(set(db_b) | set(db_l)):
        if path not in db_b or path not in db_l:
            print(f"  {path:44} only in {'left' if path in db_l else 'base'}  SCHEMA"
                  + (f" (right: {'has it' if path in db_r else 'lacks it'})" if Rt else ""))
            report["databases"].append({"database": path, "only_in": "left" if path in db_l else "base",
                                        "right_has": path in db_r if Rt else None})
            continue
        ea, twice_a = aligned(B, path, db_b[path])
        eb, twice_b = aligned(Lf, path, db_l[path])
        added = [k for k in eb if k not in ea]
        removed = [k for k in ea if k not in eb]
        changed = [k for k in ea.keys() & eb.keys() if ea[k][1] != eb[k][1]]
        f_add, f_drop, f_val = Counter(), Counter(), Counter()
        for k in changed:
            fa, fb = fields(B, ea[k][0]), fields(Lf, eb[k][0])
            for x in fb.keys() - fa.keys():
                f_add[x.decode()] += 1
            for x in fa.keys() - fb.keys():
                f_drop[x.decode()] += 1
            for x in fa.keys() & fb.keys():
                if fa[x] != fb[x]:
                    f_val[x.decode()] += 1
        common = len(ea.keys() & eb.keys())
        schema_fields = {f"+{x}" for x, n in f_add.items() if common and n >= SCHEMA_SHARE * common} | \
                        {f"-{x}" for x, n in f_drop.items() if common and n >= SCHEMA_SHARE * common}
        twice = "written twice in left" if twice_b and not twice_a else ""
        cls = "SCHEMA" if schema_fields or twice else ("unchanged" if not (added or removed or changed) else "GAMEPLAY")
        row = {"database": path, "base": len(ea), "left": len(eb), "added": len(added), "removed": len(removed),
               "changed": len(changed), "class": cls, "schema_fields": sorted(schema_fields), "twice": bool(twice),
               "fields_added": f_add.most_common(10), "fields_dropped": f_drop.most_common(10),
               "values_changed": f_val.most_common(10), "added_e.g.": added[:5], "removed_e.g.": removed[:5]}
        if Rt is not None and schema_fields and path in db_r:
            er, _ = aligned(Rt, path, db_r[path])
            sample = list(er.values())[:200]
            has_new = sum(1 for e, _ in sample if any(f[1:].encode() in fields(Rt, e) for f in schema_fields
                                                       if f.startswith("+")))
            row["right_shape"] = f"{has_new}/{len(sample)} sampled entries have the left-added fields"
        report["databases"].append(row)
        if cls != "unchanged":
            print(f"  {path:44} {len(ea):>7,} -> {len(eb):>7,}  +{len(added):,} -{len(removed):,} ~{len(changed):,}"
                  f"  {cls}{' ' + ', '.join(sorted(schema_fields)) if schema_fields else ''}{' ' + twice if twice else ''}")
            if f_val:
                print(f"      values changed: {f_val.most_common(6)}")
            if f_add:
                print(f"      fields added:   {f_add.most_common(6)}")
            if f_drop:
                print(f"      fields dropped: {f_drop.most_common(6)}")
            if "right_shape" in row:
                print(f"      right: {row['right_shape']}")
    print(f"\ndone in {time.time() - t0:.0f}s")
    if jpath:
        Path(jpath).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
