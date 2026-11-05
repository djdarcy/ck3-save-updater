"""Schemes the game started itself against carried ones, in one played save: for each scheme type with both kinds,
which fields each kind carries (share of schemes) and the common values of the small ones. Carried schemes are those
whose id is in the earlier save too. Shows what 1.20's start-up (on_ready) writes that a carried scheme lacks.
Usage: scheme_new_vs_carried.py <earlier save> <played save> [type ...]"""
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def schemes(d):
    s = gs.locate(d, "schemes/active")
    return {e.key: d[e.body[0]:e.body[1]] for e in gs.iter_entries(d, *s.body)}


old = set(schemes(load(sys.argv[1])))
now = schemes(load(sys.argv[2]))
want = set(sys.argv[3:])
by = defaultdict(lambda: {"new": [], "carried": []})
for k, b in now.items():
    t = re.search(rb"(?m)^\t*type=(\w+)", b)
    if t:
        by[t.group(1).decode()]["carried" if k in old else "new"].append(b)
for t, g in sorted(by.items(), key=lambda kv: -min(len(kv[1]["new"]), len(kv[1]["carried"]))):
    if not g["new"] or not g["carried"] or (want and t not in want):
        continue
    print(f"=== {t}: new {len(g['new'])}, carried {len(g['carried'])}")
    fields = {k: Counter() for k in ("new", "carried")}
    vals = {k: defaultdict(Counter) for k in ("new", "carried")}
    for kind in ("new", "carried"):
        for b in g[kind]:
            top = re.findall(rb"(?m)^\t\t\t([a-z_]+)=([^\n{]*)", b)
            for f, v in top:
                fields[kind][f.decode()] += 1
                if len(v) < 30:
                    vals[kind][f.decode()][v.decode().strip()] += 1
    for f in sorted(set(fields["new"]) | set(fields["carried"])):
        a, c = fields["new"][f] / len(g["new"]), fields["carried"][f] / len(g["carried"])
        va = ", ".join(f"{x}:{n}" for x, n in vals["new"][f].most_common(3))
        vc = ", ".join(f"{x}:{n}" for x, n in vals["carried"][f].most_common(3))
        flag = "  <--" if abs(a - c) > 0.3 or (va.split(":")[0] != vc.split(":")[0] and f not in ("owner", "target", "date")) else ""
        print(f"  {f:26s} new {a:4.0%} [{va[:60]}]   carried {c:4.0%} [{vc[:60]}]{flag}")
    if want == set() and t != list(by)[0]:
        pass
