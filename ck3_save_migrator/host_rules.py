"""Where the game accepts a building in 1.21: read from its files, each answer with the file and line to cite.

The rule this module exists for (djdarcy and the Director, 2026-11-17): a key defined in the game is not a key the game
accepts *here*. The building POC of patch day tested key overlap and missed that 1,361 pastures could never sit on a
castle. refactor-advisor's answer (the hostability note, ~17:10): one service reading the game's files, beside
faith_rules.py, that every carry, rule and lint check asks. This is its first relation, the one patch day's building
carry (the goal's S6) needs; the rest (laws, traditions, modifiers by scope) come when a caller needs them.

1.21's shape (measured 2026-11-17 on 1.21.0):
- common/holdings: each holding names its districts (``districts = { ... }``, ``primary_district = ...``);
- common/districts: each district names its buildings (``buildings = { ... }``, level 1 keys; a holding district names
  its main line as ``primary_building = castle_01``), and may carry a ``can_construct_potential`` trigger this module
  does not evaluate;
- common/buildings: each building names its next tier (``next_building``), so a district hosts the whole line;
- special, great and duchy-capital buildings live in a district named ``<key>_district`` (157 of v17's 188 have one).
All three folders keep their files in subfolders, files start with a byte-order mark, and keys may hold hyphens.

A verdict is three-valued: True (a district of the holding lists the building, ungated), False (none does), None (only
a gated district lists it: the game decides by a trigger, so the game's own re-save is the witness).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_KEY = r"([^\s={}#\"]+)"
_HEAD = re.compile(r"(?m)^" + _KEY + r"\s*=\s*\{")


@dataclass(frozen=True)
class Verdict:
    ok: bool | None             # True legal here, False refused, None decided by a trigger this module does not evaluate
    why: str
    where: str = ""             # file:line of the definition the answer rests on


@dataclass
class District:
    key: str
    buildings: set              # every building it hosts: its listed keys and each one's next tiers
    gated: bool                 # has can_construct_potential
    where: str
    kind: str = "regular"       # from its file: holding, regular, resource, or special (special, great, duchy-capital,
    #                             legendary, entrepot, other). Only holding and regular districts belong to a holding:
    #                             a resource district is the province's slot for its trade good, and a special one the
    #                             province's wonder slot (the first control failed on exactly this, 2026-11-17)
    # the gates the 2026-11-19 review found missing (final assessment 13:49): the district's own line, the district it
    # needs first, and the condition under which it gives its holder anything at all (_districts.info: "else won't give
    # any effects to holder")
    primary: str | None = None  # primary_building (pb_villages_01; household's is pb_royal_palace_01)
    unlocked_by: str | None = None
    enabled: str = ""           # the is_enabled block, whitespace collapsed; "" = always


@dataclass
class Place:
    """What a gate may ask of the province: the facts the save answers without a trigger engine."""
    county_capital: bool
    holding: str
    county_goods: frozenset | None = None   # trade goods the county has potential for (its provinces' resource
    #                                         districts, wool_district -> wool); None = not known, so not evaluated


@dataclass
class HostRules:
    holdings: dict              # holding -> (set of district keys, file:line)
    districts: dict             # district key -> District
    buildings: dict = field(default_factory=dict)   # building key -> file:line of its definition
    level_req: dict = field(default_factory=dict)   # building -> district_level_requirement (absent = 1)
    slots: dict = field(default_factory=dict)       # primary building -> building_slots_for_host_district
    b_enabled: dict = field(default_factory=dict)   # building -> its is_enabled block, collapsed
    b_potential: dict = field(default_factory=dict) # building -> its own can_construct_potential block, collapsed
    triggers: dict = field(default_factory=dict)    # scripted trigger -> body, collapsed

    @staticmethod
    def regular_slot_limit(province_size_level: int) -> int:
        """A holding's regular district slots: common/script_values/00_building_values.txt:2357-2366,
        floor((province_size_level + 1) / 2) + 1. It held for all 6,732 held holdings of the fresh reference (the
        13:35 review)."""
        return (province_size_level + 1) // 2 + 1

    @staticmethod
    def level(primary: str) -> int:
        """A district's level is its primary building's tier (pb_villages_03 -> 3)."""
        t = primary.rsplit("_", 1)[-1]
        return int(t) if t.isdigit() else 1

    def building_slots(self, primary: str) -> int:
        """The extra buildings a district with this primary hosts (before culture and terrain bonuses)."""
        return self.slots.get(primary, 0)

    def condition(self, text: str, place: Place, depth: int = 0) -> bool | None:
        """A gate's condition evaluated where the save can answer it: True, False, or None (a trigger this reader does
        not evaluate). Handles is_county_capital, holding_is_city, has_holding_type, AND/OR/NOT, custom_tooltip, and
        one scripted trigger level (metropolitan_type_district_trigger = county capital or city)."""
        return _eval(_parse(text), place, self.triggers, depth)

    def district_enabled(self, district: str, place: Place) -> Verdict:
        d = self.districts.get(district)
        if d is None:
            return Verdict(False, f"{district} is not a district this game defines")
        if not d.enabled:
            return Verdict(True, f"{district} is always enabled", d.where)
        ok = self.condition(d.enabled, place)
        return Verdict(ok, f"{district} is_enabled: {d.enabled}" + ("" if ok is not None else " (not evaluated)"),
                       d.where)

    def building_legal(self, building: str, district: str, primary: str, place: Place) -> Verdict:
        """May ``building`` stand in ``district`` whose primary is ``primary``, at ``place``? The line, the level, the
        building's own is_enabled, and its own trigger (left to the game: None, never written blind)."""
        v = self.building_in(building, district)
        if v.ok is False:
            return v
        need = self.level_req.get(building, 1)
        if need > self.level(primary):
            return Verdict(False, f"{building} needs district level {need}; {primary} gives {self.level(primary)}",
                           self.buildings.get(building, ""))
        if building in self.b_enabled:
            ok = self.condition(self.b_enabled[building], place)
            if ok is False:
                return Verdict(False, f"{building} is disabled here ({self.b_enabled[building]})",
                               self.buildings.get(building, ""))
            if ok is None:
                return Verdict(None, f"{building} is_enabled not evaluated: {self.b_enabled[building]}",
                               self.buildings.get(building, ""))
        if building in self.b_potential:
            ok = self.condition(self.b_potential[building], place)
            if ok is False:
                return Verdict(False, f"{building}'s can_construct_potential fails here", self.buildings.get(building, ""))
            if ok is None:
                return Verdict(None, f"{building} behind a trigger not evaluated (can_construct_potential)",
                               self.buildings.get(building, ""))
        if v.ok is None:
            return Verdict(None, f"{district} is gated: {v.why}", v.where)
        return Verdict(True, f"{district} at level {self.level(primary)} hosts {building}", v.where)

    def building_on(self, building: str, holding: str) -> Verdict:
        """May ``building`` stand on a ``holding``? Through any district the holding names."""
        if building not in self.buildings:
            return Verdict(False, f"{building} is not a building this game defines")
        if holding not in self.holdings:
            return Verdict(False, f"{holding} is not a holding this game defines")
        names, hwhere = self.holdings[holding]
        hosts = [self.districts[d] for d in sorted(names) if d in self.districts and building in self.districts[d].buildings]
        if not hosts:
            return Verdict(False, f"no district of {holding} lists {building}", hwhere)
        open_ = [d for d in hosts if not d.gated]
        if open_:
            return Verdict(True, f"{open_[0].key} hosts {building}", open_[0].where)
        return Verdict(None, f"only gated districts host {building} on {holding} ({', '.join(d.key for d in hosts)}): "
                             "a trigger decides", hosts[0].where)

    def building_in(self, building: str, district: str) -> Verdict:
        """Is ``building`` in ``district``'s line? The question for a resource or special district, which belongs to
        the province rather than to a holding."""
        if building not in self.buildings:
            return Verdict(False, f"{building} is not a building this game defines")
        d = self.districts.get(district)
        if d is None:
            return Verdict(False, f"{district} is not a district this game defines")
        if building not in d.buildings:
            return Verdict(False, f"{district} does not list {building}", d.where)
        if d.gated:
            return Verdict(None, f"{district} hosts {building} behind a trigger", d.where)
        return Verdict(True, f"{district} hosts {building}", d.where)

    def wonder_district(self, building: str) -> tuple[str | None, str]:
        """The district a special, great or duchy-capital building lives in: ``<key>_district`` exactly, else the
        district of its family at another tier (``the_great_wall_02`` -> ``the_great_wall_01_district``); else None.
        Returns (district, how): how is "exact", "family" or the reason there is none."""
        if f"{building}_district" in self.districts:
            return f"{building}_district", "exact"
        fam = re.sub(r"_\d+$", "", building)
        same = sorted(d for d in self.districts if d.startswith(fam + "_") and d.endswith("_district")
                      and re.fullmatch(re.escape(fam) + r"_\d+_district", d))
        if same:
            return same[0], "family"
        return None, f"no district named {building}_district or {fam}_<tier>_district"


