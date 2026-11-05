"""/measure (djdarcy 2026-11-05, #7 criterion 2): how 1.20 converts a carried 1.8 scheme on first load.
Pairs every scheme in an updated build (old fields) with the game's day-one re-save of it (new fields), and reports
for each old field how it relates to the new ones: kept, dropped, or turned into something. Known-answer check: type,
owner and date must come through unchanged on every paired scheme.
Usage: python -I scheme_conversion_measure.py <build.ck3> <day-one re-save.ck3>"""
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    try:
        return sf.read_save(p).gamestate
    except sf.UnsupportedKindError:
        raw = open(p, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def schemes(d):
    b = gs.locate(d, "schemes/active")
    out = {}
    for e in gs.iter_entries(d, *b.body):
        if not e.key:
            continue
        body = d[e.open + 1:e.close]
        top = dict((k.decode(), v.decode()) for k, v in re.findall(rb"(?m)^\t\t\t(\w+)=([^{\n]*)$", body))
        top["_blocks"] = sorted(set(k.decode() for k in re.findall(rb"(?m)^\t\t\t(\w+)=\{", body)))
        out[e.key] = top
    return out


old, new = schemes(load(sys.argv[1])), schemes(load(sys.argv[2]))
paired = [k for k in old if k in new]
print(f"build {len(old)}, re-save {len(new)}, paired {len(paired)}, gone {len(old) - len(paired)}, "
      f"new in re-save {len(new) - len(paired)}  (reconcile: {len(paired)}+{len(old) - len(paired)}={len(old)})")
ok = Counter()
for k in paired:
    for f in ("type", "owner", "date"):
        ok[f] += old[k].get(f, "").strip('"') == new[k].get(f, "").strip('"')
print("known-answer (unchanged on every paired scheme):", {f: f"{n}/{len(paired)}" for f, n in ok.items()})
fields_old = Counter(f for k in paired for f in old[k] if not f.startswith("_"))
fields_new = Counter(f for k in paired for f in new[k] if not f.startswith("_"))
print("old-only fields:", {f: n for f, n in fields_old.items() if f not in fields_new})
print("new-only fields:", {f: n for f, n in fields_new.items() if f not in fields_old})
print("blocks old->new:", Counter(tuple(old[k]["_blocks"]) for k in paired).most_common(3),
      Counter(tuple(new[k]["_blocks"]) for k in paired).most_common(3))
same = Counter()
for k in paired:
    for f in set(old[k]) & set(new[k]):
        if not f.startswith("_"):
            same[(f, old[k][f] == new[k][f])] += 1
print("shared fields, equal / changed:", sorted(same.items()))
# relationships worth a formula
rel = defaultdict(Counter)
for k in paired:
    o, n = old[k], new[k]
    rel["progress old->new"][(o.get("progress"), n.get("progress"))] += 1
    rel["owner_influence -> ?"][(o.get("owner_influence"), n.get("status"), n.get("phases"), n.get("opportunities"))] += 1
    rel["chance -> ramping/success"][(o.get("chance"), n.get("ramping_success_chance"))] += 1
    rel["update_days"][(o.get("update_days"), n.get("update_days"))] += 1
    rel["secrecy"][(o.get("secrecy"), n.get("secrecy"))] += 1
    rel["last_update"][(n.get("last_update"),)] += 1
for name, c in rel.items():
    print(f"{name}: {len(c)} distinct; top {c.most_common(6)}")
for f in ("status", "phases", "opportunities", "ramping_success_chance", "semiyearly_update_days", "breach", "next_id",
          "last_update"):
    print(f"new {f}: {dict(Counter(new[k].get(f) for k in paired))}")
