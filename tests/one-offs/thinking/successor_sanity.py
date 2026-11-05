"""S4 sanity pass (djdarcy 2026-11-04): for every R25 row that maps a modifier, rank all 1.20.1.2 modifiers against
the old one (modifier_reference.py's scores) and say whether our chosen successor is the best, or which beats it.
Usage: python -I successor_sanity.py <old ref.json> <new ref.json>"""
import json
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
sys.path.insert(0, r"C:\code\ck3-save-migrator\tests\one-offs\thinking")
from ck3_save_migrator.rules.to_1_20 import SUCCESSORS  # noqa: E402
from modifier_reference import words  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
old = json.load(open(sys.argv[1], encoding="utf-8"))
new = json.load(open(sys.argv[2], encoding="utf-8"))


def score(o_key, o, n_key, n):
    a = len(words(o_key.replace("_", " ")) & words(n_key.replace("_", " ")))
    b = len(words(o["name"] + " " + o["desc"]) & words(n["name"] + " " + n["desc"]))
    so = {(k, v > 0) for k, v in o["effects"].items()}
    sn = {(k, v > 0) for k, v in n["effects"].items()}
    same = {k for k in o["effects"] if k in n["effects"] and o["effects"][k] == n["effects"][k]}
    return 2 * a + b + len(so & sn) + (2 if so and so == sn else 0) + len(same), (a, b, len(so & sn), len(same))


rows = [r for r in SUCCESSORS if r.folder == "modifiers"]
print(f"{len(rows)} modifier rows")
for r in rows:
    olds = [k for k in old if re.fullmatch(r.old, k)]
    for ok in olds:
        nk = re.sub(r.old, r.new, ok) if any(c in r.old for c in "[(\\") else r.new
        o = old[ok]
        if nk not in new:
            print(f"!! {ok} -> {nk}: successor not in 1.20 reference")
            continue
        ranked = sorted(((score(ok, o, k, n), k) for k, n in new.items()), key=lambda x: -x[0][0])
        ours = score(ok, o, nk, new[nk])
        better = [(s, k) for s, k in ranked if s[0] > ours[0]][:3]
        flag = "OK " if not better else "?? "
        print(f"{flag}{ok} -> {nk}  ours {ours[0]} {ours[1]}  old {o['effects']}  new {new[nk]['effects']}")
        for s, k in better:
            print(f"      beats it: {k} {s[0]} {s[1]} \"{new[k]['name'][:40]}\" {new[k]['effects']}")