def _blocks(path: Path):
    """(key, body text, line) for every top-level block of a script file; comments removed, line numbers kept."""
    text = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8-sig", errors="replace"))
    heads = [(m.start(), m.group(1)) for m in _HEAD.finditer(text)]
    for i, (pos, key) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        yield key, text[pos:end], text.count("\n", 0, pos) + 1


def _list(body: str, key: str) -> list[str]:
    m = re.search(r"\b" + key + r"\s*=\s*\{([^{}]*)\}", body)
    return re.findall(_KEY, m.group(1)) if m else []


def _inner(body: str, key: str) -> str:
    """The text inside ``key = { ... }`` at any depth of braces, whitespace collapsed; "" when absent."""
    m = re.search(r"(?m)^\s*" + key + r"\s*=\s*\{", body)
    if not m:
        return ""
    i, depth = m.end(), 1
    while i < len(body) and depth:
        depth += {"{": 1, "}": -1}.get(body[i], 0)
        i += 1
    return " ".join(body[m.end():i - 1].split())


def _parse(text: str) -> list:
    """A condition block as [(key, value)], value a word or a nested list."""
    toks = re.findall(r"[{}=]|[^\s{}=]+", text)

    def block(i):
        out = []
        while i < len(toks) and toks[i] != "}":
            key = toks[i]
            if i + 2 < len(toks) and toks[i + 1] == "=" and toks[i + 2] == "{":
                sub, i = block(i + 3)
                out.append((key, sub))
                i += 1                                   # the closing brace
            elif i + 2 < len(toks) and toks[i + 1] == "=":
                out.append((key, toks[i + 2]))
                i += 3
            else:
                out.append((key, None))
                i += 1
        return out, i
    return block(0)[0]


