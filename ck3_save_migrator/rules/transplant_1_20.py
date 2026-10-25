"""Transplant rules for 1.8.1 -> 1.20.1.2: bring 1.20's new map regions in from a reference save.

1.20 added 3,609 provinces and 5,655 titles (East and Southeast Asia, Tibet, Japan, ...) that a 1.8.1 save has
never heard of; loaded as is, every one of those titles is unheld and the engine hands them to the player. These
rules copy them from a save written by 1.20 at the campaign's date (the reference), with every id translated by
R13 (``translate.py``) and the campaign's own world left as it is.

The rules PLAN into one ``transplant.Transplant`` kept in ``ctx.state``; R17 writes the plan in one pass (the edge
policy must know every copied object before any reference is kept). Selecting R14, R15 or R16 brings R17 along.

* R14 new-titles: every reference title whose key the save does not have (runtime ``x_`` titles excepted), with
  the province entries of the provinces the save does not have. New titles under an existing parent are stitched
  into that parent's de jure list when R17 writes.
"""

from __future__ import annotations

import re

from .. import translate as T
from ..transplant import TITLES, Transplant
from ..savefile import CK3Save
from .religion_1_20 import reference_gamestate


def transplant_of(save: CK3Save, ctx) -> Transplant:
    """The context's shared transplant plan (built on first use, against the save as the earlier rules left it)."""
    if "transplant" not in ctx.state:
        ctx.state["transplant"] = Transplant(save.gamestate, reference_gamestate(ctx))
    return ctx.state["transplant"]


def _skip(rule, why: str):
    return rule.result(extra={"skipped": why})


def r14_new_titles(save: CK3Save, ctx, rule):
    """Plan every reference title the save lacks (by key, runtime x_ titles excepted) and every reference
    province entry whose id the save lacks. Writes nothing; R17 does."""
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference): the new titles come from a 1.20 save")
    t = transplant_of(save, ctx)
    save_keys = set(T.keyed(save.gamestate, TITLES))
    ref_keys = t.title_keys()
    new = {i for i, k in ref_keys.items() if k.encode() not in save_keys and not k.startswith("x_")}
    # left to the engine: an unheld title with no land under it (it creates missing definitions itself, and a
    # copy can collide with a campaign construct of the same name: d_knights_hospitaller)
    held = t.title_holders(new)
    landless = {i for i in new if ref_keys[i][0] in "dkeh" and i not in held
                and not any(p.startswith("de_jure_vassals") for p, _, _ in
                            t.references(TITLES, i, t.entries(TITLES)[i]))}
    # a holy order that leases campaign land: 1.20 does not add these to an old save by itself (two months of
    # play on the migrated save created none of the 12), so they are expansion content -- added "as is" with
    # their leases unless --no-expansion-orders, and reported either way
    join = t.tr.spaces["title"].join
    ho_campaign = {own for own, leased in t.holy_order_titles().values()
                   if own is not None and any(x in join for x in leased)}
    t.expansion_orders = ctx.expansion_orders
    new -= landless
    if not ctx.expansion_orders:
        new -= ho_campaign
    save_provinces = {i for i, _ in T.entries(save.gamestate, "provinces")}
    provinces = set(t.entries("provinces")) - save_provinces
    t.add("title", new, "R14")
    t.add("province", provinces, "R14")
    tiers = {}
    for i in new:
        tiers[ref_keys[i][0]] = tiers.get(ref_keys[i][0], 0) + 1
    return rule.result(matched=len(new) + len(provinces),
                       extra={"titles_planned": len(new), "by_tier": dict(sorted(tiers.items())),
                              "left_to_the_engine_unheld_landless": len(landless),
                              "holy_order_titles_leasing_campaign_land": sorted(ref_keys[i] for i in ho_campaign),
                              "expansion_orders": "added" if ctx.expansion_orders else "left out",
                              "provinces_planned": len(provinces),
                              "x_titles_left_out": sum(1 for k in ref_keys.values() if k.startswith("x_"))})


def r15_dead_titles(save: CK3Save, ctx, rule):
    """Settle the save's titles the target no longer defines, and its moved baronies, by place: a clean mapping
    renames the save's title to its successor (id and holder kept); any other is removed with every reference
    to it, and the reference's titles for that land come in through R14. Runs before R14, edits the save at
    once so the joins see the new keys, and leaves its table in ctx.state for the report."""
    from .. import deadtitles as D
    from .. import gamestate as gs
    from ..lint import defined_title_keys
    if ctx.old_game_dir is None or ctx.game_dir is None:
        return _skip(rule, "needs --old-game-dir (the save's own version's game folder) and --game-dir")
    _, conversion = defined_title_keys(ctx.game_dir)
    maps = D.classify(save.gamestate, ctx.old_game_dir / "common" / "landed_titles",
                      ctx.game_dir / "common" / "landed_titles", set(conversion))
    ep = gs.EditPass()
    applied = D.apply(save.gamestate, maps, ep)
    ep.apply_to(save)
    ctx.state["dead_titles"] = maps
    by = {}
    for m in maps:
        by[f"{m.kind} {m.cls}"] = by.get(f"{m.kind} {m.cls}", 0) + 1
    return rule.result(matched=len(maps), edited=len(ep.edits),
                       extra={"by_class": by, "renamed": applied.renamed, "removed": applied.removed,
                              "references_removed": dict(applied.references_removed),
                              "table": [m.row() for m in maps]})


