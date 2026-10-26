"""Trace named baronies across our output and the game's re-save: the barony's holder, de jure and de facto
liege (as keys), its county's holder and list, and the holder's contract (liege) in each file.
Usage: python -I barony_trace.py <ours.ck3> <resaved.ck3> <barony key> [...]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402


def index(g):
    t = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        b = g[e.start:min(e.end, e.start + 4096)]
        f = {k: (m.group(1).decode() if (m := re.search(rb"\n\t" + k.encode() + rb"=\"?([\w\-']+)", b)) else None)
             for k in ("key", "holder", "de_jure_liege", "de_facto_liege")}
        lst = re.search(rb"\n\tde_jure_vassals=\{([^}]*)\}", b)
        f["vassals"] = lst.group(1).split() if lst else []
        t[i] = f
    contracts = {}
    for path in ("vassal_contracts/database", "vassal_contracts/active"):
        try:
            for i, e in T.entries(g, path):
                b = g[e.start:e.end]
                v = re.search(rb"\n\t+vassal=(\d+)", b)
                lg = re.search(rb"\n\t+liege=(\d+)", b)
                if v:
                    contracts[v.group(1).decode()] = (i, lg.group(1).decode() if lg else None)
        except Exception:  # noqa: BLE001
            pass
    return t, {f["key"]: i for i, f in t.items() if f["key"]}, contracts


for name, path in (("ours", sys.argv[1]), ("resave", sys.argv[2])):
    t, by, ct = index(load(path))
    print(f"== {name}")
    for k in sys.argv[3:]:
        i = by.get(k)
        if i is None:
            print("  ", k, "ABSENT")
            continue
        f = t[i]
        key_of = lambda x: t.get(int(x), {}).get("key") if x and x.isdigit() else x  # noqa: E731
        c = f["de_jure_liege"]
        cf = t.get(int(c), {}) if c and c.isdigit() else {}
        print(f"   {k} id {i}: holder {f['holder']}, de jure {key_of(c)}, de facto {key_of(f['de_facto_liege'])};"
              f" county holder {cf.get('holder')}, county lists it: {str(i) in cf.get('vassals', [])};"
              f" holder's contract {ct.get(f['holder'])}")
