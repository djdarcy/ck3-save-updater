"""Shape rows copied from a 1.21 reference into the 1.20 shape the save they enter is stamped with (goal F2).

The route to 1.21 with only the current game installed (K7, the collab's final assessment 2026-11-18__17-07-40):
to_1_20 copies what the campaign lacks from a 1.21 reference, the output stays stamped 1.20, and the game converts
it on one load. A copied row must then look like what a 1.20 reference would have given, or the 1.20 conversion meets
fields that point into databases the save does not have (the re-run held 5,569: districts 2,627, markets 2,942,
trade routes 25) and misses fields every 1.20 row has (holdings' buildings lists, county development).

Every function here takes one copied entry's text, as the transplant renders it (an ``id={ ... }`` block), and finds
fields by brace depth inside that entry, never by a pattern over the whole save: a pattern that misread a nested block
voided a game run on 2026-11-18 (a stray brace left by stripping ``nomad=`` but not its block).

The field lists are the collab's round 3 (2026-11-18__16-49-33), measured as the two references' field paths in both
directions and the re-run's copied rows against v17. The derivations:
- ``development`` = ``prosperity`` and ``development_progress`` = ``prosperity_progress``: the game's own conversion
  sets prosperity equal to development on all 3,469 counties of v17 (goal file, 2026-11-18 17:3x), so the reverse
  invents nothing.
- a holding's ``buildings`` list: its main building from the reference's ``holding_district`` (district -> its first
  building -> that building's type), its wonder slot from ``special_district_type`` / ``great_district_type`` without
  the ``_district`` suffix, and the slot count from a table of 1.20 counts (``slots``), else the type's usual count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import gamestate as gs
from .baselines import added_fields

# The top-level fields 1.21 added, from the two shipped baselines (refactor-advisor's row 5, the F7 audit): a later
# version's shape change is then a new baseline, not new literals. They equal the collab's measured lists exactly (the
# test pins that). A title's `type` sits on its key line and is handled there, not dropped as a field.
_ADDED = lambda path: added_fields(SHAPE_FROM, SHAPE_TO, path)          # noqa: E731
SHAPE_FROM, SHAPE_TO = "1.20.1.2", "1.21.0"
TITLE_FIELDS = tuple(f for f in _ADDED("landed_titles/landed_titles") if f != b"type")
PROVINCE_FIELDS = _ADDED("provinces")
DOMICILE_FIELDS = _ADDED("domiciles/database")
# nested paths the baselines do not cover (holdings inside provinces, landed_data and playable_data inside titles,
# county_manager's records): measured by hand in the collab's round 3
HOLDING_FIELDS = (b"districts", b"regular_district_slot_limit", b"holding_district")      # plus every *_district*
LANDED_FIELDS = (b"trade_routes", b"trade_competitiveness", b"law_proposal_date", b"gold_expenses")
PLAYABLE_FIELDS = (b"assembly", b"major_assembly_member")
COUNTY_FIELDS = (b"prosperity", b"prosperity_progress", b"opinion_of_liege", b"popular_opinion_level",
                 b"county_control_level")
# 1.20's usual building slots by holding type, the mode in the 1.20 reference at 987 (castle 4: 1,487+410+110 of
# 2,236; city 3; church 3; tribal 4 or 3 evenly, 4 taken; nomad 3); used only for a province the slot table lacks
USUAL_SLOTS = {b"castle_holding": 4, b"city_holding": 3, b"church_holding": 3, b"tribal_holding": 4,
               b"nomad_holding": 3}


def load_slots(version: str = "1.20.1.2") -> dict[str, int]:
    """The shipped table of 1.20 building slots per province (``known_slots/<version>.json``), or {} if absent."""
    import json
    from pathlib import Path
    p = Path(__file__).parent / "known_slots" / f"{version}.json"
    return json.loads(p.read_text(encoding="utf-8"))["slots"] if p.is_file() else {}


@dataclass
class Shaped:
    """What the down-shaper did, for the rule's report."""
    counts: dict = field(default_factory=dict)

    def add(self, what: str, n: int = 1) -> None:
        if n:
            self.counts[what] = self.counts.get(what, 0) + n


