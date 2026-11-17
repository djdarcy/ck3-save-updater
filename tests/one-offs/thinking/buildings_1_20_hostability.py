"""Hostability audit, measure 1 (the Director's first item, 2026-11-17 ~16:58): v17's buildings against the 1.8.1
original and the 1.20 reference, and each against 1.20's own holding lists.

Question: did the 1.20 migration keep what the player built, and is every building v17 holds one its holding may
host in 1.20? The game reads a holding's hostable buildings from common/holdings (`buildings = { <x>_01 ... }`, plus
`primary_building`), and later tiers through each building's `next_building`.

Prediction (written first): the 1.20 reference -- a fresh game -- has 0 buildings on a holding that cannot host them
(the CONTROL: if it shows many, the reader is wrong and nothing else here counts). v17 has some, from 1.8.1
holdings carried onto 1.20 holding types, and some types not defined in vanilla 1.20 (mods, or removed keys).

Run: python -I -X utf8 tests/one-offs/thinking/buildings_1_20_hostability.py <1.8.1 save> <ref 1.20> <v17> <1.20 game dir>
Reads only; writes nothing.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def holdings(g):
    """province id -> (holding type, [building types]) from provinces/<id>/holding."""
    out = {}
    b = gs.locate(g, "provinces")
    for e in gs.iter_entries(g, *b.body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", body)
        if not h:
            continue
        rest = body[h.end():]
        t = re.search(rb'\n\t\t\ttype="?(\w+)', rest)
        m = re.search(rb"\n\t\t\tbuildings=\{(.*?)\n\t\t\t\}", rest, re.S) or \
            re.search(rb"\n\t\t\tbuildings=\{(.*?) \}\n", rest, re.S)
        blds = [x.decode() for x in re.findall(rb'type="?(\w+)', m.group(1))] if m else []
        out[e.key.decode()] = (t.group(1).decode() if t else None, blds)
    return out


def strip(text):
    return re.sub(r"#[^\n]*", "", text)


def hostable(game):
    """holding type -> every building key it may host (listed level-1 keys and the primary, then next_building)."""
    nxt, defined, special = {}, set(), set()
    for f in sorted((game / "common" / "buildings").glob("*.txt")):
        text = strip(f.read_text(encoding="utf-8-sig", errors="replace"))
        # each top-level key's block runs to the next top-level key; its next_building is the tier above it
        keys = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^(\w+)\s*=\s*\{", text)]
        defined |= {k for k, _ in keys}
        # special, duchy-capital and great buildings sit in a province's special slot, hosted by the province (its
        # history's special_building_slot), not by the holding type: measured, the control showed them all
        if re.search(r"special|duchy_capital|legendary|great_project|_ach_|background", f.name):
            special |= {k for k, _ in keys}
        for i, (k, at) in enumerate(keys):
            block = text[at:keys[i + 1][1] if i + 1 < len(keys) else len(text)]
            n = re.search(r"\bnext_building\s*=\s*(\w+)", block)
            if n:
                nxt[k] = n.group(1)
    out = {}
    text = strip((game / "common" / "holdings" / "00_holdings.txt").read_text(encoding="utf-8-sig"))
    keys = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^(\w+)\s*=\s*\{", text)]
    for i, (k, at) in enumerate(keys):
        block = text[at:keys[i + 1][1] if i + 1 < len(keys) else len(text)]
        seeds = set(re.findall(r"\bprimary_building\s*=\s*(\w+)", block))
        bl = re.search(r"\bbuildings\s*=\s*\{([^}]*)\}", block)
        if bl:
            seeds |= set(re.findall(r"\w+", bl.group(1)))
        reach, todo = set(), list(seeds)
        while todo:
            x = todo.pop()
            if x in reach:
                continue
            reach.add(x)
            if x in nxt:
                todo.append(nxt[x])
        out[k] = reach
    return out, defined, special


def audit(name, hs, host, defined, special):
    verdict = collections.Counter()
    wrong = collections.Counter()
    undefined = collections.Counter()
    for pid, (ht, blds) in hs.items():
        for b in blds:
            if b not in defined:
                verdict["not defined in vanilla 1.20"] += 1
                undefined[b] += 1
            elif b in special:
                verdict["special slot (hosted by the province, not judged here)"] += 1
            elif ht not in host:
                verdict[f"holding type not in 00_holdings ({ht})"] += 1
            elif b in host[ht]:
                verdict["hostable"] += 1
            else:
                verdict["defined, but not hostable on its holding"] += 1
                wrong[(ht, b)] += 1
    total = sum(verdict.values())
    print(f"\n== {name}: {total} buildings in {sum(1 for v in hs.values() if v[1])} holdings")
    for k, n in verdict.most_common():
        print(f"   {n:7d}  {k}")
    if wrong:
        print("   wrong holding, top 15 (holding, building):")
        for (ht, b), n in wrong.most_common(15):
            print(f"     {n:6d}  {ht:22s} {b}")
    if undefined:
        print("   not defined in vanilla 1.20, top 15:")
        for b, n in undefined.most_common(15):
            print(f"     {n:6d}  {b}")
    return verdict


def main(orig, ref, v17, game):
    host, defined, special = hostable(pathlib.Path(game))
    print(f"1.20 files: {len(defined)} building keys; holdings: " +
          ", ".join(f"{k} {len(v)}" for k, v in sorted(host.items())))
    saves = {}
    for name, p in (("1.8.1 original", orig), ("1.20 reference (CONTROL)", ref), ("v17", v17)):
        saves[name] = holdings(read_save(p).gamestate)
        audit(name, saves[name], host, defined, special)

    o, r, v = saves["1.8.1 original"], saves["1.20 reference (CONTROL)"], saves["v17"]
    print("\n== where v17's holdings came from (by province id; the 1.13 map rework renumbered provinces, so the "
          "1.8.1 column is a signal, not an identity)")
    same = collections.Counter()
    for pid, (ht, blds) in v.items():
        if not blds:
            continue
        rr, oo = r.get(pid), o.get(pid)
        key = ("= ref" if rr and sorted(rr[1]) == sorted(blds) else "!= ref") + " / " + \
              ("= 1.8.1" if oo and sorted(oo[1]) == sorted(blds) else "!= 1.8.1")
        same[key] += 1
    for k, n in same.most_common():
        print(f"   {n:7d}  {k}")
    for name, hs in saves.items():
        c = collections.Counter(b for _, bl in hs.values() for b in bl)
        print(f"   {name}: {sum(c.values())} buildings, {len(c)} types")
    co = collections.Counter(b for _, bl in o.values() for b in bl)
    cv = collections.Counter(b for _, bl in v.values() for b in bl)
    gone = [(b, n) for b, n in co.most_common() if b not in cv]
    print(f"   types in 1.8.1 and absent from v17: {len(gone)}; top 15: {gone[:15]}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
