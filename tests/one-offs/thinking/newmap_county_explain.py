"""#6 criterion 2, the differences explained one by one. For each new-map county whose holder or liege title differs
from the reference: who holds it here (campaign character = the id is in the old save's living; copied = not), who
holds it in the reference, each side's liege title and whether the campaign already had that title, and the R15
table rows that name the county or a title from its chain (the dead-title successors and hand-backs).
Usage: python -I newmap_county_explain.py <old gamestate> <updated .ck3> <reference .ck3> <report.json>"""
import json
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator\tests\one-offs\thinking")
import newmap_county_holders as H  # noqa: E402  (its module body runs the summary; argv is shared)

old_d = H.load(sys.argv[1])
new_d, ref_d = H.load(sys.argv[2]), H.load(sys.argv[3])
old_t, _ = H.titles(old_d)
new_t, new_by = H.titles(new_d)
ref_t, ref_by = H.titles(ref_d)
lv = H.gs.find_section(old_d, "living")
old_living = {m.group(1).decode() for m in re.finditer(rb"(?m)^(\d+)=\{", old_d[lv.start:lv.end])}
np_, rp = H.people(new_d), H.people(ref_d)
rep = json.load(open(sys.argv[4], encoding="utf-8"))
r15 = next(r for r in rep["rules"] if r["id"] == "R15")["extra"]["table"]
settled = {row["new county"] for r in rep["rules"] if r["id"] == "R17" for row in r["extra"].get("settled", [])}


def r15_rows(*keys):
    keys = {k for k in keys if k}
    return [f"{x['key']}: {x.get('class')} -> {x.get('outcome', '')[:70]}" for x in r15
            if x["key"] in keys or keys & set(x.get("successors") or [])]


rows, kinds = [], Counter()
for k in sorted(k for k in ref_t if k.startswith("c_") and k not in old_t and k not in settled):
    if k not in new_t:
        continue
    (nh, nl), (rh, rl) = new_t[k], ref_t[k]
    nlk, rlk = new_by.get(nl), ref_by.get(rl)
    who_n = np_.get(nh) if nh else None
    who_r = rp.get(rh) if rh else None
    if who_n == who_r and nlk == rlk:
        continue
    camp = nh in old_living if nh else False
    kind = []
    if who_n != who_r:
        kind.append("holder: campaign character" if camp else "holder: another copied ruler")
    if nlk != rlk:
        kind.append("liege: reference liege is a campaign title, link dropped" if (rlk in old_t and nlk is None)
                    else f"liege: {nlk} here, {rlk} in the reference")
    kinds["; ".join(x.split(":")[0] + ":" + x.split(":")[1].split(" here")[0] if "here" in x else x for x in kind)] += 1
    rows.append((k, who_n, "campaign" if camp else "copied", who_r, nlk, rlk, rlk in old_t if rlk else None,
                 r15_rows(k, nlk, rlk, new_t.get(nlk or "", (None,))[0] and nlk)))
print(f"differing new-map counties: {len(rows)}")
for kd, n in kinds.most_common():
    print(f"  {n:>3}  {kd}")
for r in rows:
    k, wn, camp, wr, nlk, rlk, rl_old, r15m = r
    print(f"{k}: here {wn} ({camp}) under {nlk}; reference {wr} under {rlk}"
          f"{' [reference liege exists in the old save]' if rl_old else ''}")
    for m in r15m[:3]:
        print(f"      R15 {m}")
