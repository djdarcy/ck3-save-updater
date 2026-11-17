"""Roads for a save that came into 1.21 without them (patch day, the goal's S7; the Director's ruling 2026-11-17, class 2).

Measured on 1.21.0 (2026-11-17): a fresh game's ``roads={ database={ ... } }`` holds one record per road, ``type`` (a
road defined in common/roads/road_types: a named road over a list of provinces), ``tier``, ``upgrade_start_date``,
``decay_start_date`` and, for some, the ``trade_routes`` that use it. The game's own conversion of a 1.20 save leaves
the database empty and does not fill it on load. Roads are static history (the reference's 4,201 records: 4,076 at
tier 0, 125 at tier 1), so they come from the reference whole (the Director, ~17:50: "class 2's transplant of roads is
safe whole").

What is carried: every reference road whose type the target game defines, with its tier and dates. What is not:
- the ``trade_routes`` links. Routes have character owners and are left to the game (the goal's Out list), so a link
  would point at a route the target does not have;
- a road whose type the target game does not define (named by key in the result);
- anything at all when the target already holds roads: those are the game's or the player's, never replaced.

Not wired into a pack yet: who converts a save to 1.21 (the goal's S3) decides where this runs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import gamestate as gs

# a road's key may hold hyphens and other punctuation (al-...), so a key runs to whitespace, '=', a brace or '#'
_KEY = rb"([^\s={}#\"]+)"
_TOP_KEY = re.compile(rb"(?m)^" + _KEY + rb"\s*=\s*\{")
_TYPE = re.compile(rb"\btype=\"?" + _KEY)
_ROUTES = re.compile(rb"\n?[ \t]*trade_routes=\{[^{}]*\}")


@dataclass
class RoadsResult:
    gamestate: bytes
    carried: int = 0
    skipped_undefined: list[str] = field(default_factory=list)
    links_dropped: int = 0
    why_not: str | None = None          # set when nothing was written, with the reason


def defined_road_types(game_dir: Path) -> set[str]:
    """The road keys the game defines (common/roads/road_types/*.txt, top-level blocks)."""
    out: set[str] = set()
    for f in sorted((Path(game_dir) / "common" / "roads" / "road_types").rglob("*.txt")):
        text = re.sub(rb"#[^\n]*", b"", f.read_bytes().removeprefix(b"\xef\xbb\xbf"))   # the BOM hid the first key
        out |= {m.group(1).decode() for m in _TOP_KEY.finditer(text)}
    return out


def _entries(g: bytes) -> list[gs.Block]:
    try:
        b = gs.locate(g, "roads/database")
    except gs.GamestateError:
        return []
    return [e for e in gs.iter_entries(g, *b.body) if e.key is not None and e.key.isdigit()]


def transplant_roads(target: bytes, reference: bytes, defined: set[str] | None = None) -> RoadsResult:
    """``target`` with the reference's roads in its empty ``roads/database``. ``defined``: the road types the target
    game defines; a reference road of another type is skipped and named. Nothing is written (``why_not`` says why)
    when the target has no roads database (not a 1.21 save), already holds roads, or the reference has none."""
    try:
        tb = gs.locate(target, "roads/database")
    except gs.GamestateError:
        return RoadsResult(target, why_not="the save has no roads database (it is not a 1.21 save)")
    if _entries(target):
        return RoadsResult(target, why_not="the save already holds roads; they are kept as they are")
    ref = _entries(reference)
    if not ref:
        return RoadsResult(target, why_not="the reference holds no roads")
    out, skipped, dropped = [], [], 0
    for e in ref:
        body = reference[e.open + 1:e.close]
        t = _TYPE.search(body)
        key = t.group(1).decode() if t else "?"
        if defined is not None and key not in defined:
            skipped.append(key)
            continue
        body, n = _ROUTES.subn(b"", body)
        dropped += n
        out.append(b"\t\t" + e.key + b"={" + body + b"}\n")
    start, end = tb.body
    new = target[:start] + b"\n" + b"".join(out) + b"\t" + target[end:]
    return RoadsResult(new, carried=len(out), skipped_undefined=sorted(skipped), links_dropped=dropped)
