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
# R10/R9/R12 (they read the transplanted databases), R23 after them (the same family: per-character fields 1.20
# added), the transplant after religion (its translation joins faiths and rites by identity, which R8
# established) and written by R17, the faces (R19) after it so the transplanted people are in the output, the
# successor keys (R25) and the cultures' spread markers (R26) after everything that writes, the version bump last. The shipped pack's pack.toml gives this
# order; building the registry checks it.
_ORDER = ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9", "R12", "R23", "R15", "R14", "R16", "R17", "R19", "R25", "R26", "R27", "R28", "R29", "R30", "R7"]
REGISTRY: list[Rule] = rules_from_pack()
if [r.id for r in REGISTRY] != _ORDER:
    raise ImportError(f"the shipped pack's order {[r.id for r in REGISTRY]} is not the registry order {_ORDER}")
# the transplant's planning rules; choosing any of them brings the write step along
_TRANSPLANT_PLANNERS = {"R14", "R15", "R16"}


def select(spec: str | None, *, include_off: tuple[str, ...] = ()) -> list[Rule]:
    """``"all"`` -> every default rule; ``"R1,title-names"`` -> those, in registry order; ``"all,R14,R16"`` -> the
    defaults plus those (the documented way to add the transplant). ``include_off`` adds ids or names as well.
    ``None`` selects nothing (the CLI turns a missing --rules into ``"all"``); an empty string is refused.

    A token starting with ``-`` leaves that rule out: ``"all,-R21"``, or ``"-R21"`` alone, meaning all but R21. It
    applies after everything else (``all``, the names, ``include_off``, and the CLI's disabled list); a rule both
    named and left out, or left out while a selected rule requires it, is refused, naming both."""
    if spec is not None and not spec.strip():
        raise ValueError("an empty rule selection is refused; give --rules all, or a comma list of rules")
    tokens = [t.strip() for t in (spec or "").split(",") if t.strip()]
    plus = [t for t in tokens if not t.startswith("-")]
    minus = [t[1:].strip() for t in tokens if t.startswith("-")]
    if minus and not plus:
        plus = ["all"]                                  # "-R21" alone: all but R21
    chosen = set()
    named = set()
    for tok in plus:
        if tok.lower() == "all":
            chosen |= {r.id for r in REGISTRY if r.default}
            continue
        rule = _find(tok)
        chosen.add(rule.id)
        named.add(rule.id)
    for tok in include_off:
        rule = next((r for r in REGISTRY if tok.lower() in (r.id.lower(), r.name.lower())), None)
        if rule is not None:
            chosen.add(rule.id)
    out = {_find(tok, "-").id for tok in minus}
    both = sorted(named & out, key=_ORDER.index)
    if both:
        raise ValueError(f"rule {both[0]} is both named and left out (-{both[0]}) in --rules; keep one")
    chosen -= out
    if chosen & _TRANSPLANT_PLANNERS:
        if "R17" in out:
            planner = min(chosen & _TRANSPLANT_PLANNERS, key=_ORDER.index)
            raise ValueError(f"--rules leaves out R17 (transplant-write), which {planner} needs: the transplant's "
                             "planning rules bring their write step; keep R17 or leave the planners out too")
        chosen.add("R17")
    for r in REGISTRY:
        lost = [p for p in r.requires if p in out]
        if r.id in chosen and lost:
            raise ValueError(f"--rules leaves out {lost[0]}, which {r.id} ({r.name}) requires; leave {r.id} out "
                             f"too (-{r.id}), or keep {lost[0]}")
    return [r for r in REGISTRY if r.id in chosen]


def _find(tok: str, prefix: str = "") -> Rule:
    """The registered rule ``tok`` names (its id or its name, any case); unknown ones are refused, listing the
    known ids."""
    rule = next((r for r in REGISTRY if tok.lower() in (r.id.lower(), r.name.lower())), None)
    if rule is None:
        raise ValueError(f"unknown rule {prefix + tok!r}; known: all, "
                         f"{', '.join(f'{r.id}={r.name}' for r in REGISTRY)}")
    return rule


def missing_prerequisites(rules: list[Rule]) -> list[tuple[str, list[str]]]:
    """(rule id, the prerequisites it lacks) for every selected rule whose ``requires`` the selection misses."""
    have = {r.id for r in rules}
    return [(r.id, [p for p in r.requires if p not in have]) for r in rules if any(p not in have for p in r.requires)]


def run_rules(save: CK3Save, rules: list[Rule], ctx: RuleContext | None = None) -> list[RuleResult]:
    """Apply ``rules`` in order; each sees the gamestate the previous one left."""
    ctx = ctx or RuleContext()
    return [r.run(save, ctx) for r in rules]
