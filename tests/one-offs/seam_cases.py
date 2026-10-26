"""1c-bis pre-measurement: every campaign-held moved barony whose 1.20 county a copied ruler holds, with what the
settlement rule needs to decide it.

Per barony: the baron; its 1.8.2 county and that county's holder in the campaign (the "old count"); its 1.20
county and holder in the output (side); capital of the 1.20 county (game files: first barony listed); the baron
holds land outside the 1.20 county ("mixed"); the family test (house/dynasty of the player, a spouse's, or descent
from the founder); whether the baron's liege chain reaches the player; and the 1.20 county's other baronies with
their holders in the output (an EMPTY one is where a displaced capital baron could go).

Usage: python -I seam_cases.py <campaign.ck3> <output.ck3> <old landed_titles> <new landed_titles> <player>
       <house> <dynasty> <founder> [first carried slot]
"""
import re
import sys
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, gamestate as gs, translate as T  # noqa: E402

camp, out = load(sys.argv[1]), load(sys.argv[2])
old_parent, _ = D.title_tree(Path(sys.argv[3]))
new_parent, _ = D.title_tree(Path(sys.argv[4]))
player, HOUSE, DYN, FOUNDER = (int(x) for x in sys.argv[5:9])
split = int(sys.argv[9]) if len(sys.argv) > 9 else 83378
children = defaultdict(list)
for k, p in new_parent.items():                     # insertion order = file order: the first barony is the capital
    if p and k.startswith("b_"):
        children[p].append(k)


def side(c):
    return "none" if c is None else ("carried" if (c & 0xFFFFFF) >= split else "campaign")


class W:
    def __init__(self, g):
        self.g = g
        self.t, self.by = {}, {}
        for i, e in T.entries(g, "landed_titles/landed_titles"):
            b = g[e.start:min(e.end, e.start + 4096)]
            k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
            h = re.search(rb"\n\tholder=(\d+)", b)
            df = re.search(rb"\n\tde_facto_liege=(\d+)", b)
            key = k.group(1).decode() if k else ""
            self.t[i] = (key, int(h.group(1)) if h else None, int(df.group(1)) if df else None)
            if key:
                self.by[key] = i
        self.held = defaultdict(list)
        for i, (k, h, _) in self.t.items():
            if h is not None:
                self.held[h].append(k)
        self.c = {}
        for sec in ("living", "dead_unprunable", "characters/dead_prunable"):
            try:
                blk = gs.locate(g, sec)
            except Exception:  # noqa: BLE001
                continue
            for e in gs.iter_entries(g, blk.open + 1, blk.close):
                if e.key and e.key.isdigit():
                    self.c.setdefault(int(e.key), g[e.start:e.end])
        self.hd = {}
        for i, e in T.entries(g, "dynasties/dynasty_house"):
            m = re.search(rb"\n\t*dynasty=(\d+)", g[e.start:min(e.end, e.start + 2000)])
            self.hd[i] = int(m.group(1)) if m else None
        self.parents = defaultdict(set)
        for c, b in self.c.items():
            for m in re.finditer(rb"\n\t+child=\{([^}]*)\}", b):
                for k in m.group(1).split():
                    self.parents[int(k)].add(c)
            for m in re.finditer(rb"\n\t+real_father=(\d+)", b):
                self.parents[c].add(int(m.group(1)))

    def holder(self, key):
        return self.t.get(self.by.get(key), ("", None, None))[1]

    def name(self, c):
        m = re.search(rb"\n\tfirst_name=\"?([^\"\n]+)", self.c.get(c, b""))
        return f"{m.group(1).decode() if m else '?'} ({c})" if c is not None else "(none)"

    def kin(self, c):
        m = re.search(rb"\n\tdynasty_house=(\d+)", self.c.get(c, b""))
        h = int(m.group(1)) if m else None
        return h, self.hd.get(h)

    def spouses(self, c):
        b = self.c.get(c, b"")
        out = []
        for f in (b"spouse", b"primary_spouse", b"former_spouses"):
            for m in re.finditer(rb"\n\t+" + f + rb"=(?:\{([^}]*)\}|(\d+))", b):
                out += [int(x) for x in (m.group(1) or m.group(2)).split() if x.isdigit()]
        return sorted(set(out))

    def descends(self, c):
        seen, q = {c}, deque([c])
        while q:
            x = q.popleft()
            if x == FOUNDER:
                return True
            for p in self.parents.get(x, ()):
                if p not in seen:
                    seen.add(p)
                    q.append(p)
        return False

    def family(self, c):
        h, d = self.kin(c)
        if h == HOUSE or d == DYN:
            return "own house/dynasty"
        for s in self.spouses(c):
            sh, sd = self.kin(s)
            if sh == HOUSE or sd == DYN:
                return "spouse's house/dynasty"
        if self.descends(c):
            return "descends from the founder"
        if any(self.descends(s) for s in self.spouses(c)):
            return "spouse descends from the founder"
        return "-"

    def in_realm(self, c):
        seen = set()
        while c not in seen:
            if c == player:
                return True
            seen.add(c)
            m = re.search(rb"\n\t\tdomain=\{\s*(\d+)", self.c.get(c, b""))
            if not m:
                return False
            df = self.t.get(int(m.group(1)), ("", None, None))[2]
            nxt = self.t.get(df, ("", None, None))[1] if df is not None else None
            if nxt is None or nxt == c:
                return c == player
            c = nxt
        return False


