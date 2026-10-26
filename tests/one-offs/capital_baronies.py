"""Are the moved baronies the capital of their 1.20 county? (The first barony listed in a county's block in the
game's landed_titles is its capital; the county's holder always holds the capital barony.)

Reads the barony_seam output rows from a re-save pair and splits the baronies the campaign lost by "is the 1.20
county's capital". Also: of all moved held baronies (1.8.2 -> 1.20 county changed, held in the campaign), how
many are capitals.
Usage: python -I capital_baronies.py <campaign.ck3> <ours.ck3> <resaved.ck3> <old landed_titles> <new landed_titles>
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
old_parent, _ = D.title_tree(Path(sys.argv[4]))
new_parent, _ = D.title_tree(Path(sys.argv[5]))
first_child = {}
for k, par in new_parent.items():                    # insertion order = file order
    if k.startswith("b_") and par and par not in first_child:
        first_child[par] = k


def holders(g):
    out = {}
    for _, e in T.entries(g, "landed_titles/landed_titles"):
        b = g[e.start:min(e.end, e.start + 2000)]
        k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
        h = re.search(rb"\n\tholder=(\d+)", b)
        if k:
            out[k.group(1).decode()] = int(h.group(1)) if h else None
    return out


hc, ho, hr = holders(camp), holders(ours), holders(res)
moved = [k for k, h in hc.items() if k.startswith("b_") and h is not None and old_parent.get(k)
         and new_parent.get(k) and old_parent[k] != new_parent[k]]
c = Counter()
for k in moved:
    cap = first_child.get(new_parent[k]) == k
    lost = hr.get(k) != ho.get(k)
    c[("capital of its 1.20 county" if cap else "not the capital", "lost on load" if lost else "kept")] += 1
for k, n in sorted(c.items()):
    print(f"  {n:>4}  {k}")
print("lost, not the capital:", [k for k in moved if first_child.get(new_parent[k]) != k and hr.get(k) != ho.get(k)])
