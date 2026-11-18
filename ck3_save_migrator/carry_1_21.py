"""The carry into 1.21: what the old save holds and the game's own conversion drops (patch day, the goal's S6).

The shape is djdarcy's decision C (OPEN-QUESTIONS Q261117-04, 2026-11-17): the tool writes the player's built state
as 1.21 districts into the save while it is still stamped 1.20, and the player's first load in 1.21 converts the
rest. S2 measured that this works: stamped 1.20, the game converts the whole save around districts we wrote and keeps
ours (all ten cases, read_resaves.py). It also keeps illegal ones silently, so every district written here is checked
against the game's files first (host_rules).

This module holds the deterministic part, the wonders: special, great and duchy-capital buildings. 1.20 keeps each
BUILT one in a block of its holding (v17: 115 special_building, 32 great_building, 11 duchy_capital_building; a bare
special_building_type= is only the province's slot, 365 of them, and a fresh 1.21 game writes districts for built ones
only). The conversion drops them all. In 1.21 each lives in a district named for it (host_rules.wonder_district), in
a holding slot chosen by the district's file, as a fresh 1.21 game writes it (measured on the 1.21 reference):

  special_districts.txt, special_mines_districts.txt -> special_district=<id> and special_district_type=<district>
  great_districts.txt                                 -> great_district=<id> and great_district_type=<district>
  duchy_capital_districts.txt                         -> duchy_capital_district=<id> (no type line)

A wonder with no district by name is reported, never guessed (the Director: "reported, never guessed"); so is one the
game's files refuse in that district (the great wall's tiers 2 and 3: 1.21's the_great_wall_01_district lists only
tier 1). A holding that already fills the slot is left alone, so a second run changes nothing. On v17: 134 carried
(114 special, 18 great, 2 duchy-capital), 10 unmapped (the duchy buildings 1.21 renamed, the Temple in Jerusalem),
20 refused (the wall's higher tiers).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import gamestate as gs
from .host_rules import HostRules

EMPTY = "4294967295"
_SLOT = {"special_districts.txt": ("special_district", True), "special_mines_districts.txt": ("special_district", True),
         "great_districts.txt": ("great_district", True), "duchy_capital_districts.txt": ("duchy_capital_district", False)}


@dataclass
class WondersResult:
    gamestate: bytes
    carried: list = field(default_factory=list)       # (province, building, district, slot)
    unmapped: list = field(default_factory=list)      # (province, building, why)
    skipped: list = field(default_factory=list)       # (province, building, why): slot already filled, or refused


def _max_id(g: bytes, path: str) -> int:
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return 0
    return max((int(e.key) for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()), default=0)


def _holdings(g: bytes):
    """(province entry, offset just past ``holding={``, holding body) for every province with a holding."""
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if not (e.key and e.key.isdigit()):
            continue
        h = re.search(rb"\n\t\tholding=\{", g[e.open:e.close])
        if h:
            at = e.open + h.end()
            yield e, at, g[at:gs.match_brace(g, at - 1)]


def _built_wonders(g: bytes, host: HostRules) -> dict[str, list[str]]:
    """province id -> the built wonders a 1.20 save holds there."""
    out = {}
    for e, at, hb in _holdings(g):
        # 1.20 keeps a holding's BUILT wonder in its own block, special_building={ type="danevirke_01" } (and the
        # duchy building in duchy_capital_building={ type=... }); special_building_type= alone is only the province's
        # slot (365 in v17, 115 built, plus 11 duchy buildings). A fresh 1.21 game writes districts for built ones
        # only (the reference: 220 wonder districts, none empty). Read on v17 and the 1.21 reference, 2026-11-17
        built = [m.group(1).decode() for m in
                 re.finditer(rb'\n\t\t\t(?:special_building|duchy_capital_building|great_building)=\{[^{}]*?'
                             rb'\btype="?([^\s"}]+)', hb)]
        # (great_building={ type=the_great_wall_03 } is the third block: the great walls, 32 provinces in v17)
        # and the great walls and the like, which 1.20 keeps in the holding's ordinary buildings list: a key of it
        # with a special district of its own in 1.21 (the first, accidental run carried 18 great_district from here)
        bl = re.search(rb"\n\t\t\tbuildings=\{", hb)
        if bl:
            start = at + bl.end() - 1
            for k in re.findall(rb'\{\s*type="?([^\s"}]+)', g[start + 1:gs.match_brace(g, start)]):
                k = k.decode()
                d, _ = host.wonder_district(k)
                if d is not None and host.districts[d].kind == "special" and k not in built:
                    built.append(k)
        if built:
            out[e.key.decode()] = built
    return out


def carry_wonders(g: bytes, host: HostRules, witness: bytes | None = None) -> WondersResult:
    """``g`` with each holding's built wonder written as its 1.21 district. Phase one (decision C): ``g`` is the 1.20
    save itself. Phase two for a player who already re-saved in 1.21 (the Director, 2026-11-18): ``g`` is that 1.21
    re-save and ``witness`` the last 1.20 save, whose wonders are read and written into ``g`` by province."""
    res = WondersResult(g)
    nb, nd = _max_id(g, "buildings/database"), _max_id(g, "districts/database")
    btext, dtext, p = [], [], gs.EditPass()
    wonders = _built_wonders(witness if witness is not None else g, host)
    for e, h_at, hb in _holdings(g):
        pid = e.key.decode()
        built = wonders.get(pid)
        if not built:
            continue
        for key in built:
            district, how = host.wonder_district(key)
            if district is None:
                res.unmapped.append((pid, key, how))
                continue
            d = host.districts[district]
            if d.kind != "special":
                res.unmapped.append((pid, key, f"{district} is not a special district"))
                continue
            slot, typed = _SLOT.get(d.where.split(":")[0], ("special_district", True))
            if re.search(rb"\b" + slot.encode() + rb"=\d", hb):
                res.skipped.append((pid, key, f"{slot} already filled"))
                continue
            v = host.building_in(key, district)
            if v.ok is False:
                res.skipped.append((pid, key, v.why))
                continue
            nb += 1
            nd += 1
            btext.append(f"\t\t{nb}={{\n\t\t\ttype={key}\n\t\t}}\n")
            dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {nb} }}\n\t\t\ttype={district}\n\t\t\towner={pid}\n\t\t}}\n")
            line = f"\n\t\t\t{slot}={nd}" + (f"\n\t\t\t{slot}_type={district}" if typed else "")
            t = re.search(rb'\n\t\t\ttype="?\w+"?', hb)
            at = h_at + (t.end() if t else 0)
            p.add(gs.Edit(at, at, line.encode(), "carry", f"{pid} {key} -> {district}"))
            res.carried.append((pid, key, district, slot))
    if not res.carried:
        return res
    out = p.apply(g)
    out = _append(out, "buildings/database", "buildings", "".join(btext))
    out = _append(out, "districts/database", "districts", "".join(dtext))
    res.gamestate = out
    return res


def _append(g: bytes, path: str, top: str, rows: str) -> bytes:
    """Rows at the end of ``path``'s body; the section is created at the end of the gamestate when absent."""
    try:
        b = gs.locate(g, path)
        return g[:b.close] + rows.encode() + b"\t" + g[b.close:]
    except gs.GamestateError:
        return g + f"{top}={{\n\tdatabase={{\n{rows}\t}}\n}}\n".encode()
