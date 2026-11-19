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


def r41_districts(save: CK3Save, ctx, rule):
    """The save's own regular buildings, written as 1.21 regular districts before the game converts it (phase one of
    the built-state carry; the same rule body as R42, which works from the witness after the conversion)."""
    import collections
    import re
    from ..carry_1_21 import carry_districts, load_successors
    from ..district_lint import Facts, province_facts
    from ..host_rules import load
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common" / "districts").is_dir():
        return rule.result(extra={"skipped": f"no 1.21 game data at {ctx.game_dir}"})
    host = load(str(ctx.game_dir))
    g = save.gamestate
    # a 1.20 save has no province sizes yet; the conversion sets every province to size 1, two regular slots (R40
    # raises sizes after the load, in phase two)
    # and its county capitals are 1.21's (the map moved some: province 3204 lost its capital, and its walls with it)
    facts = {k: Facts(v.place, 1) for k, v in province_facts(g, str(ctx.game_dir), capitals="game").items()}
    r = carry_districts(g, host, g, facts, load_successors(), tier_policy="raise", insert=True)
    if r.written:
        save.set_gamestate(r.gamestate)
    # the route from an old save fed a 1.21 reference: provinces the transplant copied keep the reference's own
    # districts, which the down-shaper stripped (R41 on the K7 route; 3,814 holdings on v17's chain)
    from ..carry_1_21 import carry_reference_districts
    t = ctx.state.get("transplant")
    down = getattr(t, "down", None)
    copied = []
    if down is not None and getattr(down, "copied", None):
        g = save.gamestate
        rc = carry_reference_districts(g, getattr(down, "ref", None) or t.ref, host, facts, down.copied)
        copied = rc.written
        if rc.written:
            save.set_gamestate(rc.gamestate)
        r.refused.extend(rc.refused)
        r.dropped.extend(rc.dropped)
    fam = lambda k: re.sub(r"_\d+$", "", k)   # noqa: E731
    return rule.result(matched=len(r.written) + len(copied) + len(r.open) + len(r.refused) + len(r.dropped),
                       edited=len(r.written) + len(copied),
                       extra={"districts": len(r.written), "buildings": sum(len(k) for _, _, k, _ in r.written),
                              "copied_provinces_districts": len(copied),
                              "open": dict(collections.Counter(fam(k) for _, k, _ in r.open).most_common()),
                              "refused": dict(collections.Counter(fam(k) for _, k, _ in r.refused).most_common()),
                              "dropped": dict(collections.Counter(w for _, _, w in r.dropped).most_common())})


def r34_roads(save: CK3Save, ctx, rule):
    """The 1.21 reference's roads, into a save that has none (a 1.20 save gets an empty roads database first)."""
    from ..roads import defined_road_types, transplant_roads
    if ctx.reference is None:
        return rule.result(extra={"skipped": "needs a 1.21 reference save (the roads come from it)"})
    if ctx.game_dir is None:
        return rule.result(extra={"skipped": "needs the game folder (the road types it defines)"})
    from .religion_1_20 import reference_gamestate
    ref = reference_gamestate(ctx)                  # read once per run, cached in ctx.state
    g = save.gamestate
    if b"\nroads={" not in g and not g.startswith(b"roads={"):
        g = g + _EMPTY_ROADS
    r = transplant_roads(g, ref, defined_road_types(Path(ctx.game_dir)))
    if r.why_not is not None:
        return rule.result(extra={"skipped": r.why_not})
    save.set_gamestate(r.gamestate)
    return rule.result(matched=r.carried + len(r.skipped_undefined), edited=r.carried,
                       extra={"carried": r.carried, "undefined": r.skipped_undefined, "route_links_dropped": r.links_dropped})