def _all(vals):
    vals = list(vals)
    return False if False in vals else None if None in vals else True


def _any(vals):
    vals = list(vals)
    return True if True in vals else None if None in vals else False


def _eval(items: list, place: Place, triggers: dict, depth: int, scope: str = "province") -> bool | None:
    out = []
    for key, val in items:
        if scope == "county":
            # inside county = { }: only the county's trade-good potential is answered (the villages buildings' gate)
            if key == "has_potential_for_trade_good" and isinstance(val, str):
                good = val.rsplit(":", 1)[-1].removeprefix("trade_good_")
                out.append(None if place.county_goods is None else good in place.county_goods)
            elif isinstance(val, list) and key in ("OR", "AND", "NOT"):
                r = [_eval([it], place, triggers, depth, scope) for it in val]
                out.append(_any(r) if key == "OR" else _all(r) if key == "AND" else
                           (None if _all(r) is None else not _all(r)))
            else:
                out.append(None)
            continue
        if key == "county" and isinstance(val, list):
            out.append(_eval(val, place, triggers, depth, "county"))
        elif key == "is_county_capital":
            out.append(place.county_capital == (val == "yes"))
        elif key == "holding_is_city":
            out.append((place.holding == "city_holding") == (val == "yes"))
        elif key == "has_holding_type":
            out.append(place.holding == val)
        elif key == "text" and isinstance(val, str):
            continue                                     # custom_tooltip's label
        elif isinstance(val, list) and key in ("AND", "custom_tooltip"):
            out.append(_eval(val, place, triggers, depth))
        elif isinstance(val, list) and key == "OR":
            out.append(_any(_eval([it], place, triggers, depth) for it in val))
        elif isinstance(val, list) and key == "NOT":
            r = _eval(val, place, triggers, depth)
            out.append(None if r is None else not r)
        elif val == "yes" and key in triggers and depth < 3:
            out.append(_eval(_parse(triggers[key]), place, triggers, depth + 1))
        else:
            out.append(None)                             # scope:, government flags, trigger_if, ...: not evaluated
    return _all(out)


