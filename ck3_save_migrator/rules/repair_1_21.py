"""The rules of the repair_1_21 pack: phase two, repairs on a save the game already converted to 1.21.

For a player who loaded an old save in 1.21 and saved before running the tool (the Director, 2026-11-18, correction 5):
the game's conversion dropped the wonders and made no roads. The player's last 1.20 save is the witness. Measured by a
loop game run (2026-11-18__02-54-25__s6-phase2-resave): djdarcy's 1.21 re-save of v17, with 134 wonders from v17 and
the reference's 4,201 roads written in, came through the game's next save with all of them.

The witness rules (R35-R37) run only with ``--witness`` and only when the witness has the save's own game date
(correction 1): a 1.21 save played on since would have what happened in between overwritten. R38 needs no witness:
it reads only the save and the 1.21 reference, and fills only what the conversion left empty.
"""
from __future__ import annotations

import collections
import re
from pathlib import Path

from ..savefile import CK3Save, read_save


def _witness(ctx) -> CK3Save:
    """The witness save, read once per run (R35 and R37 read it, and the date guard reads its meta: five reads of a
    200 MB save before this cache; refactor-advisor's row 1, the F7 audit)."""
    if "witness_save" not in ctx.state:
        ctx.state["witness_save"] = read_save(ctx.witness)
    return ctx.state["witness_save"]


def _same_date(save: CK3Save, ctx) -> str | None:
    """None when the witness may be used; otherwise the reason it may not."""
    from ..plan import meta_date
    if ctx.witness is None:
        return "needs --witness (your last save from before 1.21)"
    w, s = meta_date(_witness(ctx).meta), meta_date(save.meta)
    if not w or w != s:
        return (f"the witness is dated {w}, this save {s}: it was played on since, and repairs from the witness would "
                "overwrite that play")
    return None


def r35_wonders_from_witness(save: CK3Save, ctx, rule):
    """The witness's built wonders, written as 1.21 districts into a save the game converted."""
    from ..carry_1_21 import carry_wonders
    from ..host_rules import load
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    r = carry_wonders(save.gamestate, load(str(ctx.game_dir)), witness=_witness(ctx).gamestate)
    if r.carried:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.carried) + len(r.unmapped) + len(r.skipped), edited=len(r.carried),
                       extra={"carried": len(r.carried), "unmapped": sorted({b for _, b, _ in r.unmapped}),
                              "refused": sorted({b for _, b, _ in r.skipped})})


def r44_holding_tiers_from_witness(save: CK3Save, ctx, rule):
    """Each holding's main building back at the witness's tier (the conversion resets every one above tier 1)."""
    from ..carry_1_21 import carry_holding_tiers
    from ..host_rules import load
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    r = carry_holding_tiers(save.gamestate, load(str(ctx.game_dir)), _witness(ctx).gamestate)
    if r.restored:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.restored) + len(r.skipped), edited=len(r.restored),
                       extra={"restored": len(r.restored),
                              "by_tier": dict(collections.Counter(new for _, _, new in r.restored)),
                              "refused": sorted({f"{k}: {w}" for _, k, w in r.skipped})})


def r42_districts_from_witness(save: CK3Save, ctx, rule):
    """The witness's regular buildings, written into the regular districts the conversion left empty, legal by the
    game's own gates; every building not written is named (open, refused, dropped)."""
    from ..carry_1_21 import carry_districts, load_successors
    from ..district_lint import province_facts
    from ..host_rules import load
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    host = load(str(ctx.game_dir))
    g = save.gamestate
    # "raise": the district's primary goes to the level its buildings need (the recommended answer; djdarcy's choice
    # between raise and cap is pending, HOLD 2026-11-19 13:49)
    r = carry_districts(g, host, _witness(ctx).gamestate, province_facts(g, str(ctx.game_dir)), load_successors(),
                        tier_policy="raise")
    if r.written:
        save.set_gamestate(r.gamestate)
    fam = lambda k: re.sub(r"_\d+$", "", k)   # noqa: E731
    return rule.result(matched=len(r.written) + len(r.open) + len(r.refused) + len(r.dropped), edited=len(r.written),
                       extra={"districts": len(r.written), "buildings": sum(len(k) for _, _, k, _ in r.written),
                              "open": dict(collections.Counter(fam(k) for _, k, _ in r.open).most_common()),
                              "refused": dict(collections.Counter(fam(k) for _, k, _ in r.refused).most_common()),
                              "dropped": dict(collections.Counter(w for _, _, w in r.dropped).most_common())})


