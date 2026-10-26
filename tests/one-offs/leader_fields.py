"""R20 candidate: what the engine sets on the campaign's mercenary company leaders when it converts a 1.8.1 save.

For each company leader of the campaign (title holder of each mercenary company's title, read in the campaign
save), compare the leader's entry across witnesses: the campaign original (1.8.1), the engine's chain product
(1.20), and our output. Reports, per field path (top-level and landed_data/*), how often the field is present in
each witness, and for scalar fields the most common values; also the fields the chain adds or drops relative to
the original, and the ones ours lacks relative to the chain.
Usage: python -I leader_fields.py <campaign.ck3> <chain.ck3> <ours.ck3>
"""
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shape_diff import load  # noqa: E402
from ck3_save_migrator import gamestate as gs, translate as T  # noqa: E402


def leaders(g):
    titles = {i: g[e.start:min(e.end, e.start + 4096)] for i, e in T.entries(g, "landed_titles/landed_titles")}
    out = set()
    for _, e in T.entries(g, "mercenary_company_manager/mercenary_companies"):
        t = re.search(rb"[\n\t]title=(\d+)", g[e.start:e.end])
        if t and int(t.group(1)) in titles:
            h = re.search(rb"\n\tholder=(\d+)", titles[int(t.group(1))])
            if h:
                out.add(int(h.group(1)))
    return out


def entry_index(g, lb, wanted):
    """id -> entry bytes for the wanted ids, from one pass over the section's top-level entries."""
    out = {}
    for e in gs.iter_entries(g, lb.open + 1, lb.close):
        if e.key is not None and e.key.isdigit() and int(e.key) in wanted:
            out[int(e.key)] = g[e.start:e.end]
    return out


def fields(body):
    """field path -> value text (scalars) or '{...}' (blocks), for depth 1 and landed_data/* depth 2."""
    out = {}
    lines = body.split(b"\n")
    depth, block = 0, None
    for ln in lines[1:]:
        s = ln.strip()
        m = re.match(rb"([a-z_]+)=(.*)", s)
        if m and depth == 0:
            k, v = m.group(1).decode(), m.group(2)
            out[k] = "{...}" if v.startswith(b"{") else v.decode(errors="replace")[:40]
            if v.startswith(b"{") and not v.rstrip().endswith(b"}"):
                block = k
        elif m and depth == 1 and block == "landed_data":
            k, v = m.group(1).decode(), m.group(2)
            out["landed_data/" + k] = "{...}" if v.startswith(b"{") else v.decode(errors="replace")[:40]
        depth += s.count(b"{") - s.count(b"}")
        if depth == 0:
            block = None
    return out


args = [a for a in sys.argv[1:] if not a.startswith("--")]
names = tuple(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--names=")) or ("campaign", "chain", "ours")
names = names[0].split(",") if len(names) == 1 and "," in names[0] else names
gsx = [load(p) for p in args[:3]]
ids = sorted(leaders(gsx[0]))
print("campaign company leaders:", len(ids))
# --rulers=N: instead, N other rulers of the first save (title holders that lead no company), every k-th one
rul = [int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--rulers=")]
if rul:
    tl = {i: gsx[0][e.start:min(e.end, e.start + 4096)] for i, e in T.entries(gsx[0], "landed_titles/landed_titles")}
    hs = sorted({int(m.group(1)) for b in tl.values() if (m := re.search(rb"\n\tholder=(\d+)", b))} - set(ids))
    ids = hs[::max(1, len(hs) // rul[0])][:rul[0]]
    print("other rulers sampled:", len(ids), "of", len(hs))
pres = defaultdict(Counter)
vals = defaultdict(lambda: defaultdict(Counter))
for name, g in zip(names, gsx):
    idx = entry_index(g, gs.locate(g, "living"), set(ids))
    for i in ids:
        b = idx.get(i)
        if b is None:
            pres["<entry>"][name + " absent"] += 1
            continue
        for k, v in fields(b).items():
            pres[k][name] += 1
            vals[k][name][v] += 1
n0, n1, n2 = names[:3]
print(f"\n{'field':40} {n0:>9} {n1:>9} {n2:>9}   {n1} values (top 3)")
for k in sorted(pres, key=lambda k: (-(pres[k][n1] - pres[k][n0] != 0), k)):
    p = pres[k]
    if p[n0] == p[n1] == p[n2] and len(vals[k][n1]) <= 1 and vals[k][n1] == vals[k][n0]:
        continue
    top = ", ".join(f"{v} x{n}" for v, n in vals[k][n1].most_common(3))
    flag = "" if p[n1] == p[n2] else f"   <- {n2} differs"
    print(f"{k:40} {p[n0]:>9} {p[n1]:>9} {p[n2]:>9}   {top}{flag}")
