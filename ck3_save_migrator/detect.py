"""Detectors: whether a built-in rule is needed on a save, read only (nothing is edited).

A Python rule's need is known only by running it, so ``check`` and the plan said "unknown" for most built-in rules.
Most of them already have a lint check that sees their symptom; three (R2, R21, R23) have a ``*_detect`` beside the
rule, the rule's own matcher run without its edits. A check may name and offer the rule that fixes what it finds,
never invent one (djdarcy: lint checks as upgrade pathways).

``detect(rule_id, gamestate, env)`` gives a ``Detection``: "needed" (a count of what the rule would fix, and up to
five examples), "done" (none found), or "unknown" (no detector, or one that needs what is not at hand: the game
folder, a reference save). The declarative patches of the built-in pack (R1, R4, R5, R7, R11) are judged by the
patch engine (``patches.pack.verdict``), as ``check`` judges them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import gamestate as gs
from .rule_types import RuleContext


@dataclass
class Detection:
    state: str                         # needed | done | unknown
    count: int | None = None
    what: str = ""
    examples: list[str] = field(default_factory=list)
    why: str = ""                      # unknown: what it would need

    def line(self) -> str:
        """The plan's words: ``needed: <count> <what>``, ``done: none found``, or ``unknown: <why>``."""
        if self.state == "needed":
            return f"needed: {self.count:,} {self.what}" if self.count is not None else f"needed: {self.what}"
        if self.state == "done":
            return "done: none found"
        return f"unknown: {self.why}"


@dataclass
class Env:
    """What a detector may need besides the gamestate."""
    game_dir: Path | None = None
    reference: bytes | None = None     # a reference save's gamestate (R14, R16, R17)
    patches: dict = field(default_factory=dict)      # the built-in pack's patches, by id (the declarative ones)
    # detector -> (the gamestate object it read, its Detection): rules that share a detector (R14/R16/R17,
    # R8/R9/R10/R12, R6/R15) read the save once per plan. Kept with the object itself and reused only for that same
    # object, never by path or by content: a dry run and a real run on one file never share a verdict.
    memo: dict = field(default_factory=dict, repr=False, compare=False)


def _found(n: int, examples: list[str], what: str) -> Detection:
    return Detection("needed", n, what, examples[:5]) if n else Detection("done")


def _lint_finding(g: bytes, check, name: str, *args) -> tuple[int, list[str]]:
    """Run one lint check into a fresh report; the count and examples of the finding called ``name``."""
    from .lint import LintReport, SectionIndex
    rep = LintReport()
    check(g, rep, *args, SectionIndex(g)) if args else check(g, rep, SectionIndex(g))
    f = next((f for f in rep.findings if f.check == name), None)
    return (f.count, f.examples) if f else (0, [])


# --------------------------------------------------------------------------- one detector per rule
def _r2(g, env):
    from .rules.to_1_20 import r2_detect
    return _found(*r2_detect(g), "scripted-relation flag bitsets wider than 1.20's 1 byte")


def _r21(g, env):
    from .rules.to_1_20 import r21_detect
    return _found(*r21_detect(g), "dead characters whose recorded liege chain loops")


def _r23(g, env):
    from .rules.to_1_20 import r23_detect
    return _found(*r23_detect(g), "nicknames without text")


def _r3(g, env):
    from .lint import inline_title_names
    hits = inline_title_names(g)
    return _found(len(hits), hits, "titles with inline names and no title_name_data")


def _r20(g, env):
    from .lint import check_ai
    return _found(*_lint_finding(g, check_ai, "AI war coordinators have been run"), "AI war coordinators never run")


def _r22(g, env):
    if env.game_dir is None:
        return Detection("unknown", why="needs the game folder (the target map)")
    from .lint import check_units_passable
    return _found(*_lint_finding(g, check_units_passable, "nothing lives on a province the new map made impassable",
                                 Path(env.game_dir)), "things on provinces the new map made impassable")


def _dead_titles(g, env):
    lt_dir = Path(env.game_dir) / "common" / "landed_titles" if env.game_dir is not None else None
    if lt_dir is None or not lt_dir.is_dir():
        return Detection("unknown", why="needs the game's data (its common/landed_titles)")
    from .rules.to_1_20 import defined_title_keys
    defined, conv = defined_title_keys(Path(env.game_dir))
    try:
        lt = gs.locate(g, "landed_titles/landed_titles")
    except gs.GamestateError:
        return Detection("done")
    # lint's "is not a valid title template": a key the game no longer defines, nor converts itself
    dead = [k.decode() for k in re.findall(rb'(?m)^\tkey="?([\w\-\']+)"?', g[lt.open:lt.close])
            if not k.startswith(b"x_") and k.decode() not in defined and k.decode() not in conv]
    return _found(len(dead), dead, "titles the game no longer defines (\"is not a valid title template\")")


def _religion_layout(g, env):
    from .lint import SectionIndex, _db
    idx = SectionIndex(g)
    if _db(g, idx, "rites/database") and _db(g, idx, "faiths/database"):
        return Detection("done")
    return Detection("needed", None, "the save has no rites/faiths database (the 1.20 religion layout)")


def _reference_titles(g, env):
    if env.reference is None:
        return Detection("unknown", why="needs a reference save")
    from .lint import check_reference_titles
    return _found(*_lint_finding(g, check_reference_titles, "titles a fresh game has exist in the save", env.reference),
                  "titles a fresh game has that the save lacks")


DETECTORS = {
    "R2": _r2, "R3": _r3, "R21": _r21, "R20": _r20, "R22": _r22, "R6": _dead_titles, "R15": _dead_titles,
    "R8": _religion_layout, "R9": _religion_layout, "R10": _religion_layout, "R12": _religion_layout,
    "R14": _reference_titles, "R16": _reference_titles, "R17": _reference_titles, "R23": _r23,
}


def has_detector(rule_id: str, env: Env | None = None) -> bool:
    p = (env.patches if env else {}).get(rule_id)
    return rule_id in DETECTORS or (p is not None and p.kind == "declarative")


def detect(rule_id: str, g: bytes, env: Env) -> Detection:
    """The rule's detection on gamestate ``g`` (read only). A detector several rules share runs once per ``env`` for
    the same gamestate object (``Env.memo``)."""
    fn = DETECTORS.get(rule_id)
    if fn is not None:
        hit = env.memo.get(fn)
        if hit is not None and hit[0] is g:
            return hit[1]
        d = fn(g, env)
        env.memo[fn] = (g, d)
        return d
    p = env.patches.get(rule_id)
    if p is not None and p.kind == "declarative":
        from .patches.pack import verdict
        v, detail = verdict(g, p, RuleContext(game_dir=env.game_dir))
        if v == "needed":
            return Detection("needed", None, detail)
        if v == "done":
            return Detection("done")
        return Detection("unknown", why=detail)
    return Detection("unknown", why="a Python rule with no detector: only running it would tell")
