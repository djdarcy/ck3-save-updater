"""Which buildings a 1.20 save holds that 1.21 gives no place to (djdarcy 2026-11-18 ~21:40, after the great wall's
tiers 2 and 3: "this might be a whole class of items we need to upgrade so we should identify all similar items").

A 1.21 district hosts its primary building, the first levels it lists, and every later level reached from those by
`next_building` (the game's own documentation: a district's `buildings` list holds "First levels of all buildings
buildable in the district (doesn't include the primary building)"). Every building key the save holds is then:
- hosted: some district can hold it;
- orphaned: 1.21 defines it, but no district can hold it (the great wall's tiers 2 and 3);
- removed: 1.21 does not define it at all.

Read only. Run: python -I -X utf8 tests/one-offs/thinking/orphaned_buildings.py <1.20 save> <1.21 game folder>
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

TOP = re.compile(r"(?m)^([A-Za-z_][\w\-']*)\s*=\s*\{")


def blocks(folder: pathlib.Path):
    """(file, key, body) for every top-level block of every .txt under folder, comments removed."""
    for f in sorted(folder.rglob("*.txt")):
        text = re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))
        for m in TOP.finditer(text):
            depth, i = 0, m.end() - 1
            while i < len(text):
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                if depth == 0:
                    break
                i += 1
            yield f.name, m.group(1), text[m.end():i]


def game_tables(game: pathlib.Path):
    common = game / "common"
    nxt, defined, file_of = {}, set(), {}
    for fname, key, body in blocks(common / "buildings"):
        defined.add(key)
        file_of[key] = fname
        n = re.search(r"\bnext_building\s*=\s*([\w\-']+)", body)
        if n:
            nxt[key] = n.group(1)
    roots, root_of = set(), {}
    for fname, key, body in blocks(common / "districts"):
        p = re.search(r"\bprimary_building\s*=\s*([\w\-']+)", body)
        listed = re.search(r"\bbuildings\s*=\s*\{([^}]*)\}", body)
        for b in ([p.group(1)] if p else []) + (listed.group(1).split() if listed else []):
            roots.add(b)
            root_of.setdefault(b, key)
    hosted = set()
    for r in roots:
        b, seen = r, set()
        while b and b not in seen:
            seen.add(b)
            hosted.add(b)
            b = nxt.get(b)
    return defined, hosted, file_of


def save_buildings(g: bytes):
    """building key -> count of holdings holding it, from holdings' buildings lists and the three wonder blocks."""
    c = collections.Counter()
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        b = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", b)
        if not h:
            continue
        hb = b[h.end() - 1:gs.match_brace(b, h.end() - 1) + 1]
        own = re.search(rb'\n\t\t\ttype="?(\w+)', hb)                  # the holding's own type, e.g. castle_holding
        if not own:
            continue                                                    # an empty holding: nothing built
        keys = set(re.findall(rb'\btype="?([\w\-\']+)', hb)) - {own.group(1)}
        for k in keys:
            c[k.decode()] += 1
    return c


def main(save, game):
    defined, hosted, file_of = game_tables(pathlib.Path(game))
    held = save_buildings(read_save(save).gamestate)
    cls = collections.defaultdict(list)
    for k, n in held.items():
        cls["hosted" if k in hosted else ("orphaned" if k in defined else "removed")].append((k, n))
    for name in ("removed", "orphaned"):
        rows = sorted(cls[name], key=lambda kn: (-kn[1], kn[0]))
        print(f"== {name}: {len(rows)} keys, {sum(n for _, n in rows)} holdings")
        for k, n in rows:
            print(f"{n:5}  {k}" + (f"  ({file_of[k]})" if k in file_of else ""))
    print(f"== hosted: {len(cls['hosted'])} keys, {sum(n for _, n in cls['hosted'])} holdings")


if __name__ == "__main__":
    main(*sys.argv[1:3])
