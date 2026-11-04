"""U1, schemes: do the schemes 1.20 marks frozen on load (freeze_data={ frozen=yes }) ever thaw and progress? Compare
schemes/active between two plain-text saves of the same campaign, an earlier and a later one: the game date of each,
then per scheme (by id) the frozen flag, progress and phase, and schemes that ended or began.
Usage: scheme_freeze_compare.py <earlier save> <later save>"""
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


def schemes(d):
    s = gs.locate(d, "schemes/active")
    return {e.key: d[e.body[0]:e.body[1]] for e in gs.iter_entries(d, *s.body)}


def val(body, key):
    m = re.search(rb"(?<![\w])" + key + rb"=(\S+)", body)
    return m.group(1).decode() if m else "-"


def frozen(body):
    return "frozen" if re.search(rb"frozen=yes", body) else "not frozen"


da, db = load(sys.argv[1]), load(sys.argv[2])
print("dates:", val(da[:2_000_000], b"\ndate").strip() if False else re.search(rb"(?m)^date=(\S+)", da).group(1).decode(),
      "->", re.search(rb"(?m)^date=(\S+)", db).group(1).decode())
a, b = schemes(da), schemes(db)
print(f"schemes: {len(a)} -> {len(b)}; ended {len(set(a) - set(b))}, begun {len(set(b) - set(a))}")
n, p = Counter(), Counter()
for k, x in a.items():
    y = b.get(k)
    if y is None:
        continue
    n[(frozen(x), "->", frozen(y))] += 1
    p["progress " + ("same" if val(x, b"progress") == val(y, b"progress") else "changed")] += 1
    p["phases " + ("same" if val(x, b"phases") == val(y, b"phases") else "changed")] += 1
print(dict(n))
print(dict(p))
begun = [b[k] for k in set(b) - set(a)]
print("begun:", dict(Counter(frozen(x) for x in begun)))
