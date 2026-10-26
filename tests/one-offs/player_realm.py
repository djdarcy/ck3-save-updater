"""Is a character inside the player's realm? For the holders of the moved baronies (step 1c): walk each holder's
liege chain (primary title = first in landed_data/domain -> its de_facto_liege title -> that title's holder ...)
and report whether the player character is on it, or is the holder.
Usage: python -I player_realm.py <save.ck3> <old landed_titles> <new landed_titles>
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, gamestate as gs, translate as T  # noqa: E402

g = load(sys.argv[1])
new_parent, _ = D.title_tree(Path(sys.argv[3]))
pm = re.search(rb"played_character=\{[^}]*?character=(\d+)", g) or re.search(rb"\n\tcharacter=(\d+)", g[:200000])
player = int(pm.group(1))
info = {}
for i, e in T.entries(g, "landed_titles/landed_titles"):
    b = g[e.start:min(e.end, e.start + 4096)]
    k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
    h = re.search(rb"\n\tholder=(\d+)", b)
    dj = re.search(rb"\n\tde_jure_liege=(\d+)", b)
    df = re.search(rb"\n\tde_facto_liege=(\d+)", b)
    info[i] = (k.group(1).decode() if k else "", int(h.group(1)) if h else None,
               int(dj.group(1)) if dj else None, int(df.group(1)) if df else None)
lb = gs.locate(g, "living")
primary = {}
for e in gs.iter_entries(g, lb.open + 1, lb.close):
    if e.key and e.key.isdigit():
        m = re.search(rb"\n\t\tdomain=\{\s*(\d+)", g[e.start:e.end])
        if m:
            primary[int(e.key)] = int(m.group(1))
print("player", player, "primary", info.get(primary.get(player), ("?",))[0])


def chain(c):
    seen, out = set(), [c]
    while c in primary and c not in seen:
        seen.add(c)
        df = info.get(primary[c], (None,) * 4)[3]
        nxt = info.get(df, (None,) * 4)[1] if df is not None else None
        if nxt is None or nxt == c:
            break
        out.append(nxt)
        c = nxt
    return out


res = Counter()
for i, (k, h, dj, _) in info.items():
    if not k.startswith("b_") or h is None:
        continue
    cur, want = info.get(dj, ("",))[0], new_parent.get(k)
    if want is None or cur == want:
        continue
    ch = chain(h)
    inside = player in ch
    res["inside the player's realm" if inside else "outside"] += 1
    if inside:
        print("  INSIDE:", k, cur, "->", want, "holder", h, "chain", ch[:5])
print(dict(res))