@lru_cache(maxsize=4)
def load(game_dir: str) -> HostRules:
    game = Path(game_dir) / "common"
    nxt, buildings, level_req, slots, b_enabled, b_potential = {}, {}, {}, {}, {}, {}
    for f in sorted((game / "buildings").rglob("*.txt")):
        for key, body, line in _blocks(f):
            buildings[key] = f"{f.name}:{line}"
            n = re.search(r"\bnext_building\s*=\s*" + _KEY, body)
            if n:
                nxt[key] = n.group(1)
            m = re.search(r"\bdistrict_level_requirement\s*=\s*(\d+)", body)
            if m:
                level_req[key] = int(m.group(1))
            m = re.search(r"\bbuilding_slots_for_host_district\s*=\s*(\d+)", body)
            if m:
                slots[key] = int(m.group(1))
            e = _inner(body, "is_enabled")
            if e:
                b_enabled[key] = e
            p = _inner(body, "can_construct_potential")
            if p:
                b_potential[key] = p
    triggers = {}
    for f in sorted((game / "scripted_triggers").rglob("*.txt")) if (game / "scripted_triggers").is_dir() else []:
        for key, body, _ in _blocks(f):
            triggers[key] = " ".join(body[body.index("{") + 1:body.rindex("}")].split()) if "}" in body else ""
    districts = {}
    for f in sorted((game / "districts").rglob("*.txt")):
        for key, body, line in _blocks(f):
            # a holding district names its line as primary_building (castle_holding_district: castle_01), the others
            # list theirs in buildings = { }; both seed the next_building walk
            reach, todo = set(), _list(body, "buildings") + re.findall(r"\bprimary_building\s*=\s*" + _KEY, body)
            while todo:
                x = todo.pop()
                if x not in reach:
                    reach.add(x)
                    if x in nxt:
                        todo.append(nxt[x])
            kind = ("holding" if f.name.startswith("holding") else "resource" if f.name.startswith("resource")
                    else "regular" if f.name.startswith("regular") else "special")
            prim = re.search(r"\bprimary_building\s*=\s*" + _KEY, body)
            unl = re.search(r"\bunlocked_by\s*=\s*" + _KEY, body)
            districts[key] = District(key, reach, "can_construct_potential" in body, f"{f.name}:{line}", kind,
                                      prim.group(1) if prim else None, unl.group(1) if unl else None,
                                      _inner(body, "is_enabled"))
    holdings = {}
    for f in sorted((game / "holdings").rglob("*.txt")):
        for key, body, line in _blocks(f):
            names = set(_list(body, "districts")) | set(re.findall(r"\bprimary_district\s*=\s*" + _KEY, body))
            holdings[key] = (names, f"{f.name}:{line}")
    return HostRules(holdings, districts, buildings, level_req, slots, b_enabled, b_potential, triggers)