def r37_baronies_from_witness(save: CK3Save, ctx, rule):
    """The baronies the game's conversion took from their holders, given back from the witness.

    1.21 moved some baronies to another county, and the conversion hands each to its new county's holder (63 of the
    66 one-barony vassals it stripped in djdarcy's re-save of v17; the 61 who took them were all alive in v17, not
    new characters). Measured by loop game runs (2026-11-18__12-18-28, then 13-02-23 with holders who kept other
    land): 75 of 83 came through the game's next save with their holder (60 of 63 landless ones with contract and
    government, 15 of 20 who kept other land); the game gave 8 to someone else, cause unread. --rules -R37 leaves it out.
    """
    from ..carry_1_21 import barony_counties, carry_baronies, defined_governments
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not barony_counties(ctx.game_dir):
        return rule.result(extra={"skipped": f"no 1.21 title files at {ctx.game_dir}"})
    r = carry_baronies(save.gamestate, _witness(ctx).gamestate, barony_counties(ctx.game_dir),
                       defined_governments(ctx.game_dir))
    if r.carried:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.carried) + len(r.skipped), edited=len(r.carried),
                       extra={"carried": len(r.carried),
                              "left alone": sorted({f"{k}: {why}" for k, _, why in r.skipped})})


def r38_title_types(save: CK3Save, ctx, rule):
    """The title types the game's conversion leaves empty, from what decides them in a fresh 1.21 game (S8).

    No witness needed: the rule reads only the save and the 1.21 reference. In djdarcy's re-save of v17 the game
    wrote type="" on 2,016 titles and failed to read each back on load ("Failed to read key reference"); typed from
    the reference's rules, the game's next save kept all 1,974 and the error log lost exactly 1,974 lines (run
    2026-11-18__13-29-58__s8-types-resave). 42 no rule decides (39 unheld old mercenary companies, 3 holy orders) are
    left empty and reported.
    """
    from ..carry_1_21 import type_titles
    if ctx.reference is None:
        return rule.result(extra={"skipped": "needs a 1.21 reference save (what decides a title's type is read there)"})
    from .religion_1_20 import reference_gamestate
    ref = reference_gamestate(ctx)                  # read once per run, cached in ctx.state
    r = type_titles(save.gamestate, ref)
    if r.typed:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.typed) + len(r.unknown), edited=len(r.typed),
                       extra={"typed": dict(__import__("collections").Counter(t for _, t, _ in r.typed)),
                              "left empty": len(r.unknown)})


def r45_duchy_capitals_from_witness(save: CK3Save, ctx, rule):
    """The witness's duchy-capital buildings, written into 1.21 duchy-capital districts (goal 2026-11-19__22-43-27, S3).

    The game's conversion of djdarcy's 1.20 campaign dropped all 9 of its duchy-capital buildings; 1.21 keeps 16 of
    1.20's 17 families under the same key, in districts a province may hold where its barony is the duchy's capital
    barony and the county's holder holds the duchy. Written only where every gate the save answers holds (the district
    enabled, its own building and the old one legal); the rest are named. On the founding campaign: 7 written, the 2 tax
    assessors named (1.21 has no tax assessor). --rules -R45 leaves it out.
    """
    from ..carry_1_21 import carry_duchy_capitals
    from ..district_lint import province_facts, stage_two_facts
    from ..host_rules import load
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    g = save.gamestate
    facts = stage_two_facts(g, str(ctx.game_dir), province_facts(g, str(ctx.game_dir)))
    r = carry_duchy_capitals(g, load(str(ctx.game_dir)), _witness(ctx).gamestate, facts)
    if r.written:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.written) + len(r.named), edited=len(r.written),
                       extra={"written": [f"{p} {k} -> {d}" for p, k, d, _, _ in r.written],
                              "named": [f"{p} {k}: {w}" for p, k, w in r.named]})