def r16_people(save: CK3Save, ctx, rule):
    """Plan the people the planned titles need: their holders, the holders' courtiers, and the close family of
    both (one hop, living and dead). History characters the campaign already has stay the campaign's (joined:
    the reference's references to them are redirected, nothing of the reference is written into them)."""
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference): the people come from a 1.20 save")
    t = transplant_of(save, ctx)
    holders = t.title_holders(t.carry["title"])
    rulers = set(holders.values())
    # displaced (design ruling 06:58): a reference ruler whose every title went to a campaign holder through a
    # clean R15 rename comes in landless, in the court of that campaign holder, with their own dependants
    taker: dict[int, int] = {}
    displaced_rows = []
    ref_ids = {k: i for i, k in t.title_keys().items()}
    taken: dict[int, set[int]] = {}
    for m in ctx.state.get("dead_titles", []):
        if m.cls != "clean" or m.holder is None:
            continue
        rid = ref_ids.get(m.successors[0])
        h = t.title_holders([rid]).get(rid) if rid is not None else None
        if h is not None:
            taken.setdefault(h, set()).add(rid)
            taker.setdefault(h, m.holder)
    all_held = t.title_holders(t.entries(TITLES))
    for h, rids in taken.items():
        own = {i for i, x in all_held.items() if x == h}
        if own <= rids and h not in rulers and h not in t.tr.spaces["character"].join:
            t.employer[h] = taker[h]
            displaced_rows.append({"reference_character": h, "court_of": taker[h],
                                   "titles_taken": sorted(t.title_keys()[i] for i in rids)})
    c = t.people_closure(rulers | set(t.employer))
    people = c["rulers"] | c["courtiers"] | c["family"]
    joined = {p for p in people if p in t.tr.spaces["character"].join}
    t.add("character", people, "R16")
    # Unit 5b (director, 2026-10-25): every culture template the save lacks (not only the closure's), and
    # China's system state -- the situations, which bring their sub-regions and participant groups
    t.add("culture", set(t.entries("culture_manager/cultures")), "R16")
    t.add("situation", set(t.entries("situation_manager/database")), "R16")
    dead = sum(1 for p in people - joined if t.character(p)[0] == "dead_unprunable")
    return rule.result(matched=len(people - joined),
                       extra={"titles_with_a_holder": len(holders), "rulers": len(rulers),
                              "displaced_landless": len(t.employer), "displaced": displaced_rows,
                              "courtiers": len(c["courtiers"]), "family": len(c["family"]),
                              "left_to_the_campaign": len(joined), "dead": dead})


def r17_transplant_write(save: CK3Save, ctx, rule):
    """Write the transplant plan in one pass: carried objects closed, entries rewritten with the edge policy and
    inserted at column 0, seams stitched, the coat counter raised, lookups extended."""
    t = ctx.state.get("transplant")
    if t is None:
        return _skip(rule, "nothing planned (run R14, R15 or R16 first)")
    ep = t.edits()
    ep.apply_to(save)
    rep = t.report.as_dict()
    rep["holy_sites"] = _reattach_holy_sites(save, ctx)
    return rule.result(matched=sum(t.report.inserted.values()), edited=len(ep.edits), extra=rep)


def _reattach_holy_sites(save: CK3Save, ctx) -> dict:
    """R8 copies 1.20's holy sites before the transplant exists, so a site on a barony the save did not have yet
    (Angkor, Borobudur, Samarkand, ...) loses its barony and goes inactive. Now that R17 has written the new
    baronies, give each such site its barony back by key, with the reference's is_active."""
    from .. import gamestate as gs
    pending = ctx.state.get("holy_sites_without_barony", [])
    if not pending:
        return {"reattached": 0, "still_without_barony": []}
    g = save.gamestate
    ids = {k.decode(): i for k, i in T.keyed(g, TITLES).items()}
    sites = dict(T.entries(g, "religion/holy_sites"))
    ep = gs.EditPass()
    done, missing = [], []
    for s in pending:
        e, bid = sites.get(int(s["index"])), ids.get(s["barony"] or "")
        if e is None or bid is None:
            missing.append(s["barony"])
            continue
        kids = list(gs.iter_children(g, e.open + 1, e.close))
        if any(c.key == b"barony" for c in kids):
            continue
        act = next((c for c in kids if c.key == b"is_active" and c.block is None), None)
        if act is not None and s["is_active"]:
            ep.add(gs.Edit(act.value_start, act.value_end, s["is_active"].encode(), "R17", "holy site is_active"))
        at = g.rfind(b"\n", 0, e.close) + 1
        indent = re.match(rb"[\t ]*", g[at:]).group() or b"\t\t"
        ep.add(gs.Edit(at, at, indent + b"\t" + f"barony={bid}\n".encode(), "R17", "holy site barony"))
        done.append(s["barony"])
    ep.apply_to(save)
    return {"reattached": len(done), "still_without_barony": sorted(x for x in missing if x)}


from . import Rule  # noqa: E402  (Rule is defined before this module is imported)

RULES = [
    Rule("R14", "new-titles", "1.13 to 1.20 (map rework: East Asia, Tibet, ...)",
         "plan the titles and provinces the save does not have, from a 1.20 reference save", r14_new_titles,
         default=False),
    Rule("R15", "dead-titles", "1.13 to 1.20 (titles the map rework removed or moved)",
         "rename the save's dead and moved titles to their 1.20 successors where the mapping is clean; remove "
         "the rest (split, wasteland, dropped), reported", r15_dead_titles, default=False),
    Rule("R16", "people", "1.13 to 1.20 (the new regions' rulers, courts and families)",
         "plan the holders of the planned titles, their courts and close family, from a 1.20 reference save",
         r16_people, default=False),
    Rule("R17", "transplant-write", "1.20",
         "write everything R14-R16 planned, ids translated, references outside the output dropped, seams "
         "stitched", r17_transplant_write, default=False),
]
