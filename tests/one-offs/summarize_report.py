"""Summarise a migrate --report JSON: counts per rule plus the details that need eyes.

Usage: python tests/one-offs/summarize_report.py <report.json> [...]
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for path in sys.argv[1:]:
    rep = json.loads(Path(path).read_text(encoding="utf-8"))
    print(f"== {Path(path).name}  (wos shape {rep.get('wos_shape')}, output {Path(rep['output']).name if rep.get('output') else '-'})")
    for r in rep["rules"]:
        print(f"  {r['id']:3} {r['name']:20} matched {r['matched']:>8,} edited {r['edited']:>8,}")
        x = r.get("extra", {})
        if r["id"] == "R11":
            print(f"      by_kind {x.get('by_kind')}")
        if r["id"] == "R8":
            print(f"      stats {x.get('stats')}")
            print(f"      faith heads {x.get('faith_heads')}")
        if r["id"] == "R10":
            for k, v in x.get("custom", {}).items():
                print(f"      custom {k}: {json.dumps(v, ensure_ascii=False)[:900]}")
        if r["id"] == "R9":
            print(f"      by_place {x.get('by_place')}")
            print(f"      unresolved {x.get('unresolved')}")
            t = x.get("table", {})
            for fid in ("102", "9", "10", "44", "11", "23"):
                if fid in t:
                    print(f"      table {fid}: {t[fid]}")
            print(f"      heads_carried {x.get('heads_carried')}")
            print(f"      head_conflicts {x.get('head_conflicts')}")
            print(f"      faith_heads (non-empty) { {k: v for k, v in (x.get('faith_heads') or {}).items() if v} }")
        if r["id"] == "R12":
            print(f"      took {x.get('took')}")
            print(f"      check {x.get('check')}")
    # A6c: living characters per rite, explicit (R9 swap) + inherited (R12), labelled by the faith it belongs to
    by_id = {r["id"]: r.get("extra", {}) for r in rep["rules"]}
    rite_label = {}
    for old, row in (by_id.get("R9", {}).get("table") or {}).items():
        if row.get("rite_id") is not None:
            rite_label.setdefault(str(row["rite_id"]), f"{row.get('faith_type')}/{row.get('rite_type') or 'main'}")
    for old, rec in (by_id.get("R10", {}).get("custom") or {}).items():
        if "rite_id" in rec:
            rite_label[str(rec["rite_id"])] = f"{rec['name']} (faith {rec.get('faith_id')})"
    exp = by_id.get("R9", {}).get("living_explicit_by_rite") or {}
    inh = by_id.get("R12", {}).get("living_inherited_by_rite") or {}
    print("  A6c living by rite (explicit + inherited = total), top 12:")
    for rid in sorted(set(exp) | set(inh), key=lambda k: -(exp.get(k, 0) + inh.get(k, 0)))[:12]:
        e, i = exp.get(rid, 0), inh.get(rid, 0)
        print(f"      rite {rid:>4} {rite_label.get(rid, '?'):40} {e:>7,} + {i:>7,} = {e + i:>7,}")
    lost = rep.get("lost", [])
    kinds = {}
    for l in lost:
        kinds[l.get("what")] = kinds.get(l.get("what"), 0) + 1
    print(f"  lost: {kinds}; first: {lost[:3]}")
    print(f"  assumptions: {rep.get('assumptions')}")
