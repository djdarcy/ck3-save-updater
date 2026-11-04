"""R19 dna-layout: every face carried into the target's gene layout (see ``ck3_save_migrator/dna.py``).

The layouts come from the run's setup (``ctx.state["dna_setup"]``, which update and migrate build from the save,
the game folder, ``--old-game-dir``, the reference and ``--portrait-mods`` / ``dlc_load.json``); without one the
rule builds it from the context the same way. A character the transplant added (R17's
``ctx.state["transplanted_characters"]``) is read in the reference save's layout, never guessed by length.
"""

from __future__ import annotations

from .. import dna as D
from ..savefile import CK3Save


def setup_for(save: CK3Save, ctx) -> D.Setup:
    st = ctx.state.get("dna_setup")
    if st is not None:
        return st
    ref_meta = None
    if ctx.reference is not None:
        from ..plan import read_light
        ref_meta = read_light(ctx.reference).meta
    from ..discover import game_version
    st = D.setup(save_meta=save.meta, game_dir=ctx.game_dir, old_game_dir=ctx.old_game_dir, reference_meta=ref_meta,
                 portrait_mods_given=ctx.state.get("portrait_mods"),
                 old_portrait_mods=ctx.state.get("old_portrait_mods"),
                 target_version=game_version(ctx.game_dir) if ctx.game_dir else ctx.target_version)
    st.face_changes = tuple(ctx.state.get("face_changes") or ())   # --face-changes (none by default: 0.4.0's R19)
    ctx.state["dna_setup"] = st
    return st


def r19_dna_layout(save: CK3Save, ctx, rule):
    """Rewrite every dna= string from its source layout (the save's, or the reference's for a character the
    transplant added) to the target's, by gene and template name, and set portraits_version to the target's."""
    if ctx.game_dir is None:
        return rule.result(extra={"skipped": "no game folder: the target layout is unknown"})
    st = setup_for(save, ctx)
    empty = [x.name for x in (st.source, st.target) if not x.places]
    if empty:                   # a layout with no genes would empty every face: never translate into or out of one
        return rule.result(extra={"skipped": f"no genes found for {' and '.join(empty)} layout (no common/genes in "
                                             "its folders): the faces are left as they are",
                                  "layouts": st.describe()})
    res = D.plan_save(save.gamestate, st, ctx.state.get("transplanted_characters"))
    if res.edits:
        save.set_gamestate(D.apply_edits(save.gamestate, res.edits))
    own, ref = st.plans()
    faces = sum(len(v) for v in res.outcomes.values())
    return rule.result(matched=faces + sum(res.other.values()), edited=len(res.edits), extra={
        "outcomes": {k: sorted(v, key=int) for k, v in sorted(res.outcomes.items())},
        "outcome_counts": {k: len(v) for k, v in sorted(res.outcomes.items())},
        "other_dna": dict(res.other),
        "plans": [own.counts()] + ([ref.counts()] if ref is not None else []),
        "layouts": st.describe(),
        "length_mismatches": {"longer, tail dropped": [{"layout": n, "places_dropped": k, "faces": c}
                                                       for (n, k), c in sorted(res.dropped_places.items())],
                              "shorter, left as is": len(res.outcomes.get("left as is: shorter than its layout", []))},
        "dna_lengths_in": dict(res.lengths),
        # a template index the source gene does not define: the source layout is probably not the save's
        "template_indexes_the_source_layout_does_not_define": {"count": sum(res.impossible.values()),
                                                                "by_gene": dict(res.impossible_by_gene())},
        "portraits_version": ({"from": res.portraits_version[0], "to": res.portraits_version[1]}
                              if res.portraits_version else {"to": st.portraits_version, "changed": False}),
    })


from . import Rule  # noqa: E402  (circular-safe: Rule is defined before this module is imported)

RULES = [
    Rule("R19", "dna-layout", "1.8.1<v<=1.20.1.2",
         "carry every face (dna=) into the target's gene layout, by gene and template name, and stamp its "
         "portraits_version", r19_dna_layout),
]
