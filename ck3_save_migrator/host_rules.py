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


@dataclass
class HostRules:
    holdings: dict              # holding -> (set of district keys, file:line)
    districts: dict             # district key -> District
    buildings: dict = field(default_factory=dict)   # building key -> file:line of its definition

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


@lru_cache(maxsize=4)
def load(game_dir: str) -> HostRules:
    game = Path(game_dir) / "common"
    nxt, buildings = {}, {}
    for f in sorted((game / "buildings").rglob("*.txt")):
        for key, body, line in _blocks(f):
            buildings[key] = f"{f.name}:{line}"
            n = re.search(r"\bnext_building\s*=\s*" + _KEY, body)
            if n:
                nxt[key] = n.group(1)
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
            districts[key] = District(key, reach, "can_construct_potential" in body, f"{f.name}:{line}", kind)
    holdings = {}
    for f in sorted((game / "holdings").rglob("*.txt")):
        for key, body, line in _blocks(f):
            names = set(_list(body, "districts")) | set(re.findall(r"\bprimary_district\s*=\s*" + _KEY, body))
            holdings[key] = (names, f"{f.name}:{line}")
    return HostRules(holdings, districts, buildings)
