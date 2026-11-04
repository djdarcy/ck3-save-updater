"""U1 culture: are the cultures 1.20 marks invalid="" on load still alive? Between an earlier and a later save of the
same campaign, per culture (by id): does it carry invalid=, how many of its innovations gained progress or completed,
and did its era data change. Grouped by whether the earlier save marks it invalid.
Usage: culture_liveness.py <earlier save> <later save>"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def cultures(d):
    cm = gs.locate(d, "culture_manager/cultures")
    return {e.key: d[e.body[0]:e.body[1]] for e in gs.iter_entries(d, *cm.body)}


INNO = re.compile(rb"type=\"?(innovation_\w+)\"?\s*(?:progress=(\S+))?")


def innovations(body):
    i = body.find(b"culture_innovation=")
    if i < 0:
        return {}
    j = gs.match_brace(body, body.index(b"{", i))
    return {m.group(1): (float(m.group(2)) if m.group(2) else 100.0) for m in INNO.finditer(body, i, j)}


a, b = cultures(load(sys.argv[1])), cultures(load(sys.argv[2]))
n = Counter()
for k, x in a.items():
    y = b.get(k)
    group = "invalid" if b'invalid=""' in x else "valid"
    n[(group, "cultures")] += 1
    if y is None:
        n[(group, "gone")] += 1
        continue
    i0, i1 = innovations(x), innovations(y)
    moved = sum(1 for t, p in i1.items() if p > i0.get(t, 0))
    done = sum(1 for t, p in i1.items() if p >= 100 and i0.get(t, 0) < 100)
    n[(group, "with innovation progress")] += moved > 0
    n[(group, "innovations advanced")] += moved
    n[(group, "innovations completed")] += done
    n[(group, "era data changed")] += x[x.find(b"culture_era_data"):x.find(b"culture_innovation")] != \
        y[y.find(b"culture_era_data"):y.find(b"culture_innovation")]
for k in sorted(n):
    print(f"{n[k]:6}  {k[0]:8s} {k[1]}")