def _depth_at(text: bytes, pos: int) -> int:
    """Brace depth at ``pos`` inside an entry's text (the entry's own ``{`` makes depth 1), skipping quoted strings."""
    d = 0
    for m in gs._BRACE_OR_STRING.finditer(text, 0, pos):
        tok = m.group(0)
        if tok == b"{":
            d += 1
        elif tok == b"}":
            d -= 1
    return d


def _value_end(text: bytes, at: int) -> int:
    """End of the value that starts at ``at`` (a block, a quoted string, or a bare word)."""
    if text[at:at + 1] == b"{":
        return gs.match_brace(text, at) + 1
    if text[at:at + 1] == b'"':
        return text.index(b'"', at + 1) + 1
    m = re.compile(rb"[^\s{}]*").match(text, at)
    return m.end()


def drop_fields(text: bytes, names, depth: int, inside: bytes | None = None) -> tuple[bytes, int]:
    """``text`` without every ``name=value`` (value a word, a string or a block) at ``depth`` -- inside the block
    ``inside`` when given (found at ``depth - 1``). Returns the text and how many were dropped."""
    lo, hi = 0, len(text)
    if inside is not None:
        m = None
        for c in re.finditer(rb"[\s{]" + re.escape(inside) + rb"=\{", text):
            if _depth_at(text, c.start() + 1) == depth - 1:
                m = c
                break
        if m is None:
            return text, 0
        lo = m.end() - 1
        hi = gs.match_brace(text, lo) + 1
    pat = re.compile(rb"(\n[ \t]*|(?<=\s))(" + b"|".join(re.escape(n) for n in names) + rb")=")
    cuts = []
    for m in pat.finditer(text, lo, hi):
        if _depth_at(text, m.start(2)) != depth:
            continue
        cuts.append((m.start(1) if m.group(1).startswith(b"\n") else m.start(2), _value_end(text, m.end())))
    for s, e in reversed(cuts):
        text = text[:s] + text[e:]
    return text, len(cuts)


def title(text: bytes, out: Shaped) -> bytes:
    """A copied title: no ``type=`` on its key line, none of the 1.21-only title fields."""
    text, n = re.subn(rb"(\n[ \t]*)type=[^\s=]*\t(key=)", rb"\1\2", text, count=1)
    out.add("title type", n)
    text, n = drop_fields(text, TITLE_FIELDS, 1)
    out.add("title fields", n)
    return text


def county_record(text: bytes, out: Shaped) -> bytes:
    """A copied county record: development from prosperity (the game's own conversion maps them one to one)."""
    if re.search(rb"\bdevelopment=", text):
        return text
    p = re.search(rb"\n([ \t]*)prosperity=([\d.]+)", text)
    pp = re.search(rb"\n[ \t]*prosperity_progress=([\d.]+)", text)
    text, n = drop_fields(text, COUNTY_FIELDS, 1)
    out.add("county fields", n)
    if p:
        ind = p.group(1)
        add = b"\n" + ind + b"development=" + p.group(2)
        if pp:
            add += b"\n" + ind + b"development_progress=" + pp.group(1)
        brace = text.index(b"{")
        text = text[:brace + 1] + add + text[brace + 1:]
        out.add("county development derived")
    return text


def character(text: bytes, out: Shaped) -> bytes:
    """A copied character: none of 1.21's landed and playable fields (trade routes bear ids the save lacks)."""
    text, n = drop_fields(text, LANDED_FIELDS, 2, inside=b"landed_data")
    out.add("landed fields", n)
    text, n = drop_fields(text, PLAYABLE_FIELDS, 2, inside=b"playable_data")
    out.add("playable fields", n)
    return text


def domicile(text: bytes, out: Shaped) -> bytes:
    text, n = drop_fields(text, DOMICILE_FIELDS, 1)
    out.add("domicile fields", n)
    return text


