"""Could a 1.20 resource-type building become the 1.21 resource district of its province?

djdarcy 2026-11-19: "when we see 1.20 quarries that means we should add a "stone district" if that's valid and makes
sense for that part of the map? Can users just add a "stone district" arbitrarily ...?" 1.21's resource districts are
player-buildable: common/districts/resource_districts.txt gives each `can_construct_potential = { county = {
has_potential_for_trade_good = trade_good_type:trade_good_X } }` and `can_be_replaced = yes`; a province holds one,
as `resource_district=<id>` in its holding.

For a 1.20 family F mapped to a resource district R with trade good X (argv), over the provinces where v17 has F built:
does the county have potential for X (common/trade/county_potential_trade_goods), and what resource district does the
province hold in v19 (R already / another one / none)?

Prediction (written first): most quarry counties have stone potential (1.20 quarries had their own terrain gate); most
of those provinces hold some other resource district in v19, so the choice is "replace" more often than "add".

Run: python -I -X utf8 tests/one-offs/thinking/resource_district_fit.py <v17> <v19> <1.21 game dir> <family> <district> <good>
     e.g. ... quarries stone_district stone
Read-only.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.deadtitles import title_tree  # noqa: E402
from ck3_save_migrator.district_lint import county_potential_goods  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402


def provinces(g):
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if e.key and e.key.isdigit():
            yield e.key.decode(), g[e.open:e.close]


def resource_goods(game):
    """resource district -> the trade good its can_construct_potential asks the county to have potential for."""
    from ck3_save_migrator import host_rules
    out = {}
    for k, body, _ in host_rules._blocks(pathlib.Path(game) / "common" / "districts" / "resource_districts.txt"):
        m = re.search(r"has_potential_for_trade_good\s*=\s*trade_good_type:trade_good_(\w+)", body)
        if m:
            out[k] = m.group(1)
    return out


def load(v17, v19, game):
    parent, prov = title_tree(pathlib.Path(game) / "common" / "landed_titles")
    county_of = {str(p): parent.get(b) for b, p in prov.items()}
    w_bodies = dict(provinces(read_save(v17).gamestate))
    g = read_save(v19).gamestate
    D = {e.key.decode(): g[e.open:e.close + 1] for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if e.key}
    have = {}
    for pid, body in provinces(g):
        m = re.search(rb"\n\t\t\tresource_district=(\d+)", body)
        if m:
            t = re.search(rb"type=([a-z_0-9]+)", D.get(m.group(1).decode(), b""))
            have[pid] = t.group(1).decode() if t else "?"
    return county_of, county_potential_goods(game), w_bodies, have


def auto(v17, v19, game, icon_clip, floor="0.88"):
    """Every (1.20 family, resource district) pair the CLIP run proposed (district_buildings/<x>_district at >= floor)."""
    import json
    rg = resource_goods(game)
    state = load(v17, v19, game)
    for r in json.loads(pathlib.Path(icon_clip).read_text(encoding="utf-8")):
        for t in r["top"]:
            d = t["icon"].split("/")[-1]
            if t["icon"].startswith("district_buildings/") and d in rg and t["cosine"] >= float(floor):
                print(f"\n== {r['family']} -> {d} (good {rg[d]}, imgcompare {t['cosine']})")
                fit(state, r["family"], d, rg[d])


def main(v17, v19, game, family, district, good):
    fit(load(v17, v19, game), family, district, good)


def fit(state, family, district, good):
    county_of, goods, w_bodies, have = state
    # built buildings are `type="quarries_02"`; a construction is `building="quarries_03"`, so type= alone is built
    built = {pid for pid, body in w_bodies.items() if re.search(rb'\btype="?' + family.encode() + rb"_\d+", body)}
    rows = collections.Counter()
    others = collections.Counter()
    for pid in built:
        pot = good in goods.get(county_of.get(pid) or "", ())
        cur = have.get(pid)
        state = "already" if cur == district else ("other" if cur else "none")
        rows[(pot, state)] += 1
        if pot and state == "other":
            others[cur] += 1
    print(f"v17 provinces with {family} built: {len(built)}")
    for pot in (True, False):
        for state in ("already", "none", "other"):
            print(f"  county {'has' if pot else 'lacks'} {good} potential, v19 resource district {state:7s}: {rows[(pot, state)]}")
    print(f"  where it would replace another resource district, the ones replaced: {others.most_common(8)}")


if __name__ == "__main__":
    if sys.argv[1] == "--auto":   # --auto <v17> <v19> <game> <icon_clip.json> [floor]
        auto(*sys.argv[2:])
    else:
        main(*sys.argv[1:])
