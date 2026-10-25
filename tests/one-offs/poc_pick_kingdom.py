"""Unit 2 arm A: candidate kingdoms for the single-ruler transplant.

A candidate is a k_ title in the 1.20 reference that the save does not have (no title with its key), held, by an
independent holder (the kingdom has no de facto liege), whose de jure counties are all new to the save, and which
is not under a hegemony (h_) or in China. Printed per candidate: holder, the de jure empire, de jure counties and
baronies, how many titles the holder's realm has, and the size of a rough closure (realm holders, their courts,
spouses and children).

Usage: python -I tests/one-offs/poc_pick_kingdom.py <migrated save gamestate> <reference gamestate>
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402

F = {k: re.compile(rb"\n\t" + k.encode() + rb"=(\d+)") for k in ("holder", "de_facto_liege", "de_jure_liege")}
DJV = re.compile(rb"\n\tde_jure_vassals=\{([^}]*)\}")


def titles(g):
    out = {}
    for i, e in T.entries(g, "landed_titles/landed_titles"):
        b = g[e.open:e.close]
        k = T._depth0(g, e, T._KEY)
        rec = {"key": k.decode() if k else "?"}
        for f, rx in F.items():
            m = rx.search(b)
            rec[f] = int(m.group(1)) if m else None
        m = DJV.search(b)
        rec["vassals"] = [int(x) for x in m.group(1).split()] if m else []
        out[i] = rec
    return out


def main():
    S = Path(sys.argv[1]).read_bytes()
    R = Path(sys.argv[2]).read_bytes()
    save_keys = {r["key"] for r in titles(S).values()}
    rt = titles(R)

    def chain(i):
        seen = []
        while i is not None and len(seen) < 8:
            seen.append(rt[i]["key"])
            i = rt[i]["de_jure_liege"]
        return seen

    def dejure_below(i):
        out = []
        for v in rt[i]["vassals"]:
            out.append(v)
            out += dejure_below(v)
        return out

    holders_titles = defaultdict(list)
    for i, r in rt.items():
        if r["holder"] is not None:
            holders_titles[r["holder"]].append(i)
    employer = defaultdict(list)
    for i, e in T.entries(R, "living"):
        m = re.search(rb"\n\t\temployer=(\d+)", R[e.open:e.close])
        if m:
            employer[int(m.group(1))].append(i)

    rows = []
    for i, r in rt.items():
        k = r["key"]
        if not k.startswith("k_") or k in save_keys or r["holder"] is None or r["de_facto_liege"] is not None:
            continue
        up = chain(i)
        if any(x.startswith("h_") or "china" in x for x in up):
            continue
        below = dejure_below(i)
        counties = [t for t in below if rt[t]["key"].startswith("c_")]
        if not counties or any(rt[t]["key"] in save_keys for t in below):
            continue
        realm_holders = {rt[t]["holder"] for t in below if rt[t]["holder"] is not None} | {r["holder"]}
        court = sum(len(employer[h]) for h in realm_holders)
        rows.append((len(counties), k, r["holder"], up[1] if len(up) > 1 else "-", len(below),
                     len(holders_titles[r["holder"]]), len(realm_holders), court))
    rows.sort()
    print(f"{len(rows)} candidates (counties, key, holder, de jure liege, de jure titles, holder's titles, "
          f"realm holders, their courtiers)")
    for row in rows[:25]:
        print("  ", row)

    # by realm: an independent ruler (a held title with no de facto liege) and every title de facto below them
    children = defaultdict(list)
    for i, r in rt.items():
        if r["de_facto_liege"] is not None:
            children[r["de_facto_liege"]].append(i)

    def realm(ts):
        out, todo = set(), list(ts)
        while todo:
            t = todo.pop()
            if t in out:
                continue
            out.add(t)
            todo += children[t]
            h = rt[t]["holder"]
            if h is not None and t != todo:
                todo += [x for x in holders_titles[h] if x not in out]
        return out

    tops = {r["holder"] for i, r in rt.items() if r["holder"] is not None and r["de_facto_liege"] is None}
    rows2 = []
    for h in tops:
        mine = holders_titles[h]
        if any(rt[t]["de_facto_liege"] is not None for t in mine):
            continue                                    # holds something under another liege: not independent
        rl = realm(mine)
        keys = [rt[t]["key"] for t in rl]
        if any(k in save_keys for k in keys) or any(k.startswith("h_") or "china" in k for k in keys):
            continue
        if any("china" in x or x.startswith("h_") for t in mine for x in chain(t)):
            continue
        tier = max((k[0] for k in keys if not k.startswith("x_")), key="bcdke".index, default="b")
        counties = sum(1 for k in keys if k.startswith("c_"))
        holders = {rt[t]["holder"] for t in rl if rt[t]["holder"] is not None}
        court = sum(len(employer[x]) for x in holders)
        top_keys = sorted((k for k in keys if k[0] in "ke"), key=len)[:3]
        rows2.append((tier, counties, len(rl), len(holders), court, h, top_keys))
    rows2.sort(key=lambda r: ("bcdke".index(r[0]) * -1, r[1]))
    print(f"\n{len(rows2)} independent rulers whose whole realm is new (tier, counties, realm titles, holders, "
          f"courtiers, ruler, top titles)")
    for row in [r for r in rows2 if r[0] in "ke"][:20]:
        print("  ", row)
    print("duke-tier, 3 or more counties:")
    for row in sorted([r for r in rows2 if r[0] == "d" and r[1] >= 3], key=lambda r: r[1])[:25]:
        print("  ", row)


if __name__ == "__main__":
    main()
