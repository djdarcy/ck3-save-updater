"""Step 1c pre-measurement: the baronies campaign barons lose when the engine loads our output.

The pair: our output as loaded and the game's re-save of exactly it. A lost barony = a barony held in ours by a
vassal whose contract the re-save drops (engine_drops.py) -- AND, wider, every barony a campaign character holds
in ours but nobody or someone else holds in the re-save. For each: its county in the 1.8.2 and 1.20 title
trees, whether the barony moved county, R15's class of the barony and of its old county (deadtitles.classify on
the campaign original), the side of the 1.20 county's holder in ours, and the re-save holder.

PREDICTION (director 04:40, written before the run): most of the 26 taken baronies sit in counties the clean
rule gave to reference holders; the 57 unheld sit in counties R15 renamed.

Usage: python -I barony_seam.py <campaign.ck3> <ours.ck3> <resaved.ck3> <old landed_titles> <new landed_titles>
       <first carried character slot>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, translate as T  # noqa: E402

camp, ours, res = (load(p) for p in sys.argv[1:4])
old_dir, new_dir, split = Path(sys.argv[4]), Path(sys.argv[5]), int(sys.argv[6])
old_parent, _ = D.title_tree(old_dir)
new_parent, _ = D.title_tree(new_dir)
r15 = {m.key: m for m in D.classify(camp, old_dir, new_dir)}


def titles(g):
    out = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        b = g[e.start:min(e.end, e.start + 4096)]
        k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
        h = re.search(rb"\n\tholder=(\d+)", b)
        out[i] = (k.group(1).decode() if k else None, int(h.group(1)) if h else None)
    return out


to, tr = titles(ours), titles(res)
by_key_o = {k: (i, h) for i, (k, h) in to.items() if k}
by_key_r = {k: (i, h) for i, (k, h) in tr.items() if k}


def side(c):
    return "none" if c is None else ("carried" if (c & 0xFFFFFF) >= split else "campaign")


rows = []
for k, (i, h) in by_key_o.items():
    if not k.startswith("b_") or h is None:
        continue
    hr = by_key_r.get(k, (None, None))[1]
    if hr == h:
        continue                                           # kept: not a loss
    oc, nc = old_parent.get(k), new_parent.get(k)
    nc_holder = by_key_o.get(nc, (None, None))[1] if nc else None
    rows.append({
        "barony": k, "held by": side(h), "after": "unheld" if hr is None else f"to {side(hr)}",
        "moved county": "yes" if oc != nc else "no", "old county": oc, "new county": nc,
        "R15 barony": r15[k].cls if k in r15 else "-", "R15 old county": r15[oc].cls if oc in r15 else "-",
        "new county holder": side(nc_holder),
    })
print("held baronies whose holder changes on load:", len(rows))
for col in ("held by", "after", "moved county", "R15 barony", "R15 old county", "new county holder"):
    print(f"  {col:18}", dict(Counter(r[col] for r in rows)))
print("\n  after x new county holder x R15 old county:")
for k, n in Counter((r["held by"], r["after"], r["moved county"], r["new county holder"])
                    for r in rows).most_common(12):
    print(f"    {n:>4}  {k}")
print("\n  examples:")
for r in sorted(rows, key=lambda r: r["held by"], reverse=True)[:12]:      # carried first, then campaign
    print("   ", r)