C, O = W(camp), W(out)
_, prov_of = D.title_tree(Path(sys.argv[4]))
holding = {}
for p, e in T.entries(out, "provinces"):
    m = re.search(rb"holding=\{[^}]*?type=\"?(\w+)", out[e.start:min(e.end, e.start + 1500)])
    holding[p] = m.group(1).decode() if m else None


def built(b):
    """The holding type on a barony's province in the output, or None (unbuilt: no one can hold it)."""
    return holding.get(prov_of.get(b))
rows = []
for i, (k, h, _) in C.t.items():
    if not k.startswith("b_") or h is None:
        continue
    oc, nc = old_parent.get(k), new_parent.get(k)
    if not oc or not nc or oc == nc:
        continue
    x = O.holder(nc)
    if side(x) != "carried":
        continue
    others = [(b, O.holder(b)) for b in children.get(nc, []) if b != k]
    rows.append({
        "barony": k, "baron": C.name(h), "old county": oc, "old count": C.name(C.holder(oc)),
        "baron is old count": C.holder(oc) == h,
        "new county": nc, "new holder": O.name(x), "capital": children.get(nc, [None])[0] == k,
        "mixed": not all(t.startswith("b_") and new_parent.get(t) == nc for t in C.held[h]),
        "family": C.family(h), "in realm": C.in_realm(h),
        "empty baronies in new county": [f"{b} ({built(b) or 'UNBUILT'})" for b, hh in others if hh is None],
        "other baronies": [(b, side(hh)) for b, hh in others],
    })
rows.sort(key=lambda r: (not r["in realm"], r["new county"], r["barony"]))
print(f"campaign-held moved baronies under a carried 1.20 county: {len(rows)} "
      f"(in the player's realm {sum(r['in realm'] for r in rows)}, outside {sum(not r['in realm'] for r in rows)})")
for r in rows:
    print(f"- {r['barony']}: baron {r['baron']} [{r['family']}]{' (mixed)' if r['mixed'] else ''}"
          f"{' CAPITAL' if r['capital'] else ''} | old {r['old county']} held by {r['old count']}"
          f"{' (the baron)' if r['baron is old count'] else ''} | new {r['new county']} held by {r['new holder']}"
          f" | realm: {'yes' if r['in realm'] else 'no'} | empty in new county: {r['empty baronies in new county'] or '-'}"
          f" | others: {r['other baronies']}")
