"""S1 of the built-state carry goal (goals/2026-11-19__01-33-58): the role table as a cited successor table.

For every (1.20 building family, holding type) pair v17 holds, the 1.21 building it becomes and the district that hosts
it, from four sources, and whether the game's files settle the row or djdarcy must (the Director's plan, S1: "rows the
game's own files determine go in without his check; he sees only the rows where the sources disagree or none applies").

Sources, in this order:
  same   the family still exists in 1.21 (key for key, S0 (2)) and host_rules says it may stand on this holding;
  cross  the cross-tab of role_table_1_21.py (the two fresh references share province ids): the 1.21 building family
         most lifted where 1.20 had this family -- only real buildings (not a district's own pb_* line), and only if
         host_rules puts its first tier in a regular district of this holding;
  icon   a 1.21 building drawn with this family's old icon, hostable the same way.
Kinds kept out of the table, with their reason: the holding's own line (the conversion keeps it), wonders and
duchy-capital buildings (their own <key>_district; R33 and R35 carry them).

A row is SETTLED when `same` holds, or when exactly one of cross/icon is hostable, or both agree. It is DJDARCY's when
cross and icon are both hostable and disagree, or when no source gives a hostable building (a gated-only candidate is
shown as the recommendation, never taken).

Prediction (written before the run, 02:58): the settled rows cover >= 90% of the carried instances; djdarcy's rows are
roughly the 453 "neither" instances plus a few disagreements, under 1,000 instances in all. CONTROL: the four holding
lines (castle, city, temple, tribe) come out as "holding line", never as a carried row.

Run: python -I -X utf8 tests/one-offs/thinking/s1_successor_table.py <v17> <ref 1.20> <ref 1.21> <1.21 game dir> <out.json>
Reads the saves and the game; writes only <out.json>.
"""
import collections
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))
from ck3_save_migrator import host_rules  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402
import role_table_1_21 as rt  # noqa: E402


def first_tier(rules, family):
    """The lowest tier key 1.21 defines for a family (castle_01, meadowlands_pastures_1), or None."""
    keys = [k for k in rules.buildings if re.fullmatch(re.escape(family) + r"(_\d+)?", k)]
    if not keys:
        return None
    return min(keys, key=lambda k: int(k.rsplit("_", 1)[1]) if k.rsplit("_", 1)[-1].isdigit() else 0)


def hosting(rules, building, holding):
    """(verdict, district key, district kind) -- the regular or holding district of `holding` that hosts `building`."""
    v = rules.building_on(building, holding)
    if v.ok is False or holding not in rules.holdings:
        return v, None, None
    names, _ = rules.holdings[holding]
    ds = [rules.districts[d] for d in sorted(names) if d in rules.districts and building in rules.districts[d].buildings]
    ds.sort(key=lambda d: (d.gated, d.kind != "regular"))
    return v, ds[0].key, ds[0].kind


SKIP = {"construction_time", "cost_gold", "cost_prestige", "cost_piety", "levy", "garrison", "max_garrison", "ai_value",
          "base", "value", "factor", "add", "multiply", "years", "months", "days"}


def modifiers(game_dir):
    """building key -> the set of numeric-valued keys in its block (its modifiers, by name), from common/buildings."""
    out = {}
    for f in sorted((pathlib.Path(game_dir) / "common" / "buildings").rglob("*.txt")):
        for key, body, _ in host_rules._blocks(f):
            out[key] = {k for k in re.findall(r"\b([a-z][a-z_]+)\s*=\s*-?\d", body) if k not in SKIP}
    return out


def effects_candidates(rules, old_mods, new_mods, family, holding, top=3):
    """Proposal only: 1.21 first-tier buildings in a regular district of `holding`, ranked by the overlap (Jaccard) of
    their modifier names with the old family's first tier in 1.20."""
    old_key = next((k for k in (family + "_01", family + "_1", family) if k in old_mods), None)
    if not old_key or holding not in rules.holdings:
        return []
    mine = old_mods[old_key]
    names, _ = rules.holdings[holding]
    seen = {}
    for d in sorted(names):
        dist = rules.districts.get(d)
        if not dist or dist.kind != "regular":
            continue
        for b in dist.buildings:
            if b == first_tier(rules, rt.fam(b)) and b in new_mods and mine | new_mods[b]:
                j = len(mine & new_mods[b]) / len(mine | new_mods[b])
                if j > seen.get(b, (0,))[0]:
                    seen[b] = (round(j, 2), d, dist.gated, sorted(mine & new_mods[b])[:6])
    ranked = sorted(seen.items(), key=lambda x: -x[1][0])[:top]
    return [{"building": b, "score": s, "district": d, "gated": g, "shared": sh} for b, (s, d, g, sh) in ranked]


