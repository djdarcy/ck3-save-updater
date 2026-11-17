"""Patch day S6, the role table's proposal (final assessment 2026-11-17__15-28-05, step 4): for each 1.20 building
family v17 holds, where it could live in 1.21, from three signals. The table proposes; djdarcy confirms row by row.

Signals, strongest first:
  X  cross-tab: the 1.20 and 1.21 reference saves are fresh games started on 987.10.27 from the same bookmark, so
     their province ids agree. Provinces whose 1.20 holding has family F -> what the same province holds in 1.21
     (district types D:, building families B:), ranked by lift (share among F's provinces / share among all).
     This is Paradox's own conversion of its start data, and outranks the icons.
  I  icon: a 1.21 building whose type_icon is old_buildings/<F>.dds (art reuse: proposes, never decides).
  H  hostability: may the 1.21 candidate building sit on F's old holding type? 1.21's common/holdings lists each
     holding's districts, and common/districts lists each district's buildings (then next_building tiers).
     "gated" = the district has can_construct_potential, a trigger this reader does not evaluate.

Prediction (written first): most of v17's buildings by count (the big families: farms, walls, castles' own lines)
get a cross-tab candidate with lift >= 2; the icon covers about 30 families; a family with neither is a row
djdarcy decides by hand. CONTROL: the holdings' own primary lines (castle_NN, city_NN, temple_NN, tribe_NN) must map
by cross-tab to their own holding district (castle_holding_district ...); if they do not, the cross-tab is broken.

Run: python -I -X utf8 tests/one-offs/thinking/role_table_1_21.py <v17> <ref 1.20> <ref 1.21> <1.21 game dir>
Reads only; writes nothing.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

EMPTY = "4294967295"
PRIMARY = {"castle": "castle_holding_district", "city": "city_holding_district",
           "temple": "church_holding_district", "tribe": "tribal_holding_district"}


def fam(key):
    return re.sub(r"_\d+$", "", key)


def strip(text):
    return re.sub(r"#[^\n]*", "", text)


def blocks(folder):
    """key -> (block text, file name) for every top-level block in a folder's .txt files."""
    out = {}
    for f in sorted(folder.rglob("*.txt")):         # 1.21 keeps definitions in subfolders (the gamediff trap)
        text = strip(f.read_text(encoding="utf-8-sig", errors="replace"))
        keys = [(m.group(1), m.start()) for m in re.finditer(r"(?m)^(\w+)\s*=\s*\{", text)]
        for i, (k, at) in enumerate(keys):
            out[k] = (text[at:keys[i + 1][1] if i + 1 < len(keys) else len(text)], f.name)
    return out


def inner_list(block, key):
    m = re.search(r"\b" + key + r"\s*=\s*\{([^{}]*)\}", block)
    return re.findall(r"\w+", m.group(1)) if m else []


def game_tables(game):
    b = blocks(game / "common" / "buildings")
    nxt = {k: m.group(1) for k, (t, _) in b.items() if (m := re.search(r"\bnext_building\s*=\s*(\w+)", t))}
    icon = collections.defaultdict(set)
    for k, (t, _) in b.items():
        m = re.search(r'type_icon\s*=\s*"?old_buildings/(\w+)\.dds', t)
        if m:
            icon[m.group(1)].add(k)
    d = blocks(game / "common" / "districts")
    dist_b, gated = {}, set()
    for k, (t, _) in d.items():
        reach, todo = set(), inner_list(t, "buildings")
        while todo:
            x = todo.pop()
            if x not in reach:
                reach.add(x)
                if x in nxt:
                    todo.append(nxt[x])
        dist_b[k] = reach
        if "can_construct_potential" in t:
            gated.add(k)
    h = blocks(game / "common" / "holdings")
    hold_d = {k: set(inner_list(t, "districts")) | set(re.findall(r"\bprimary_district\s*=\s*(\w+)", t))
              for k, (t, _) in h.items()}
    return icon, dist_b, gated, hold_d


def host(building, holding, dist_b, gated, hold_d):
    ds = [d for d in hold_d.get(holding, ()) if building in dist_b.get(d, ())]
    if not ds:
        return "no"
    return "yes" if any(d not in gated for d in ds) else "gated"