def r46_resource_districts_from_witness(save: CK3Save, ctx, rule):
    """The witness's resource-type buildings (quarries, logging camps, orchards, elephant pens) carried into the
    province's 1.21 resource slot (goal 2026-11-19__22-43-27, S5): an empty slot gets the district, the same district
    is raised, another district asks the player (--auto resources=k|m|r; default m: the game's minor building inside
    it). On the founding campaign with the defaults: 426 districts, 21 raised, 161 minor buildings, none replaced.
    --rules -R46 leaves it out.
    """
    from ..carry_1_21 import carry_resource_districts
    from ..choices import Asker
    from ..district_lint import province_facts, stage_two_facts
    from ..host_rules import load
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    g = save.gamestate
    facts = stage_two_facts(g, str(ctx.game_dir), province_facts(g, str(ctx.game_dir)))
    r = carry_resource_districts(g, load(str(ctx.game_dir)), _witness(ctx).gamestate, facts,
                                 ctx.state.get("asker") or Asker())
    if r.written or r.raised or r.minor or r.replaced:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.written) + len(r.raised) + len(r.minor) + len(r.replaced) + len(r.named),
                       edited=len(r.written) + len(r.raised) + len(r.minor) + len(r.replaced),
                       extra={"districts": len(r.written), "raised": len(r.raised), "minor": len(r.minor),
                              "replaced": len(r.replaced),
                              "named": dict(collections.Counter(w[:60] for _, _, w in r.named).most_common())})


def r47_missing_innovations(save: CK3Save, ctx, rule):
    """The innovations new in 1.21 that the game's conversion never gives a culture (goal 2026-11-19__22-43-27, S1).

    No witness needed: the rule reads the save, the 1.21 reference and the game's innovation eras. The game's
    conversion of djdarcy's 1.20 campaign left 18 of 1.21's 131 innovations (prospecting, coppicing, heavy plow,
    monasticism, ...) off all 284 cultures, and two years of play added none. Each is written undiscovered, except
    where the fresh game's culture of the same template starts with it and this culture has reached its era (12 on
    the founding campaign). Leave it out with ``--rules -R47`` or ``disable R47``.
    """
    from ..carry_1_21 import innovation_eras, insert_missing_innovations
    if ctx.reference is None:
        return rule.result(extra={"skipped": "needs a 1.21 reference save (which innovations a culture lists is read there)"})
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "culture" / "innovations").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    from .religion_1_20 import reference_gamestate
    r = insert_missing_innovations(save.gamestate, reference_gamestate(ctx), innovation_eras(ctx.game_dir))
    if r.cultures:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.missing), edited=r.cultures,
                       extra={"innovations added": r.missing, "cultures": r.cultures,
                              "discovered (the fresh game's same culture, era reached)": len(r.discovered)})


def r39_empty_cooldowns(save: CK3Save, ctx, rule):
    """The decision cooldowns the game's conversion writes with an empty key: each for a decision neither 1.20 nor 1.21
    defines, 1.8-era decisions replaced by activities and carried in old saves (S8).

    No witness or reference needed. In djdarcy's re-save of v17: 2,187, each logging "Trying to set date from an
    empty string" on every load; a cooldown for a decision that no longer exists does nothing, so it is dropped.
    """
    from ..carry_1_21 import drop_empty_cooldowns
    g, n = drop_empty_cooldowns(save.gamestate)
    if n:
        save.set_gamestate(g)
    return rule.result(matched=n, edited=n, extra={"dropped": n})


def r40_province_size(save: CK3Save, ctx, rule):
    """Province sizes the game's conversion left at the smallest, raised to a fresh 1.21 game's (S6).

    Needs the 1.21 reference (history at the campaign's date). The conversion put every province of v17 at level 1;
    the reference has 547 above it. Never lowers a size.
    """
    from ..carry_1_21 import carry_province_size
    if ctx.reference is None:
        return rule.result(extra={"skipped": "needs a 1.21 reference save (the sizes come from it)"})
    from .religion_1_20 import reference_gamestate
    ref = reference_gamestate(ctx)                  # read once per run, cached in ctx.state
    g, raised = carry_province_size(save.gamestate, ref)
    if raised:
        save.set_gamestate(g)
    return rule.result(matched=len(raised), edited=len(raised),
                       extra={"raised": len(raised), "to levels": dict(sorted(
                           __import__("collections").Counter(n for _, _, n in raised).items()))})


def r36_roads(save: CK3Save, ctx, rule):
    """The 1.21 reference's roads, into a converted save that has none (the game's conversion makes none)."""
    from .to_1_21 import r34_roads
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    return r34_roads(save, ctx, rule)
