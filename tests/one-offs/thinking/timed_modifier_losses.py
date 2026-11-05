"""HOLD item 1: the timed modifiers 1.20 removed. For each lost key that sits in a modifier={ modifier=X
expiration_date=D } block: how many instances, on what (characters, counties, dynasties), the expiry range, the old
effect (1.8.2 common/modifiers), and the finder's same-effect 1.20 candidate.
Usage: timed_modifier_losses.py <save> <lost.txt> <successors.json>"""
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = sf.read_save(sys.argv[1]).gamestate
lost = [ln.split()[1].rstrip(":") for ln in open(sys.argv[2], encoding="utf-8") if len(ln.split()) > 1]
succ = {r["key"]: r for r in json.load(open(sys.argv[3], encoding="utf-8"))}
date = re.search(rb"(?m)^date=(\S+)", d[:5_000_000]).group(1).decode()
print(f"save date {date}")
rows = []
for key in lost:
    hits = list(re.finditer(rb"modifier=\"?" + re.escape(key.encode()) + rb"\"?\s+(?:[^\n]*\n\s*)?expiration_date=(\S+)", d))
    if not hits:
        continue
    exp = sorted(h.group(1).decode() for h in hits)
    s = succ.get(key, {})
    rows.append((len(hits), key, exp[0], exp[-1], s.get("evidence", "")[:110], s.get("successor"), s.get("confidence")))
for n, key, e0, e1, ev, cand, conf in sorted(rows, reverse=True):
    print(f"{n:4} {key:45s} expires {e0}..{e1}  cand={cand} [{conf}]  {ev}")
print(f"total {sum(r[0] for r in rows)} instances, {len(rows)} keys")
