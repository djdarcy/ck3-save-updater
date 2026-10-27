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

_HOLDING = re.compile(rb"holding=\{[^}]*?type=")     # a province entry that has a holding (1.8.1 or 1.20 form)

# Reference titles the engine is measured to create by itself in a migrated campaign, so a copy would duplicate it
# ("Duplicate landed title name", 2026-10-25). Measured key by key in the game's own saves of the migrated founding
# campaign at 990.1.1 and 1003.1.1: of the 340 titles 1.20 defines that the save lacked, only this one appeared. Why
# the engine creates it is not known (not from history files, not from a holy order). Any other title a fresh game
# has is carried, empty if the fresh game has it empty (DWP 2026-10-27 05-49-04, option B; djdarcy: carry only
# what a fresh game has, as it has it).
ENGINE_CREATED = frozenset({"d_knights_hospitaller"})


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
    t.r15_kept = ctx.state.get("r15_kept", [])        # held titles R15 removed: their successors go to the holder
    save_keys = set(T.keyed(save.gamestate, TITLES))
    ref_keys = t.title_keys()
    new = {i for i, k in ref_keys.items() if k.encode() not in save_keys and not k.startswith("x_")}
    # every title a fresh 1.20 game has is carried, held or not: an unheld titular title (h_roman_empire, the
    # monastic orders, e_carthage ...) is how "not yet created, can be earned" is written, and the game's scripts
    # name them (2026-10-27: 252 of 323 named 845 times; the engine created 1 of them in 16 years of play). Only the
    # titles the engine is measured to create itself are left to it.
    engine = {i for i in new if ref_keys[i] in ENGINE_CREATED}
    held = t.title_holders(new)
    unheld_titular = {i for i in new - engine if ref_keys[i][0] in "dkeh" and i not in held
                      and not any(p.startswith("de_jure_vassals") for p, _, _ in
                                  t.references(TITLES, i, t.entries(TITLES)[i]))}
    # a holy order that leases campaign land: 1.20 does not add these to an old save by itself (two months of
    # play on the migrated save created none of the 12), so they are expansion content -- added "as is" with
    # their leases unless --no-expansion-orders, and reported either way
    join = t.tr.spaces["title"].join
    ho_campaign = {own for own, leased in t.holy_order_titles().values()
                   if own is not None and any(x in join for x in leased)}
    t.expansion_orders = ctx.expansion_orders
    new -= engine
    if not ctx.expansion_orders:
        new -= ho_campaign
    save_provinces = {i: e for i, e in T.entries(save.gamestate, "provinces")}
    provinces = set(t.entries("provinces")) - set(save_provinces)
    t.add("title", new, "R14")
    t.add("province", provinces, "R14")
    # ruling B (director 2026-10-26 13:3x): a copied barony on a province the campaign kept with NO holding gets
    # the reference's province entry (the copied holder had nothing to hold, and the engine strips him on load:
    # b_luoshan, province 8985). A campaign barony the campaign never built stays unbuilt, counted.
    unbuilt = 0
    if ctx.game_dir is not None:
        from .. import deadtitles as D
        _, prov_of = D.title_tree(ctx.game_dir / "common" / "landed_titles")
        new_baronies = {prov_of[ref_keys[i]] for i in new if ref_keys[i].startswith("b_") and ref_keys[i] in prov_of}
        refp = t.entries("provinces")
        for p, e in save_provinces.items():
            r = refp.get(p)
            if r is None or _HOLDING.search(save.gamestate[e.start:min(e.end, e.start + 1500)]) or \
                    not _HOLDING.search(t.ref[r.start:min(r.end, r.start + 1500)]):
                continue
            if p in new_baronies:
                t.fill_provinces.add(p)
            else:
                unbuilt += 1
    tiers = {}
    for i in new:
        tiers[ref_keys[i][0]] = tiers.get(ref_keys[i][0], 0) + 1
    return rule.result(matched=len(new) + len(provinces),
                       extra={"titles_planned": len(new), "by_tier": dict(sorted(tiers.items())),
                              "unheld_titular_carried": len(unheld_titular),
                              "left_to_the_engine": sorted(ref_keys[i] for i in engine),
                              "holy_order_titles_leasing_campaign_land": sorted(ref_keys[i] for i in ho_campaign),
                              "expansion_orders": "added" if ctx.expansion_orders else "left out",
                              "provinces_planned": len(provinces),
                              "provinces_given_a_holding": len(t.fill_provinces),
                              "unbuilt_in_the_campaign_built_in_a_fresh_1_20_game": unbuilt,
                              "x_titles_left_out": sum(1 for k in ref_keys.values() if k.startswith("x_"))})


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def save_version(save: CK3Save) -> tuple[int, ...] | None:
    """The game version a save says it was written by (meta_data ``version="1.8.1"``), as numbers."""
    from .. import gamestate as gs
    try:
        meta = gs.find_section(save.gamestate, "meta_data")
    except gs.GamestateError:
        return None
    for c in gs.iter_children(save.gamestate, *meta.body):
        if c.key == b"version" and c.value_start is not None:
            return _version_tuple(save.gamestate[c.value_start:c.value_end].decode("ascii", "replace")) or None
    return None


