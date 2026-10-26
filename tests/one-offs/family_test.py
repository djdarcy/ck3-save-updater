"""Is a character "of the player's family"? (decision I input; the first function of the family-tree tool, U17)

Definition (director 2026-10-26, from djdarcy): his house is HOUSE or his dynasty DYNASTY; or a spouse's
(current or former) house or dynasty is; or he descends from the FOUNDER (father/mother upward, any depth); or a
spouse does. Parents come from the child lists of every character section (living, dead_unprunable,
characters/dead_prunable) plus real_father. Per person: the test that matched and its path, and whether his
liege chain (primary title -> de facto liege title -> its holder, upward) reaches the player.

Usage: python -I family_test.py <save.ck3> <player> <house> <dynasty> <founder> <id> [<id> ...]
"""
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import gamestate as gs, translate as T  # noqa: E402

g = load(sys.argv[1])
player, HOUSE, DYN, FOUNDER = (int(x) for x in sys.argv[2:6])
people = [int(x) for x in sys.argv[6:]]

chars = {}
for sec in ("living", "dead_unprunable", "characters/dead_prunable"):
    try:
        b = gs.locate(g, sec)
    except Exception:  # noqa: BLE001
        continue
    for e in gs.iter_entries(g, b.open + 1, b.close):
        if e.key and e.key.isdigit():
            chars.setdefault(int(e.key), g[e.start:e.end])
house_dyn = {}
for i, e in T.entries(g, "dynasties/dynasty_house"):
    m = re.search(rb"\n\t*dynasty=(\d+)", g[e.start:min(e.end, e.start + 2000)])
    house_dyn[i] = int(m.group(1)) if m else None


def ids(body, field):
    out = []
    for m in re.finditer(rb"\n\t+" + field + rb"=(?:\{([^}]*)\}|(\d+))", body):
        out += [int(x) for x in (m.group(1) or m.group(2)).split() if x.isdigit()]
    return out


parents = defaultdict(set)
for c, b in chars.items():
    for k in ids(b, b"child"):
        parents[k].add(c)
for c, b in chars.items():
    for f in ids(b, b"real_father"):
        parents[c].add(f)


def spouses(c):
    b = chars.get(c, b"")
    return sorted(set(ids(b, b"spouse") + ids(b, b"primary_spouse") + ids(b, b"former_spouses")))


def house_of(c):
    m = re.search(rb"\n\tdynasty_house=(\d+)", chars.get(c, b""))
    h = int(m.group(1)) if m else None
    return h, house_dyn.get(h)


def first_name(c):
    m = re.search(rb"\n\tfirst_name=\"?([^\"\n]+)", chars.get(c, b""))
    return m.group(1).decode() if m else "?"


def descent(c):
    """Shortest parent path from c up to FOUNDER, or None."""
    prev, q = {c: None}, deque([c])
    while q:
        x = q.popleft()
        if x == FOUNDER:
            path = []
            while x is not None:
                path.append(x)
                x = prev[x]
            return path
        for p in parents.get(x, ()):
            if p not in prev:
                prev[p] = x
                q.append(p)
    return None


titles = {}
for i, e in T.entries(g, "landed_titles/landed_titles"):
    b = g[e.start:min(e.end, e.start + 4096)]
    h = re.search(rb"\n\tholder=(\d+)", b)
    df = re.search(rb"\n\tde_facto_liege=(\d+)", b)
    titles[i] = (int(h.group(1)) if h else None, int(df.group(1)) if df else None)


def chain(c):
    out, seen = [c], set()
    while c not in seen:
        seen.add(c)
        m = re.search(rb"\n\t\tdomain=\{\s*(\d+)", chars.get(c, b""))
        if not m:
            break
        df = titles.get(int(m.group(1)), (None, None))[1]
        nxt = titles.get(df, (None, None))[0] if df is not None else None
        if nxt is None or nxt == c:
            break
        out.append(nxt)
        c = nxt
    return out


for c in people:
    tests = []
    h, d = house_of(c)
    if h == HOUSE or d == DYN:
        tests.append(f"own house {h} / dynasty {d}")
    for s in spouses(c):
        sh, sd = house_of(s)
        if sh == HOUSE or sd == DYN:
            tests.append(f"spouse {first_name(s)} ({s}), house {sh} / dynasty {sd}")
    p = descent(c)
    if p:
        tests.append(f"descends from the founder, {len(p) - 1} generation(s): "
                     + " -> ".join(f"{first_name(x)} ({x})" for x in p))
    for s in spouses(c):
        sp = descent(s)
        if sp:
            tests.append(f"spouse {first_name(s)} ({s}) descends from the founder, {len(sp) - 1} generation(s)")
    ch = chain(c)
    print(f"{first_name(c)} ({c}): house {h}, dynasty {d}; spouses {spouses(c) or '-'}; "
          f"in the player's realm: {'yes' if player in ch else 'no'}")
    print("   family: " + ("; ".join(tests) if tests else "NO (no test matched)"))
