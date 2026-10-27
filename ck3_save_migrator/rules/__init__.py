"""Migration rules: named, versioned edits applied to a save in order.

A rule takes a ``CK3Save`` and a ``RuleContext``, edits the gamestate through an
``EditPass`` (so everything it does not touch stays byte-identical) and returns a
``RuleResult`` with counts -- the measurement loop runs on those counts.

``since`` records the game version whose loader made the rule necessary. Where
the exact major is not known yet it is a range, ``"1.8.1<v<=1.20.1.2"``: absent
from 1.8.1's format, required (or rejected) by 1.20.1.2's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..savefile import CK3Save


@dataclass
class RuleContext:
    game_dir: Path | None = None            # <steam>/common/Crusader Kings III/game, for rules that read game data
    target_version: str = "1.20.1.2"
    target_save_game_version: int = 18
    portraits_version: int | None = None    # R7 sets it only when given
    reference: Path | None = None           # a save written by the target game version (R8-R12 copy from it)
    wos_shape: str = "faith"                # R10: custom faiths become a 'faith' or a 'rite'
    old_game_dir: Path | None = None        # R15: the save's own version's 'game' folder (its map, for successors)
    expansion_orders: bool = True           # R14: add the target's new holy orders even where they lease the
                                            # save's own land (expansion content the engine does not add itself)
    state: dict = field(default_factory=dict)  # facts one rule leaves for a later one (R8 -> R9/R10/R12)


@dataclass
class RuleResult:
    id: str
    name: str
    since: str
    description: str
    matched: int = 0
    edited: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "since": self.since, "description": self.description,
                "matched": self.matched, "edited": self.edited, **({"extra": self.extra} if self.extra else {})}


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    since: str
    description: str
    apply: Callable[[CK3Save, RuleContext, "Rule"], RuleResult]
    default: bool = True                   # included in --rules all
    # the rules whose ctx.state this one reads, and R8 for a rule that writes a faith or rite id (director
    # 2026-10-26 00:45, S1): a selection without them is refused before any work
    requires: tuple[str, ...] = ()

    def result(self, **kw) -> RuleResult:
        return RuleResult(self.id, self.name, self.since, self.description, **kw)

    def run(self, save: CK3Save, ctx: RuleContext) -> RuleResult:
        return self.apply(save, ctx, self)


from .to_1_20 import RULES as _TO_1_20  # noqa: E402
from .religion_1_20 import RULES as _RELIGION  # noqa: E402
from .transplant_1_20 import RULES as _TRANSPLANT  # noqa: E402

# Registry order is execution order: R11 before R8 (it reads the old layout), R8 before
# R10/R9/R12 (they read the transplanted databases), the transplant after religion (its translation joins
# faiths and rites by identity, which R8 established) and written by R17, the version bump last.
_ORDER = ["R1", "R2", "R3", "R4", "R5", "R21", "R20", "R22", "R6", "R11", "R8", "R10", "R9", "R12", "R15", "R14", "R16", "R17", "R7"]
_BY_ID = {r.id: r for r in list(_TO_1_20) + list(_RELIGION) + list(_TRANSPLANT)}
REGISTRY: list[Rule] = [_BY_ID[i] for i in _ORDER]
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