def old_holdings(g):
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", body)
        if not h:
            continue
        rest = body[h.end():]
        t = re.search(rb'\n\t\t\ttype="?(\w+)', rest)
        m = re.search(rb"\n\t\t\tbuildings=\{(.*?)\n\t\t\t\}", rest, re.S) or \
            re.search(rb"\n\t\t\tbuildings=\{(.*?) \}\n", rest, re.S)
        out[e.key.decode()] = (t.group(1).decode() if t else None,
                               [x.decode() for x in re.findall(rb'type="?(\w+)', m.group(1))] if m else [])
    return out


def new_tokens(g):
    """province id -> {"D:<district type>", "B:<building family>"} from a 1.21 save."""
    btype = {}
    for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body):
        m = re.search(rb"type=(\w+)", g[e.open:e.open + 200])
        btype[e.key.decode()] = m.group(1).decode() if m else "?"
    dist = {}
    for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body):
        body = g[e.open:e.close]
        m = re.search(rb"\bbuildings=\{([^{}]*)\}", body)
        dist[e.key.decode()] = (re.search(rb"type=(\w+)", body).group(1).decode(),
                                [x for x in (m.group(1).decode().split() if m else []) if x != EMPTY])
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", body, re.S)
        if not h:
            continue
        hb = h.group(1)
        ids = [m.group(1).decode() for m in re.finditer(rb"\b\w*district=(\d+)", hb)]
        m = re.search(rb"\bdistricts=\{([^{}]*)\}", hb)
        ids += m.group(1).decode().split() if m else []
        toks = set()
        for d in ids:
            if d in dist:
                toks.add("D:" + dist[d][0])
                toks |= {"B:" + fam(btype.get(b, "?")) for b in dist[d][1]}
        out[e.key.decode()] = toks
    return out


def main(v17, ref20, ref21, game):
    icon, dist_b, gated, hold_d = game_tables(pathlib.Path(game))
    v = old_holdings(read_save(v17).gamestate)
    r20 = old_holdings(read_save(ref20).gamestate)
    r21 = new_tokens(read_save(ref21).gamestate)

    shared = [p for p in r20 if p in r21 and r20[p][1]]
    base = collections.Counter(t for p in shared for t in r21[p])
    by_f = collections.defaultdict(list)
    for p in shared:
        for f in {fam(b) for b in r20[p][1]}:
            by_f[f].append(p)

    count = collections.Counter()
    holds = collections.defaultdict(collections.Counter)
    for ht, bl in v.values():
        for b in bl:
            count[fam(b)] += 1
            holds[fam(b)][ht] += 1
    total = sum(count.values())
    print(f"v17: {total} buildings, {len(count)} families. Cross-tab on {len(shared)} provinces held in both "
          f"references. 1.21 files: {len(dist_b)} districts ({len(gated)} gated), icons for {len(icon)} families.\n")
    print("family | v17 n (holdings) | X cross-tab top 3 (share, lift) | I icon -> 1.21 building [host on top holding]")
    stats = collections.Counter()
    for f, n in count.most_common():
        top_h = holds[f].most_common(1)[0][0]
        ps = by_f.get(f, [])
        xs = []
        if len(ps) >= 3:
            co = collections.Counter(t for p in ps for t in r21[p])
            for t, c in co.items():
                lift = (c / len(ps)) / (base[t] / len(shared))
                if c >= 3 and lift >= 2 and c / len(ps) >= 0.2:
                    xs.append((lift, t, c / len(ps)))
            xs.sort(reverse=True)
            if f in PRIMARY:                    # the control, judged by share: a holding's own district is everywhere
                d, c = max(((t, c) for t, c in co.items() if t.startswith("D:")), key=lambda x: x[1])
                print(f"CONTROL {f}: top district by share {d} ({c / len(ps):.0%}); expected D:{PRIMARY[f]}")
        icons = sorted(icon.get(f, ()))
        ic = "; ".join(f"{b} [{host(b, top_h, dist_b, gated, hold_d)}]" for b in icons) or "-"
        xt = ", ".join(f"{t} ({s:.0%}, x{l:.1f})" for l, t, s in xs[:3]) or (f"- (only {len(ps)} provinces)"
                                                                            if len(ps) < 3 else "-")
        hs = ", ".join(f"{k} {c}" for k, c in holds[f].most_common(2))
        print(f"{f} | {n} ({hs}) | {xt} | {ic}")
        stats["X" if xs else "noX"] += n
        stats["I" if icons else "noI"] += n
        stats["neither"] += n if not xs and not icons else 0
    print(f"\nby buildings: cross-tab candidate {stats['X']} / {total}; icon {stats['I']} / {total}; "
          f"neither {stats['neither']} / {total}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
