"""Mercenary companies in a save: how many have a title, whether the title has a holder, and whether the holder is
a living character. Split at an id threshold (companies >= SPLIT are the carried ones). Prints counts and examples.
Usage: python -I company_leaders.py <save.ck3> [split]
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs, savefile as sf, translate as T  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shape_diff import load  # noqa: E402  (reads plain-text saves too)

g = load(sys.argv[1])
split = int(sys.argv[2]) if len(sys.argv) > 2 else 1 << 62
titles = dict(T.entries(g, "landed_titles/landed_titles"))
lb = gs.locate(g, "living")
living = set(int(x) for x in re.findall(rb"(?m)^\t*(\d+)=\{", g[lb.open:lb.close]))
out = Counter()
ex = {}
for i, e in T.entries(g, "mercenary_company_manager/mercenary_companies"):
    side = "carried" if i >= split else "campaign"
    body = g[e.start:e.end]
    t = re.search(rb"[\n\t]title=(\d+)", body)
    if not t:
        out[(side, "no title")] += 1
        continue
    te = titles.get(int(t.group(1)))
    if te is None:
        out[(side, "title missing")] += 1
        ex.setdefault((side, "title missing"), i)
        continue
    h = re.search(rb"\n\tholder=(\d+)", g[te.start:min(te.end, te.start + 4096)])
    if not h:
        out[(side, "unheld")] += 1
        ex.setdefault((side, "unheld"), (i, int(t.group(1))))
    elif int(h.group(1)) not in living:
        out[(side, "holder not living")] += 1
        ex.setdefault((side, "holder not living"), (i, int(h.group(1))))
    else:
        hid = h.group(1)
        m = re.search(rb"(?m)^\t*" + hid + rb"=\{", g[lb.open:lb.close])
        s = lb.open + m.start()
        ce = gs.match_brace(g, lb.open + m.end() - 1)
        body_c = g[s:ce]
        dom = re.search(rb"domain=\{([^}]*)\}", body_c)
        gov = re.search(rb"government=(\w+)", body_c)
        ok_dom = bool(dom and t.group(1) in dom.group(1).split())
        k = (side, "led", "domain ok" if ok_dom else "domain LACKS title", gov.group(1).decode() if gov else "no gov")
        out[k] += 1
        ex.setdefault(k, (i, int(hid)))
for k in sorted(out):
    print(k, out[k], ex.get(k, ""))
