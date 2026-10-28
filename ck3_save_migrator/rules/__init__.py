"""Migration rules: named, versioned edits applied to a save in order.

A rule takes a ``CK3Save`` and a ``RuleContext``, edits the gamestate through an
``EditPass`` (so everything it does not touch stays byte-identical) and returns a
``RuleResult`` with counts -- the measurement loop runs on those counts.

``since`` records the game version whose loader made the rule necessary. Where
the exact major is not known yet it is a range, ``"1.8.1<v<=1.20.1.2"``: absent
from 1.8.1's format, required (or rejected) by 1.20.1.2's.

``REGISTRY`` is built from the shipped pack (``ck3_save_migrator/packs/to_1_20``): R1, R4, R5, R7 and R11 are
declarative patches run by the patch engine; the others are code patches naming the functions in this package.
"""

from __future__ import annotations

from ..rule_types import Rule, RuleContext, RuleResult
from ..savefile import CK3Save
from ..patches.pack import rules_from_pack

__all__ = ["REGISTRY", "Rule", "RuleContext", "RuleResult", "missing_prerequisites", "run_rules", "select"]

# Registry order is execution order: R11 before R8 (it reads the old layout), R8 before
# R10/R9/R12 (they read the transplanted databases), the transplant after religion (its translation joins
# faiths and rites by identity, which R8 established) and written by R17, the version bump last. The shipped
# pack's pack.toml gives this order; building the registry checks it.
_ORDER = ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9", "R12", "R15", "R14", "R16", "R17", "R7"]
REGISTRY: list[Rule] = rules_from_pack()
if [r.id for r in REGISTRY] != _ORDER:
    raise ImportError(f"the shipped pack's order {[r.id for r in REGISTRY]} is not the registry order {_ORDER}")
# the transplant's planning rules; choosing any of them brings the write step along
_TRANSPLANT_PLANNERS = {"R14", "R15", "R16"}


def select(spec: str | None, *, include_off: tuple[str, ...] = ()) -> list[Rule]:
    """``"all"`` -> every default rule; ``"R1,title-names"`` -> those, in registry order; ``"all,R14,R16"`` -> the
    defaults plus those (the documented way to add the transplant). ``include_off`` adds ids or names as well.
    ``None`` selects nothing (the CLI turns a missing --rules into ``"all"``); an empty string is refused."""
    if spec is not None and not spec.strip():
        raise ValueError("an empty rule selection is refused; give --rules all, or a comma list of rules")
    chosen = set()
    for tok in (t.strip() for t in (spec or "").split(",") if t.strip()):
        if tok.lower() == "all":
            chosen |= {r.id for r in REGISTRY if r.default}
            continue
        rule = next((r for r in REGISTRY if tok.lower() in (r.id.lower(), r.name.lower())), None)
        if rule is None:
            raise ValueError(f"unknown rule {tok!r}; known: all, {', '.join(f'{r.id}={r.name}' for r in REGISTRY)}")
        chosen.add(rule.id)
    for tok in include_off:
        rule = next((r for r in REGISTRY if tok.lower() in (r.id.lower(), r.name.lower())), None)
        if rule is not None:
            chosen.add(rule.id)
    if chosen & _TRANSPLANT_PLANNERS:
        chosen.add("R17")
    return [r for r in REGISTRY if r.id in chosen]


def missing_prerequisites(rules: list[Rule]) -> list[tuple[str, list[str]]]:
    """(rule id, the prerequisites it lacks) for every selected rule whose ``requires`` the selection misses."""
    have = {r.id for r in rules}
    return [(r.id, [p for p in r.requires if p not in have]) for r in rules if any(p not in have for p in r.requires)]


def run_rules(save: CK3Save, rules: list[Rule], ctx: RuleContext | None = None) -> list[RuleResult]:
    """Apply ``rules`` in order; each sees the gamestate the previous one left."""
    ctx = ctx or RuleContext()
    return [r.run(save, ctx) for r in rules]
