"""The rules of the repair_1_21 pack: phase two, repairs on a save the game already converted to 1.21.

For a player who loaded an old save in 1.21 and saved before running the tool (the Director, 2026-11-18, correction 5):
the game's conversion dropped the wonders and made no roads. The player's last 1.20 save is the witness. Measured by a
loop game run (2026-11-18__02-54-25__s6-phase2-resave): djdarcy's 1.21 re-save of v17, with 134 wonders from v17 and
the reference's 4,201 roads written in, came through the game's next save with all of them.

Both rules run only with ``--witness`` and only when the witness has the save's own game date (correction 1): a 1.21
save played on since would have what happened in between overwritten.
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
    66 one-barony vassals it stripped in djdarcy's re-save of v17). Measured by a loop game run
    (2026-11-18__12-18-28__s6-baronies4-resave): 60 of the 63 came through the game's next save with their holder,
    contract and government; the game gave the other 3 (b_avignon, b_vienne, b_jiuyuan) to someone else, cause unread.
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


def r36_roads(save: CK3Save, ctx, rule):
    """The 1.21 reference's roads, into a converted save that has none (the game's conversion makes none)."""
    from .to_1_21 import r34_roads
    why = _same_date(save, ctx)
    if why:
        return rule.result(extra={"skipped": why})
    return r34_roads(save, ctx, rule)
