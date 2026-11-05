"""Where a new-map county came from: its baronies in the updated save, whether each barony's key existed in the old
save and who held it there, and the county's holder and liege in the old, updated and reference saves.
Usage: python -I county_origin.py <old gamestate> <updated .ck3> <reference .ck3> <county key> [...]"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator\tests\one-offs\thinking")
import newmap_county_holders as H  # noqa: E402


def full(d):
    """{key: (holder, de_facto_liege key, de_jure_liege key)}."""
    b = H.gs.locate(d, "landed_titles/landed_titles")
    raw, by_id = {}, {}
    for e in H.gs.iter_entries(d, *b.body):
        body = d[e.open:e.close]
        k = re.search(rb'(?m)^\tkey="?([\w-]+)', body)
        if not k:
            continue
        g = {f: (m.group(1).decode() if (m := re.search(rb"(?m)^\t" + f.encode() + rb"=(\d+)", body)) else None)
             for f in ("holder", "de_facto_liege", "de_jure_liege")}
        raw[k.group(1).decode()] = g
        by_id[e.key.decode()] = k.group(1).decode()
    return {k: (g["holder"], by_id.get(g["de_facto_liege"]), by_id.get(g["de_jure_liege"])) for k, g in raw.items()}


saves = {"old 1.8": H.load(sys.argv[1]), "ours": H.load(sys.argv[2]), "reference": H.load(sys.argv[3])}
T = {n: full(d) for n, d in saves.items()}
P = {n: H.people(d) for n, d in saves.items()}
for county in sys.argv[4:]:
    print(f"== {county}")
    for n in saves:
        h, lg, dj = T[n].get(county, (None, None, None))
        print(f"  {n:9} holder {P[n].get(h)} ({h}); de facto liege {lg}; de jure liege {dj}"
              + ("" if county in T[n] else "  [title absent]"))
    for b in sorted(k for k, v in T["ours"].items() if k.startswith("b_") and v[2] == county):
        oh = T["old 1.8"].get(b)
        print(f"    {b}: in the old save {'yes' if oh else 'no'}"
              + (f", held by {P['old 1.8'].get(oh[0])} ({oh[0]}), de jure county {oh[2]}" if oh else ""))
    for n in ("ours", "reference"):
        for lgk in {T[n].get(county, (None, None, None))[1]} - {None}:
            h = T[n][lgk][0]
            print(f"  {n}: {lgk} held by {P[n].get(h)} ({h})")
