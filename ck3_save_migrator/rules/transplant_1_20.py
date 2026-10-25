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
    save_provinces = {i for i, _ in T.entries(save.gamestate, "provinces")}
    provinces = set(t.entries("provinces")) - save_provinces
    t.add("title", new, "R14")
    t.add("province", provinces, "R14")
    tiers = {}
    for i in new:
        tiers[ref_keys[i][0]] = tiers.get(ref_keys[i][0], 0) + 1
    return rule.result(matched=len(new) + len(provinces),
                       extra={"titles_planned": len(new), "by_tier": dict(sorted(tiers.items())),
                              "provinces_planned": len(provinces),
                              "x_titles_left_out": sum(1 for k in ref_keys.values() if k.startswith("x_"))})


def r16_people(save: CK3Save, ctx, rule):
    """Plan the people the planned titles need: their holders, the holders' courtiers, and the close family of
    both (one hop, living and dead). History characters the campaign already has stay the campaign's (joined:
    the reference's references to them are redirected, nothing of the reference is written into them)."""
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference): the people come from a 1.20 save")
    t = transplant_of(save, ctx)
    holders = t.title_holders(t.carry["title"])
    c = t.people_closure(set(holders.values()))
    people = c["rulers"] | c["courtiers"] | c["family"]
    joined = {p for p in people if p in t.tr.spaces["character"].join}
    t.add("character", people, "R16")
    dead = sum(1 for p in people - joined if t.character(p)[0] == "dead_unprunable")
    return rule.result(matched=len(people - joined),
                       extra={"titles_with_a_holder": len(holders), "rulers": len(c["rulers"]),
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
    return rule.result(matched=sum(t.report.inserted.values()), edited=len(ep.edits), extra=rep)


from . import Rule  # noqa: E402  (Rule is defined before this module is imported)

RULES = [
    Rule("R14", "new-titles", "1.13 to 1.20 (map rework: East Asia, Tibet, ...)",
         "plan the titles and provinces the save does not have, from a 1.20 reference save", r14_new_titles,
         default=False),
    Rule("R16", "people", "1.13 to 1.20 (the new regions' rulers, courts and families)",
         "plan the holders of the planned titles, their courts and close family, from a 1.20 reference save",
         r16_people, default=False),
    Rule("R17", "transplant-write", "1.20",
         "write everything R14-R16 planned, ids translated, references outside the output dropped, seams "
         "stitched", r17_transplant_write, default=False),
]