class Provinces:
    """The holding shaper, with the reference's district and building databases read once."""

    def __init__(self, ref: bytes, slots: dict[str, int] | None = None):
        self.ref, self.slots = ref, slots or {}
        self._dist: dict[bytes, list[bytes]] | None = None
        self._btype: dict[bytes, bytes] | None = None

    def _maps(self):
        if self._dist is None:
            self._dist, self._btype = {}, {}
            for path, sink in (("districts/database", "d"), ("buildings/database", "b")):
                try:
                    blk = gs.locate(self.ref, path)
                except gs.GamestateError:
                    continue
                for e in gs.iter_entries(self.ref, *blk.body):
                    if not e.key:
                        continue
                    body = self.ref[e.open:e.close]
                    if sink == "d":
                        m = re.search(rb"\bbuildings=\{([^}]*)\}", body)
                        self._dist[e.key] = m.group(1).split() if m else []
                    else:
                        m = re.search(rb'\btype="?([\w-]+)', body)
                        if m:
                            self._btype[e.key] = m.group(1)
        return self._dist, self._btype

    def province(self, pid: str, text: bytes, out: Shaped) -> bytes:
        text, n = drop_fields(text, PROVINCE_FIELDS, 1)
        out.add("province size fields", n)
        h = None
        for c in re.finditer(rb"[\s{]holding=\{", text):
            if _depth_at(text, c.start() + 1) == 1:
                h = c
                break
        if h is None:
            return text
        open_ = h.end() - 1
        hb = text[open_:gs.match_brace(text, open_) + 1]
        if re.search(rb"\bbuildings=\{", hb):
            return text
        dist, btype = self._maps()
        main = None
        hd = re.search(rb"\bholding_district=(\d+)", hb)
        if hd and dist.get(hd.group(1)):
            main = btype.get(dist[hd.group(1)][0])
        wonders = []
        # duchy-capital wonders too (11 in the 1.21 reference; 1.21 writes duchy_capital_district=<id> with no type
        # line, 1.20 a built duchy_capital_building={ type=... }; refactor-advisor's row 6, the F7 audit)
        for kind in (b"special", b"great", b"duchy_capital"):
            built = re.search(rb"\b" + kind + rb"_district=(\d+)", hb)
            slot = re.search(rb"\b" + kind + rb'_district_type="?([\w-]+?)_district\b', hb)
            if slot:
                wonders.append(b"\n\t\t\t" + kind + b"_building_type=" + slot.group(1))
            if built and dist.get(built.group(1)):
                b = btype.get(dist[built.group(1)][0])
                if b:
                    wonders.append(b"\n\t\t\t" + kind + b"_building={\n\t\t\t\ttype=" + b + b"\n\t\t\t}")
        names = HOLDING_FIELDS + tuple(sorted({m.group(1) for m in re.finditer(rb"\b(\w+_district(?:_type)?)=", hb)}))
        hb2, n = drop_fields(hb, names, 1)
        out.add("holding district fields", n)
        htype = (re.search(rb'\btype="?(\w+)', hb2) or [None, b""])[1]
        count = self.slots.get(pid) or USUAL_SLOTS.get(htype, 3)
        entries = [b"{\n\t\t\t\t\ttype=" + main + b"\n\t\t\t\t}"] if main else []
        entries += [b"{\n\t\t\t\t}"] * max(0, count - len(entries))
        lines = b"\n\t\t\tbuildings={\n\t\t\t\t" + b"\n\t\t\t\t".join(entries) + b"\n\t\t\t}" + b"".join(wonders)
        t = re.search(rb'\n[ \t]*type="?\w+"?', hb2)
        at = t.end() if t else 1
        hb2 = hb2[:at] + lines + hb2[at:]
        out.add("holding buildings derived")
        if not main:
            out.add("holding without a main building")
        return text[:open_] + hb2 + text[open_ + len(hb):]
