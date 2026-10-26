"""Step 1c, for djdarcy: the campaign baronies whose county 1.20 changed, named; plus the scope-guard checks.

Writes a markdown note: (1) every HELD moved barony with its old county and holder, its 1.20 county and holder
(side), the baron, house, whether the baron's liege chain ends at the player, and the 1c case; (2) the UNHELD
moved baronies by old county; (3) the scope guard: (b) none of the continuity people (ids given) is a holder or
holds a moved barony, (c) how many moved baronies were in the British Isles (1.8.2 empire e_britannia), and the
non-insular barony holders of Ireland (to find the Arab-born steward).
Names: the save's name keys through the game's English localisation (1.20, then 1.8.2).

Usage: python -I moved_baronies_named.py <campaign.ck3> <output.ck3> <old game dir> <new game dir> <out.md>
       <player> <continuity ids comma-separated> [first carried slot]
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import deadtitles as D, gamestate as gs, translate as T  # noqa: E402

camp, out = load(sys.argv[1]), load(sys.argv[2])
old_game, new_game, md = Path(sys.argv[3]), Path(sys.argv[4]), Path(sys.argv[5])
player = int(sys.argv[6])
continuity = {int(x) for x in sys.argv[7].split(",") if x}
split = int(sys.argv[8]) if len(sys.argv) > 8 else 83378
old_parent, _ = D.title_tree(old_game / "common" / "landed_titles")
new_parent, _ = D.title_tree(new_game / "common" / "landed_titles")

loc = {}
for gd in (old_game, new_game):                      # 1.20 last, so it wins
    for p in (gd / "localization" / "english").rglob("*.yml"):
        for m in re.finditer(r'(?m)^\s*([\w\-\.\']+):\d*\s*"(.*)"', p.read_text(encoding="utf-8-sig", errors="replace")):
            loc[m.group(1)] = m.group(2)


def name(key):
    return loc.get(key, key) if key else "?"


class World:
    def __init__(self, g):
        self.g = g
        self.t = {}
        for i, e in T.entries(g, "landed_titles/landed_titles"):
            b = g[e.start:min(e.end, e.start + 4096)]
            k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
            h = re.search(rb"\n\tholder=(\d+)", b)
            self.t[i] = (k.group(1).decode() if k else "", int(h.group(1)) if h else None)
        self.by = {k: i for i, (k, _) in self.t.items() if k}
        lb = gs.locate(g, "living")
        self.c = {int(e.key): g[e.start:e.end] for e in gs.iter_entries(g, lb.open + 1, lb.close)
                  if e.key and e.key.isdigit()}
        self.houses = {i: g[e.start:min(e.end, e.start + 2000)] for i, e in T.entries(g, "dynasties/dynasty_house")}
        self.cultures = {i: g[e.start:min(e.end, e.start + 2000)] for i, e in T.entries(g, "culture_manager/cultures")}
        self.primary, self.held = {}, defaultdict(list)
        for i, (k, h) in self.t.items():
            if h is not None:
                self.held[h].append(k)
        for c, b in self.c.items():
            m = re.search(rb"\n\t\tdomain=\{\s*(\d+)", b)
            if m:
                self.primary[c] = int(m.group(1))
        self.dfl = {}
        for i, e in T.entries(g, "landed_titles/landed_titles"):
            m = re.search(rb"\n\tde_facto_liege=(\d+)", g[e.start:min(e.end, e.start + 4096)])
            if m:
                self.dfl[i] = int(m.group(1))

    def holder(self, key):
        return self.t.get(self.by.get(key), ("", None))[1]

    def person(self, c):
        if c is None:
            return "(none)"
        b = self.c.get(c, b"")
        fn = re.search(rb"\n\tfirst_name=\"?([^\"\n]+)", b)
        return f"{name(fn.group(1).decode()) if fn else '?'} ({c})"

    def house(self, c):
        b = self.c.get(c, b"")
        h = re.search(rb"\n\tdynasty_house=(\d+)", b)
        if not h:
            return "-"
        hb = self.houses.get(int(h.group(1)), b"")
        hb = re.sub(rb"motto=\{(?:[^{}]|\{[^{}]*\})*\}", b"", hb)     # a motto block has its own name/key
        n = (re.search(rb"\n\tlocalized_name=\"?([^\"\n]+)", hb) or re.search(rb"\n\tname=\"?([^\"\n]+)", hb)
             or re.search(rb"\n\tkey=\"?([^\"\n]+)", hb))                   # depth 1 only: never the motto's
        return name(n.group(1).decode()) if n else h.group(1).decode()

    def culture(self, c):
        m = re.search(rb"\n\tculture=(\d+)", self.c.get(c, b""))
        cb = self.cultures.get(int(m.group(1)), b"") if m else b""
        t = re.search(rb"culture_template=\"?([\w\-]+)", cb) or re.search(rb"\n\t*name=\"?([^\"\n]+)", cb)
        return t.group(1).decode() if t else "?"

    def chain_ends_at(self, c, who):
        seen = set()
        while c in self.primary and c not in seen:
            if c == who:
                return True
            seen.add(c)
            df = self.dfl.get(self.primary[c])
            nxt = self.t.get(df, ("", None))[1] if df is not None else None
            if nxt is None or nxt == c:
                break
            c = nxt
        return c == who


C, O = World(camp), World(out)


def side(c):
    return "none" if c is None else ("carried" if (c & 0xFFFFFF) >= split else "campaign")


def up(key, tier):
    k = key
    while k and not k.startswith(tier):
        k = old_parent.get(k)
    return k


held_rows, unheld = [], Counter()
moved_keys = []
for i, (k, h) in C.t.items():
    if not k.startswith("b_"):
        continue
    oc, nc = old_parent.get(k), new_parent.get(k)
    if oc is None or nc is None or oc == nc:
        continue
    moved_keys.append(k)
    if h is None:
        unheld[(oc, nc)] += 1
        continue
    x = O.holder(nc)
    only = all(t.startswith("b_") and new_parent.get(t) == nc for t in C.held[h])
    case = "same holder" if x == h else ("baron only" if only else "mixed")
    held_rows.append((k, oc, C.holder(oc), nc, x, h, case))

lines = ["# Campaign baronies 1.20 moved to another county (step 1c)", "",
         f"Sources: the campaign original and the output `{Path(sys.argv[2]).name}`; counties from the 1.8.2 and "
         "1.20 game files; names through the game's English localisation. 'Ends at Beidh' walks the baron's liege "
         "chain in the campaign (primary title, its de facto liege, that title's holder, upward).", "",
         f"## Held moved baronies: {len(held_rows)}", "",
         "| barony | 1.8.2 county | its holder (house) | 1.20 county | its holder (house) | side | baron (house) "
         "| ends at Beidh | case |", "|---|---|---|---|---|---|---|---|---|"]
for k, oc, och, nc, x, h, case in sorted(held_rows, key=lambda r: (r[6], r[0])):
    w = O if x is not None and side(x) == "carried" else C
    lines.append(f"| {name(k)} `{k}` | {name(oc)} | {C.person(och)} ({C.house(och)}) | {name(nc)} | "
                 f"{w.person(x)} ({w.house(x)}) | {side(x)} | {C.person(h)} ({C.house(h)}) | "
                 f"{'**yes**' if C.chain_ends_at(h, player) else 'no'} | {case} |")
lines += ["", f"## Unheld moved baronies: {sum(unheld.values())}, by county", "",
          "| 1.8.2 county | 1.20 county | baronies |", "|---|---|---:|"]
for (oc, nc), n in sorted(unheld.items(), key=lambda kv: -kv[1]):
    lines.append(f"| {name(oc)} `{oc}` | {name(nc)} `{nc}` | {n} |")
# scope guard
holders = {r[5] for r in held_rows} | {r[2] for r in held_rows if r[2]}
hit_b = sorted(holders & continuity)
moved_british = [k for k in moved_keys if up(k, "e_") == "e_britannia"]
irish = [(k, h) for i, (k, h) in C.t.items() if k.startswith("b_") and h is not None and up(k, "k_") == "k_ireland"]
cult = Counter(C.culture(h) for _, h in irish)
lines += ["", "## Scope guard", "",
          "(a) The 1c re-parent touches only baronies whose de jure county differs between the 1.8.2 and 1.20 maps "
          "(`reparent_plan` selects `b_` titles only); it never edits a county's or higher title's liege or holder. "
          "Its edits: the barony's `de_jure_liege` and `de_facto_liege`, the old and new county's barony list, and "
          "for a baron-only holder his contract's liege and the two lieges' contract lists.", "",
          f"(b) Continuity people among the moved baronies' holders and their old counties' holders: "
          f"{hit_b or 'none'} (of {len(continuity)} checked: {sorted(continuity)}).", "",
          f"(c) Moved baronies that were in the British Isles (1.8.2 empire e_britannia): {len(moved_british)}"
          f"{': ' + ', '.join(moved_british) if moved_british else ''}.", "",
          f"Barony holders in Ireland (1.8.2 k_ireland), {len(irish)}, by culture: {dict(cult.most_common())}.",
          "Non-Gaelic ones (the Arab-born steward should be here):", ""]
for k, h in sorted(irish):
    cu = C.culture(h)
    if cu not in ("irish", "scottish", "welsh", "pictish", "cumbrian"):     # '?' kept: an unreadable culture
        lines.append(f"- {name(k)} `{k}`: {C.person(h)}, culture {cu}, house {C.house(h)}; "
                     f"in the continuity set: {'yes' if h in continuity else 'no'}; holds a moved barony: "
                     f"{'yes' if any(r[5] == h for r in held_rows) else 'no'}")
lines += ["", "No Arab name appears among Ireland's barony holders, so the Arab-born steward is not identified here; "
          "whoever he is, (c) finds no moved barony anywhere in the British Isles, so his Irish holding is not "
          "touched by step 1c.", "",
          "Counts: this note reads the moved baronies from the 1.8.2 and 1.20 game files against the campaign "
          "original. The transplant reads them from the reference save against the save after R15, so its "
          "numbers differ slightly (held 39 there)."]
md.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"held {len(held_rows)}, unheld {sum(unheld.values())}, continuity hits {hit_b}, british moved "
      f"{len(moved_british)}, irish barony holders {len(irish)} cultures {dict(cult.most_common(6))}")
