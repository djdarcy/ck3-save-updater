"""Carried baronies on provinces the campaign kept with no holding, where 1.20 has one.

For each barony title the output holds that the campaign does not have (a carried 1.20 barony), its province
(from the 1.20 title tree): the output's province entry has a holding type or not, and the reference's does.
A barony on a province with no holding cannot be held; the engine clears it on load (b_luoshan, province 8985,
re-save of e2e_1c3). Also counts provinces <= the campaign's top id whose reference entry has a holding and
whose output entry has none, whatever their barony.
Usage: python -I empty_provinces.py <campaign.ck3> <output.ck3> <reference.ck3> <1.20 landed_titles>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, translate as T  # noqa: E402

camp, out, ref = (load(p) for p in sys.argv[1:4])
_, prov_of = D.title_tree(Path(sys.argv[4]))


def keys(g):
    return {k.decode() for k in T.keyed(g, "landed_titles/landed_titles")}


def holdings(g):
    out = {}
    for i, e in T.entries(g, "provinces"):
        m = re.search(rb"holding=\{[^}]*?type=\"?(\w+)", g[e.start:min(e.end, e.start + 1500)])
        out[i] = m.group(1).decode() if m else None
    return out


ck, ok = keys(camp), keys(out)
ho, hr = holdings(out), holdings(ref)
held_out = {}
for i, e in T.entries(out, "landed_titles/landed_titles"):
    b = out[e.start:min(e.end, e.start + 2000)]
    k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
    if k:
        held_out[k.group(1).decode()] = bool(re.search(rb"\n\tholder=\d+", b))
c = Counter()
ex = []
for k in sorted(ok - ck):
    if not k.startswith("b_") or k not in prov_of:
        continue
    p = prov_of[k]
    state = ("out has holding" if ho.get(p) else "out has NO holding") + \
            (", ref has " + str(hr.get(p)) if hr.get(p) else ", ref has none")
    c[(state, "held" if held_out.get(k) else "unheld")] += 1
    if not ho.get(p) and hr.get(p) and held_out.get(k) and len(ex) < 6:
        ex.append((k, p, hr.get(p)))
print("carried baronies by province state:")
for k, n in c.most_common():
    print(f"  {n:>5}  {k}")
print("examples (barony, province, reference holding):", ex)
gap = [p for p in hr if hr[p] and not ho.get(p) and p in ho]
print("provinces present in the output with no holding where the reference has one:", len(gap),
      "| by reference type:", dict(Counter(hr[p] for p in gap).most_common()))
