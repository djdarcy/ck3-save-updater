"""Step 1c: the held baronies whose de jure county moved 1.8.2 -> 1.20, sorted by what keeping them needs.

For each barony in the output whose save de jure liege county differs from its 1.20 county: the holder H, the
1.20 county C' and its holder X (in the output). Cases:
  same holder      H holds C' too: re-parent only, no new liege
  baron only       every title H holds is a barony inside C' (after re-parenting): H becomes X's vassal
  mixed            H also holds titles outside C': two lieges would be needed (a design question)
  county unheld    C' has no holder in the output
Usage: python -I barony_holders.py <out.ck3> <old landed_titles> <new landed_titles> [first carried slot]
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, translate as T  # noqa: E402

g = load(sys.argv[1])
_, _ = Path(sys.argv[2]), None
new_parent, _ = D.title_tree(Path(sys.argv[3]))
split = int(sys.argv[4]) if len(sys.argv) > 4 else 83378
info = {}
for i, e in T.entries(g, "landed_titles/landed_titles"):
    b = g[e.start:min(e.end, e.start + 4096)]
    k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
    h = re.search(rb"\n\tholder=(\d+)", b)
    dj = re.search(rb"\n\tde_jure_liege=(\d+)", b)
    info[i] = (k.group(1).decode() if k else None, int(h.group(1)) if h else None, int(dj.group(1)) if dj else None)
by_key = {k: i for i, (k, _, _) in info.items() if k}
held = defaultdict(list)
for i, (k, h, _) in info.items():
    if h is not None and k:
        held[h].append(k)


def side(c):
    return "none" if c is None else ("carried" if (c & 0xFFFFFF) >= split else "campaign")


cases, rows = Counter(), []
for i, (k, h, dj) in info.items():
    if not k or not k.startswith("b_") or h is None:
        continue
    cur = info.get(dj, (None,))[0] if dj is not None else None
    want = new_parent.get(k)
    if want is None or cur == want:
        continue
    x = info.get(by_key.get(want), (None, None))[1] if want in by_key else None
    if want not in by_key:
        case = "county missing in output"
    elif x is None:
        case = "county unheld"
    elif x == h:
        case = "same holder"
    elif all(t.startswith("b_") and new_parent.get(t) == want for t in held[h]):
        case = "baron only"
    else:
        case = "mixed"
    cases[(case, side(h), side(x))] += 1
    if case == "mixed" and len(rows) < 8:
        rows.append((k, cur, want, h, sorted(held[h])[:6]))
print("held baronies whose county moved:", sum(cases.values()))
for c, n in cases.most_common():
    print(f"  {n:>5}  {c}   (case, holder side, 1.20 county holder side)")
print("mixed examples (barony, save county, 1.20 county, holder, holder's titles):")
for r in rows:
    print("  ", r)
