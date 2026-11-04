"""U1 schemes: which carried schemes ended between two saves, by scheme type, and what they had been doing (status,
progress) when last seen. Also tallies the game's own log lines about schemes when a run folder is given.
Usage: scheme_endings.py <earlier save> <later save> [<run folder>]"""
import re
import sys
from collections import Counter
from pathlib import Path

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


da, db = load(sys.argv[1]), load(sys.argv[2])
print("dates:", re.search(rb"(?m)^date=(\S+)", da).group(1).decode(), "->",
      re.search(rb"(?m)^date=(\S+)", db).group(1).decode())
a, b = schemes(da), schemes(db)
ended = [a[k] for k in set(a) - set(b)]
kept = [a[k] for k in set(a) & set(b)]
by_type_ended, by_type_all = Counter(val(x, b"type") for x in ended), Counter(val(x, b"type") for x in a.values())
print(f"ended {len(ended)} of {len(a)}")
for t, n in by_type_all.most_common(12):
    print(f"  {t:28s} ended {by_type_ended[t]:4d} of {n:4d}")
print("  status when last seen, ended:", dict(Counter(val(x, b"status") for x in ended)))
if len(sys.argv) > 3:
    logs = Path(sys.argv[3]) / "logs"
    for name in ("game.log", "error.log"):
        p = logs / name
        if p.exists():
            t = p.read_text(encoding="utf-8", errors="replace")
            hits = Counter(m.group(0)[:90] for m in re.finditer(r"[^\n]*[Ss]cheme[^\n]*", t))
            print(f"  {name}: {sum(hits.values())} scheme lines; top: {hits.most_common(4)}")