def main(v17, ref20, ref21, game, out, old_game=None):
    rules = host_rules.load(game)
    new_mods = modifiers(game)
    old_mods = modifiers(old_game) if old_game else {}
    icon, *_ = rt.game_tables(pathlib.Path(game))
    holding_lines = {rt.fam(re.sub(r"\s", "", m)) for d in rules.districts.values() if d.kind == "holding"
                     for m in d.buildings if re.search(r"_0?1$", m)}
    v = rt.old_holdings(read_save(v17).gamestate)
    r20 = rt.old_holdings(read_save(ref20).gamestate)
    r21 = rt.new_tokens(read_save(ref21).gamestate)
    shared = [p for p in r20 if p in r21 and r20[p][1]]
    base = collections.Counter(t for p in shared for t in r21[p])
    by_f = collections.defaultdict(list)
    for p in shared:
        for f in {rt.fam(b) for b in r20[p][1]}:
            by_f[f].append(p)

    pairs = collections.Counter()
    levels = collections.defaultdict(collections.Counter)
    for ht, bl in v.values():
        for b in bl:
            pairs[(rt.fam(b), ht)] += 1
            levels[(rt.fam(b), ht)][b] += 1

    rows, stats = [], collections.Counter()
    for (f, ht), n in pairs.most_common():
        row = {"family": f, "holding": ht, "instances": n, "keys": dict(levels[(f, ht)])}
        ft = first_tier(rules, f)
        if f in holding_lines:
            row.update(kind="holding line", reason="the holding's own building; the conversion keeps it")
        elif rules.wonder_district(ft or f + "_01")[0] or rules.wonder_district(f)[0]:
            row.update(kind="wonder", reason="its own <key>_district; carried by R33/R35")
        else:
            cands = {}
            if ft:
                vd, dk, kind = hosting(rules, ft, ht)
                cands["same"] = (ft, vd, dk, kind)
            ps = by_f.get(f, [])
            if len(ps) >= 3:
                co = collections.Counter(t for p in ps for t in r21[p])
                xs = []
                for t, c in co.items():
                    if not t.startswith("B:") or t[2:].startswith("pb_") or t[2:] in holding_lines:
                        continue
                    lift = (c / len(ps)) / (base[t] / len(shared))
                    if c >= 3 and lift >= 2 and c / len(ps) >= 0.2:
                        b1 = first_tier(rules, t[2:])
                        if b1:
                            vd, dk, kind = hosting(rules, b1, ht)
                            if vd.ok and kind == "regular":
                                xs.append((lift, b1, vd, dk, kind))
                if xs:
                    lift, b1, vd, dk, kind = max(xs, key=lambda x: x[0])
                    cands["cross"] = (b1, vd, dk, kind)
                    row["cross_lift"] = round(lift, 1)
            ics = []
            for b in sorted(icon.get(f, ())):
                vd, dk, kind = hosting(rules, b, ht)
                ics.append((b, vd, dk, kind))
            good_ic = [x for x in ics if x[1].ok and x[3] == "regular"]
            if good_ic:
                cands["icon"] = good_ic[0]
            gated = [x for x in ics if x[1].ok is None]

            # 03:0x, after the first run: the cross-tab measures co-location, not succession (pastures -> communal_wells,
            # barracks -> communal_wells, plantations -> minaret), so it is shown and never decides
            same = cands.get("same")
            if same and same[1].ok:
                pick, src = same, "same"
            elif "icon" in cands:
                pick, src = cands["icon"], "icon"
            else:
                pick, src = None, "none"
            if not pick:
                row["effects"] = effects_candidates(rules, old_mods, new_mods, f, ht)
            row["sources"] = {k: {"building": c[0], "ok": c[1].ok, "district": c[2], "kind": c[3], "where": c[1].where,
                                  "why": c[1].why} for k, c in cands.items()}
            if gated:
                row["gated_candidates"] = [g[0] for g in gated]
            if pick:
                row.update(kind="settled", source=src, successor=pick[0], district=pick[2], where=pick[1].where)
            else:
                row.update(kind="djdarcy", source=src)
        rows.append(row)
        stats[row["kind"]] += n

    pathlib.Path(out).write_text(json.dumps(rows, indent=1), encoding="utf-8")
    carried = stats["settled"] + stats["djdarcy"]
    print(f"pairs {len(rows)}, instances {sum(pairs.values())}")
    for k in ("holding line", "wonder", "settled", "djdarcy"):
        print(f"  {k:13} {stats[k]:6}  rows {sum(1 for r in rows if r['kind'] == k)}")
    print(f"settled share of carried instances: {stats['settled'] / carried:.1%}")
    by_src = collections.Counter()
    for r in rows:
        if r["kind"] in ("settled", "djdarcy"):
            by_src[(r["kind"], r["source"])] += r["instances"]
    print("by source:", dict(by_src))
    ctl = {r["family"]: r["kind"] for r in rows if r["family"] in ("castle", "city", "temple", "tribe")}
    print("CONTROL holding lines:", ctl)


if __name__ == "__main__":
    main(*sys.argv[1:7])
