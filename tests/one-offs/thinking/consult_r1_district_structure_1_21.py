"""Consultation round 1 (patch day 1.21), question 2: how a 1.21 holding's districts and buildings are structured.

Read-only. For a 1.21 save: per district the slot array (filled / empty), what sits at index 0 (the primary building?),
whether district.owner is the province id, per holding the count of regular districts against the slot limit, district
types by slot kind (holding/resource/regular/special fields of the province), and the province fields that point at
districts. Also what roads / markets / routes ids point at (quick range checks against provinces and titles).
Run: python -I -X utf8 tests/one-offs/thinking/consult_r1_district_structure_1_21.py <save> [label]
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

EMPTY = "4294967295"


def ids(body, key):
    m = re.search(rb"\b" + key + rb"=\{([^{}]*)\}", body)
    return m.group(1).decode().split() if m else None


def main(save, label="save"):
    g = read_save(save).gamestate
    btype = {}
    for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body):
        m = re.search(rb"type=(\w+)", g[e.open:e.open + 200])
        btype[e.key.decode()] = m.group(1).decode() if m else "?"
    dist = {}
    for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body):
        body = g[e.open:e.close]
        dist[e.key.decode()] = (re.search(rb"type=(\w+)", body).group(1).decode(), ids(body, rb"buildings") or [],
                                re.search(rb"owner=(\d+)", body).group(1).decode())
    print(f"[{label}] {len(btype)} buildings, {len(dist)} districts")
    size, filled, first = collections.Counter(), collections.Counter(), collections.Counter()
    refd = collections.Counter()
    for t, bl, _ in dist.values():
        size[len(bl)] += 1
        f = [b for b in bl if b != EMPTY]
        filled[len(f)] += 1
        for b in f:
            refd[b] += 1
        if f:
            first[(t, re.sub(r"_?\d+$", "", btype.get(bl[0], "EMPTY")))] += 1
    print("slot array size:", sorted(size.items()), "| filled per district:", sorted(filled.items()))
    print("buildings referenced by a district:", len(refd), "of", len(btype), "| by 2+ districts:",
          sum(1 for n in refd.values() if n > 1))
    print("index-0 building family by district type (top 25):", first.most_common(25))

    pkeys = collections.Counter()
    own_ok = own_bad = 0
    regular_n, over = collections.Counter(), 0
    kinds = collections.defaultdict(collections.Counter)
    size_lv = collections.Counter()
    sample = None
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", body, re.S)
        if not h:
            continue
        hb = h.group(1)
        for m in re.finditer(rb"\n\t\t\t([a-z_]+)=", hb):
            pkeys[m.group(1).decode()] += 1
        lim = re.search(rb"regular_district_slot_limit=(\d+)", hb)
        lv = re.search(rb"province_size_level=(\d+)", body)
        reg = [d for d in (ids(hb, rb"districts") or []) if d != EMPTY]
        if lim:
            regular_n[(int(lim.group(1)), len(reg))] += 1
            over += len(reg) > int(lim.group(1))
            size_lv[(lv.group(1).decode() if lv else "-", int(lim.group(1)))] += 1
        for key in (b"holding_district", b"resource_district", b"special_district", b"duchy_capital_district",
                    b"great_district", b"trade_post_district", b"entrepot_district"):
            m = re.search(rb"\b" + key + rb"=(\d+)", hb)
            if m and m.group(1).decode() in dist:
                d = dist[m.group(1).decode()]
                kinds[key.decode()][d[0]] += 1
                if d[2] == e.key.decode():
                    own_ok += 1
                else:
                    own_bad += 1
        for d in reg:
            kinds["districts(regular)"][dist[d][0]] += 1
        if sample is None and len(reg) >= 2:
            sample = (e.key.decode(), hb.decode("utf-8", "replace"),
                      {d: (dist[d][0], [btype.get(b, b) for b in dist[d][1]]) for d in reg})
    print("holding fields:", dict(pkeys))
    print("district.owner == province id:", own_ok, "ok,", own_bad, "not")
    print("(slot limit, regular districts built):", sorted(regular_n.items()), "| holdings over the limit:", over)
    print("(province_size_level, slot limit):", sorted(size_lv.items()))
    for k, c in kinds.items():
        print(f"  {k}: {c.most_common(8)}")
    if sample:
        print("sample holding", sample[0], sample[1][:700], "\n  regular districts:", sample[2])

    for path, keys in (("roads/database", (rb"trade_routes",)),
                       ("trade_markets/database", (rb"titles", rb"trade_routes")),
                       ("trade_routes/database", (rb"path", rb"trade_markets", rb"roads"))):
        try:
            b = gs.locate(g, path)
        except gs.GamestateError:
            print(f"{path}: absent")
            continue
        mx = collections.defaultdict(int)
        scal = collections.defaultdict(set)
        n = 0
        for e in gs.iter_entries(g, *b.body):
            body = g[e.open:e.close]
            n += 1
            for k in keys:
                for v in ids(body, k) or []:
                    mx[k.decode()] = max(mx[k.decode()], int(v))
            for k in (b"location", b"duchy", b"owner", b"mode", b"toll_level", b"tier"):
                m = re.search(rb"\n\t\t\t" + k + rb"=(\S+)", body)
                if m:
                    scal[k.decode()].add(m.group(1).decode())
        print(f"{path}: {n} entries; max id in lists {dict(mx)}; scalar fields:",
              {k: (sorted(v)[:6], len(v)) for k, v in scal.items()})


if __name__ == "__main__":
    main(*sys.argv[1:3])
