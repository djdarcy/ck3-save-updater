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

from pathlib import Path

from ..savefile import CK3Save, read_save


def _same_date(save: CK3Save, ctx) -> str | None:
    """None when the witness may be used; otherwise the reason it may not."""
    from ..plan import meta_date
    if ctx.witness is None:
        return "needs --witness (your last save from before 1.21)"
    w, s = meta_date(read_save(ctx.witness).meta), meta_date(save.meta)
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
    r = carry_wonders(save.gamestate, load(str(ctx.game_dir)), witness=read_save(ctx.witness).gamestate)
    if r.carried:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.carried) + len(r.unmapped) + len(r.skipped), edited=len(r.carried),
                       extra={"carried": len(r.carried), "unmapped": sorted({b for _, b, _ in r.unmapped}),
                              "refused": sorted({b for _, b, _ in r.skipped})})


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
    r = carry_baronies(save.gamestate, read_save(ctx.witness).gamestate, barony_counties(ctx.game_dir),
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
    ref = ctx.state.get("reference_gamestate") or read_save(ctx.reference).gamestate
    r = type_titles(save.gamestate, ref)
    if r.typed:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.typed) + len(r.unknown), edited=len(r.typed),
                       extra={"typed": dict(__import__("collections").Counter(t for _, t, _ in r.typed)),
                              "left empty": len(r.unknown)})


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


def r36_roads(save: CK3Save, ctx, rule):
    """The 1.21 reference's roads, into a converted save that has none (the game's conversion makes none)."""
    from .to_1_21 import r34_roads
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    return r34_roads(save, ctx, rule)
