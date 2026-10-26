"""For named characters: the titles they hold (keys), their house and dynasty, and whether those are the player's.
Usage: python -I holders_kin.py <save.ck3> <player id> <id> [<id> ...]
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import gamestate as gs, translate as T  # noqa: E402

g = load(sys.argv[1])
player = int(sys.argv[2])
ids = [int(x) for x in sys.argv[3:]]
lb = gs.locate(g, "living")
chars = {int(e.key): g[e.start:e.end] for e in gs.iter_entries(g, lb.open + 1, lb.close)
         if e.key and e.key.isdigit() and int(e.key) in set(ids) | {player}}
houses = {i: g[e.start:min(e.end, e.start + 3000)] for i, e in T.entries(g, "dynasties/dynasty_house")}
keys = {}
for i, e in T.entries(g, "landed_titles/landed_titles"):
    b = g[e.start:min(e.end, e.start + 4096)]
    k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
    h = re.search(rb"\n\tholder=(\d+)", b)
    if k and h:
        keys.setdefault(int(h.group(1)), []).append(k.group(1).decode())


def kin(c):
    b = chars.get(c, b"")
    h = re.search(rb"\n\tdynasty_house=(\d+)", b)
    hid = int(h.group(1)) if h else None
    d = re.search(rb"\n\tdynasty=(\d+)", houses.get(hid, b"")) if hid is not None else None
    nm = re.search(rb"first_name=\"?([^\"\n]+)", b)
    return (nm.group(1).decode() if nm else "?"), hid, (int(d.group(1)) if d else None)


pn, ph, pd = kin(player)
print(f"player {player} {pn}: house {ph}, dynasty {pd}")
for c in ids:
    n, h, d = kin(c)
    rel = "same house" if h is not None and h == ph else ("same dynasty" if d is not None and d == pd else "-")
    print(f"  {c:>9} {n:<14} house {h}, dynasty {d}  {rel:<12} holds {len(keys.get(c, []))}: {sorted(keys.get(c, []))}")
