"""The rules of the to_1_21 pack: decision C's pre-load pass (patch day, OPEN-QUESTIONS Q261117-04).

The save stays stamped 1.20, so the player's first load in 1.21 converts it. Before that load, these rules write what
the game's own conversion would lose and keep when it is already there. The loop measured both on 2026-11-17 by
loading the results in 1.21.0 and saving (private/data/runs/2026-11-17__19-50-08__s6-wonders-resave and
…19-55-56__s7-roads120-resave):
- R33 the wonders (carry_1_21.carry_wonders): 133 of 134 kept by the conversion, each in its slot with its building;
- R34 the roads (roads.transplant_roads from the 1.21 reference): 4,201 of 4,201 kept, tiers intact.
"""
from __future__ import annotations

from pathlib import Path

from ..savefile import CK3Save, read_save

_EMPTY_ROADS = b"roads={\n\tdatabase={\n\t}\n}\n"


def r33_wonders(save: CK3Save, ctx, rule):
    """Each holding's built wonder, great work and duchy-capital building, written as its 1.21 district."""
    from ..carry_1_21 import carry_wonders
    from ..host_rules import load
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    r = carry_wonders(save.gamestate, load(str(ctx.game_dir)))
    if r.carried:
        save.set_gamestate(r.gamestate)
    return rule.result(matched=len(r.carried) + len(r.unmapped) + len(r.skipped), edited=len(r.carried),
                       extra={"carried": len(r.carried),
                              "unmapped": sorted({b for _, b, _ in r.unmapped}),
                              "refused": sorted({b for _, b, _ in r.skipped})})


def r34_roads(save: CK3Save, ctx, rule):
    """The 1.21 reference's roads, into a save that has none (a 1.20 save gets an empty roads database first)."""
    from ..roads import defined_road_types, transplant_roads
    if ctx.reference is None:
        return rule.result(extra={"skipped": "needs a 1.21 reference save (the roads come from it)"})
    if ctx.game_dir is None:
        return rule.result(extra={"skipped": "needs the game folder (the road types it defines)"})
    ref = ctx.state.get("reference_gamestate") or read_save(ctx.reference).gamestate
    g = save.gamestate
    if b"\nroads={" not in g and not g.startswith(b"roads={"):
        g = g + _EMPTY_ROADS
    r = transplant_roads(g, ref, defined_road_types(Path(ctx.game_dir)))
    if r.why_not is not None:
        return rule.result(extra={"skipped": r.why_not})
    save.set_gamestate(r.gamestate)
    return rule.result(matched=r.carried + len(r.skipped_undefined), edited=r.carried,
                       extra={"carried": r.carried, "undefined": r.skipped_undefined, "route_links_dropped": r.links_dropped})