def r15_dead_titles(save: CK3Save, ctx, rule):
    """Settle the save's titles the target no longer defines, and its moved baronies, by place: a clean mapping
    renames the save's title to its successor (id and holder kept); any other is removed with every reference
    to it, and the reference's titles for that land come in through R14. Runs before R14, edits the save at
    once so the joins see the new keys, and leaves its table in ctx.state for the report."""
    from .. import deadtitles as D
    from .. import gamestate as gs
    from ..lint import defined_title_keys
    # S11 (measured 2026-10-26): the mapping comes from the two maps' files, which still differ on a save that is
    # already on the target map; re-run on the founding save's migrated output, R15 swapped b_darlington and
    # b_hartlepool back and removed 8 moved baronies. A save already at the target version is on the target map.
    have = save_version(save)
    if have is not None and have >= _version_tuple(ctx.target_version):
        return _skip(rule, f"the save is already at {'.'.join(map(str, have))} (the target map); nothing to settle")
    if ctx.old_game_dir is None or ctx.game_dir is None:
        return _skip(rule, "needs --old-game-dir (the save's own version's game folder) and --game-dir")
    _, conversion = defined_title_keys(ctx.game_dir)
    maps = D.classify(save.gamestate, ctx.old_game_dir / "common" / "landed_titles",
                      ctx.game_dir / "common" / "landed_titles", set(conversion))
    # djdarcy 2026-10-27 (~06:30): "any titles that were in play that are still existent in the game that were
    # present in our original game should be upgraded if possible so the correct holder still has their title."
    # A held title R15 removes because 1.20 split or redrew its land: its successors go to the campaign holder
    # (the transplant does it, Transplant.holdings_plan). Recorded here, before the removal, with the title's old
    # de facto liege (by key), which the removal strips.
    blocks = dict(T.entries(save.gamestate, TITLES))
    key_of = {i: (k.decode() if (k := T._depth0(save.gamestate, e, T._KEY)) else "") for i, e in blocks.items()}
    kept = []
    for m in maps:
        if m.holder is None or m.cls != "unclean" or not m.successors:
            continue
        e = blocks[m.save_id]
        df = re.search(rb"\n\tde_facto_liege=(\d+)", save.gamestate[e.open:min(e.close, e.open + 4096)])
        kept.append({"key": m.key, "holder": m.holder, "successors": list(m.successors),
                     "old_liege_key": key_of.get(int(df.group(1))) if df else None})
    ctx.state["r15_kept"] = kept
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
    # only the situation types the save lacks (S11, measured 2026-10-26: re-run on the founding save's migrated
    # output, R16 planned all 4 again, and R17 inserted them a second time with their 11 sub-regions and 55
    # groups; cultures are safe, they join by template)
    def sit_type(g, e):
        m = re.search(rb"\n\t+type=\"?(\w+)", g[e.start:min(e.end, e.start + 2000)])
        return m.group(1) if m else None
    try:
        have = {sit_type(save.gamestate, e) for _, e in T.entries(save.gamestate, "situation_manager/database")}
    except T.TranslationError:
        have = set()
    t.add("situation", {i for i, e in t.entries("situation_manager/database").items()
                        if sit_type(t.ref, e) not in have}, "R16")
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
        # S2: name only the rules that plan a write; R15 renames titles in place and plans nothing for R17
        return _skip(rule, "nothing planned: R14 (titles, provinces) and R16 (people) plan what this rule writes")
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
         default=False, requires=("R8",)),
    Rule("R15", "dead-titles", "1.13 to 1.20 (titles the map rework removed or moved)",
         "rename the save's dead and moved titles to their 1.20 successors where the mapping is clean; remove "
         "the rest (split, wasteland, dropped), reported", r15_dead_titles, default=False,
         requires=("R14", "R16")),
    Rule("R16", "people", "1.13 to 1.20 (the new regions' rulers, courts and families)",
         "plan the holders of the planned titles, their courts and close family, from a 1.20 reference save",
         r16_people, default=False, requires=("R8", "R14")),
    Rule("R17", "transplant-write", "1.20",
         "write everything R14-R16 planned, ids translated, references outside the output dropped, seams "
         "stitched", r17_transplant_write, default=False),
]
