"""S3 /measure: how 1.20 scores a house relation. In a played save, per level: how many relations, the range of their
fraction, and, from their history lines, the amounts of each change. Answers where "deep in the feud level" sits, and
how fast relations move. Usage: house_relation_scores.py <played save>"""
import re
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    d = sf.read_save(sys.argv[1]).gamestate
except sf.UnsupportedKindError:
    raw = open(sys.argv[1], "rb").read()
    d = raw[raw.index(b"\n") + 1:]
b = gs.locate(d, "house_relations/database")
frac, amounts = defaultdict(list), defaultdict(list)
for e in gs.iter_entries(d, *b.body):
    body = d[e.body[0]:e.body[1]]
    lvl = re.search(rb"(?m)^\t\t\ttype=\S+\s+level=default_house_relation_level_(\w+)", body) or \
        re.search(rb"level=default_house_relation_level_(\w+)", body)
    f = re.search(rb"fraction=(-?[\d.]+)", body)
    if lvl and f:
        frac[lvl.group(1).decode()].append(float(f.group(1)))
    for a in re.findall(rb"amount=(-?[\d.]+)", body):
        amounts[lvl.group(1).decode() if lvl else "?"].append(float(a))
for lv in ("feud", "rivalry", "quarrel", "neutral", "cordial", "friendly", "amity"):
    fs = frac.get(lv, [])
    if fs:
        am = amounts.get(lv, [])
        print(f"{lv:9s} n={len(fs):5d} fraction min {min(fs):6.2f} max {max(fs):6.2f} | history amounts: "
              f"{len(am)} changes, range {min(am) if am else 0:.2f}..{max(am) if am else 0:.2f}")
