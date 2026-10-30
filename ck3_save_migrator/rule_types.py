"""The types a migration rule is made of: ``Rule``, ``RuleContext`` and ``RuleResult``.

They live outside the ``rules`` package so that the patch engine (``patches``), which builds ``Rule`` objects, and
the rules package, whose ``REGISTRY`` is built by the patch engine from the shipped pack, can each import them
without importing the other first. ``ck3_save_migrator.rules`` re-exports all three; import them from there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .savefile import CK3Save


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
    # the installed folders of the mods the save lists, in its order (R23 reads their localization; a later one wins)
    mod_dirs: list[Path] = field(default_factory=list)
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
