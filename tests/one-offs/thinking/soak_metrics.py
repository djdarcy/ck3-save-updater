"""The soak's measurements, start save against end save (goal 2026-11-20__16-02-08 S3; board U34, U39).

Three controls played the same way (observe mode, speed 5): conv-1.21 (the game's own conversion, untooled), ours-1.21
(v20) and ref-1.21 (a fresh 1.21 game). For each, the start save and the end save:
  - date, living characters, deaths by starvation (death_reason death_starved, the save's only food signal);
  - counties: prosperity (mean and histogram 1-10; 1.21 split development into prosperity and settlement size),
    county control, opinion of liege, popular opinion level;
  - provinces with a holding: settlement size level (mean, histogram);
  - the economy: districts and buildings in the databases, buildings with an unmet trade-good need (share of need
    rows), markets with their total production and need, holding income summed;
  - retention (start -> end): provinces whose district types at the start are all still there at the end.

Usage: python -I tests/one-offs/thinking/soak_metrics.py <start.ck3> <end.ck3> [label]
Prints one JSON line per save plus the retention line; reads only.
"""
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def num(b, key):
    m = re.search(rb"\n\t+" + key + rb"=(-?[\d.]+)", b)
    return float(m.group(1)) if m else None


def entries(g, path):
    try:
        loc = gs.locate(g, path)
    except Exception:
        return []
    return [(e.key.decode(), g[e.open:e.close]) for e in gs.iter_entries(g, *loc.body) if e.key]


def province_districts(g):
    dtype = {k: (re.search(rb"type=([a-z_0-9]+)", b) or [None, b"?"])[1].decode() for k, b in entries(g, "districts/database")}
    out = {}
    for pid, b in entries(g, "provinces"):
        h = re.search(rb"holding=\{", b)
        if not h:
            continue
        hb = b[h.end():gs.match_brace(b, h.end() - 1)]
        ids = set(re.findall(rb"\d+", (re.search(rb"districts=\{([^}]*)\}", hb) or [b"", b""])[1]))
        ids |= set(re.findall(rb"(?:holding|resource|duchy_capital)_district=(\d+)", hb))
        types = {dtype[i.decode()] for i in ids if i.decode() in dtype}
        if types:
            out[pid] = types
    return out


def metrics(path):
    g = read_save(path).gamestate
    m = {"save": Path(path).name, "date": (re.search(rb"\ndate=([\d.]+)", g) or [0, b"?"])[1].decode()}
    living = gs.locate(g, "living")
    m["living"] = sum(1 for e in gs.iter_entries(g, *living.body) if e.key)
    m["starved"] = len(re.findall(rb"death_reason=death_starved", g))
    cs = entries(g, "county_manager/counties")
    for key in ("prosperity", "county_control", "opinion_of_liege", "popular_opinion_level"):
        vals = [v for _, b in cs if (v := num(b, key.encode())) is not None]
        m[key] = round(st.mean(vals), 2) if vals else None
    m["prosperity_hist"] = dict(sorted(collections.Counter(int(num(b, b"prosperity") or 0) for _, b in cs).items()))
    sizes = [int(v) for pid, b in entries(g, "provinces") if b"holding={" in b and b"type=" in b
             and (v := num(b, b"province_size_level")) is not None]
    m["size_level"] = round(st.mean(sizes), 2) if sizes else None
    m["size_hist"] = dict(sorted(collections.Counter(sizes).items()))
    m["districts"] = len(entries(g, "districts/database"))
    blds = entries(g, "buildings/database")
    m["buildings"] = len(blds)
    unmet = sum(b.count(b"=unmet_building_need") for _, b in blds)
    rows = sum(b.count(b"fulfilled_trade_good_needs=") for _, b in blds) - sum(1 for _, b in blds if b"fulfilled_trade_good_needs={" in b)
    m["unmet_need_share"] = round(unmet / rows, 3) if rows else None
    mk = entries(g, "trade_markets/database")
    m["markets"] = len(mk)
    m["market_production"] = int(sum(float(x) for _, b in mk for x in re.findall(rb"\ttotal_production=([\d.]+)", b)))
    m["market_need"] = int(sum(float(x) for _, b in mk for x in re.findall(rb"\tneed=([\d.]+)", b)))
    m["holding_income"] = round(sum(float(x) for x in re.findall(rb"\n\t\t\tincome=([\d.]+)", g[gs.locate(g, "provinces").body[0]:gs.locate(g, "provinces").body[1]])), 1)
    return g, m


def main(start, end, label="?"):
    g0, m0 = metrics(start)
    g1, m1 = metrics(end)
    for m in (m0, m1):
        print(json.dumps({"label": label, **m}))
    d0, d1 = province_districts(g0), province_districts(g1)
    common = [p for p in d0 if p in d1]
    kept = sum(1 for p in common if d0[p] <= d1[p])
    lost = collections.Counter(t for p in common for t in d0[p] - d1[p])
    print(json.dumps({"label": label, "retention": f"{kept} of {len(common)} provinces keep every start district type",
                      "types_lost": dict(lost.most_common(10)), "provinces_gone": len(d0) - len(common)}))


if __name__ == "__main__":
    main(*sys.argv[1:4])
