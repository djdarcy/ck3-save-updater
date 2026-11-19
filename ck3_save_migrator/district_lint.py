"""The legality lint for 1.21 districts: does each holding's regular districts sit in a state a 1.21 game could be in?

Why it exists (the built-state carry's review, 2026-11-19 13:35, and its final assessment 13:49): the game keeps
illegal district states silently (measured 2026-11-17: over the slot limit, a guild without its housing, error.log named
none of them), so "the re-save kept it" proves nothing. This lint reads the gates host_rules carries and reports every
breach, with the fresh 1.21 reference as its control: the reference must come out (nearly) clean.

Checks, per holding: the regular districts against the slot limit from province size; each district's enable
condition and its unlocked_by prerequisite; villages and urban housing together (common/holdings/00_holdings.txt: "you
do not want to build both"); each building's legality in its district at its primary's level (host_rules.building_legal:
line, level, is_enabled, the county's trade-good potential); the building count against the primary's slots. Verdicts
host_rules cannot evaluate are counted as "unknown", never as breaches.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import gamestate as gs
from .host_rules import HostRules, Place

EMPTY = b"4294967295"


@dataclass
class Facts:
    place: Place
    size_level: int


@dataclass
class LintResult:
    breaches: list = field(default_factory=list)      # (province, kind, detail)
    unknown: collections.Counter = field(default_factory=collections.Counter)   # why -> count
    holdings: int = 0
    districts: int = 0
    buildings: int = 0

    def by_kind(self) -> collections.Counter:
        return collections.Counter(k for _, k, _ in self.breaches)


def county_potential_goods(game_dir) -> dict[str, frozenset]:
    """county key -> the trade goods it has potential for, from the game's own list:
    common/trade/county_potential_trade_goods/*.txt, ``trade_good_X = { counties = { c_a c_b ... } }``. (First read as
    the county's resource districts, 13:5x; the fresh reference's control showed 1,926 false breaches: pastures built in
    a county whose only resource district was millet. The potential list is wider.)"""
    from .host_rules import _blocks, _list
    d = Path(game_dir) / "common" / "trade" / "county_potential_trade_goods"
    out = collections.defaultdict(set)
    for f in sorted(d.rglob("*.txt")) if d.is_dir() else []:
        for key, body, _ in _blocks(f):
            for c in _list(body, "counties"):
                out[c].add(key.removeprefix("trade_good_"))
    return {c: frozenset(v) for c, v in out.items()}


def county_capital_baronies(game_dir) -> set[str]:
    """The game's county capitals: each county's first-listed barony in common/landed_titles. On the fresh 1.21 game
    this matched the save's capital_barony=yes for all 3,549 counties (2026-11-19 15:3x). Phase one needs it: a 1.20 save
    holds 1.20's capitals, and the 1.21 map moved some (province 3204: walls written as a capital, disabled after the
    conversion)."""
    from .deadtitles import title_tree
    parent, _ = title_tree(Path(game_dir) / "common" / "landed_titles")
    first = {}
    for k, p in parent.items():
        if k.startswith("b_") and p and p.startswith("c_") and p not in first:
            first[p] = k
    return set(first.values())


def province_facts(g: bytes, game_dir, capitals: str = "save") -> dict[str, Facts]:
    """province id -> what the gates ask: county capital, holding type, the county's goods, the size level. The county
    capital is the barony title with capital_barony=yes (the save), placed by common/landed_titles; the county's goods
    come from the game's county potential list (county_potential_goods)."""
    from .carry_1_21 import barony_counties
    from .mapdata import barony_provinces
    bprov = barony_provinces(Path(game_dir))           # the install's game/ folder, as the rules get it
    bcounty = barony_counties(game_dir)
    capital_prov = set()
    if capitals == "game":                             # phase one: the target game's capitals, not the 1.20 save's
        capital_prov = {str(bprov[b]) for b in county_capital_baronies(game_dir) if b in bprov}
    else:
        for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
            b = g[e.open:e.close]
            if re.search(rb"(?<!\w)capital_barony=yes", b):   # not duchy_capital_barony
                k = re.search(rb'\bkey="?([^\s"]+)', b)       # 1.20 quotes title keys, 1.21 does not
                if k and k.group(1).decode() in bprov:
                    capital_prov.add(str(bprov[k.group(1).decode()]))
    prov_county = {str(p): bcounty.get(b) for b, p in bprov.items()}
    potential = county_potential_goods(game_dir)
    holding, size = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if not (e.key and e.key.isdigit()):
            continue
        body = g[e.open:e.close]
        pid = e.key.decode()
        h = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", body, re.S)
        t = re.search(rb"\n\t\t\ttype=\"?(\w+)", h.group(1)) if h else None
        holding[pid] = t.group(1).decode() if t else None
        s = re.search(rb"\bprovince_size_level=(\d+)", body)
        size[pid] = int(s.group(1)) if s else 0
    out = {}
    for pid, ht in holding.items():
        if ht:
            county = prov_county.get(pid)
            cg = potential.get(county, frozenset()) if county else None     # a county off the list has none
            out[pid] = Facts(Place(pid in capital_prov, ht, cg), size[pid])
    return out


def lint(g: bytes, host: HostRules, facts: dict[str, Facts]) -> LintResult:
    res = LintResult()
    dist = {e.key: g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body)}
    btype = {e.key: re.search(rb"type=(\S+)", g[e.open:e.close]).group(1).decode()
             for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        pid = e.key.decode() if e.key else ""
        f = facts.get(pid)
        if f is None:
            continue
        h = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", g[e.open:e.close], re.S)
        m = re.search(rb"\bdistricts=\{([^{}]*)\}", h.group(1)) if h else None
        ids = [i for i in (m.group(1).split() if m else []) if i != EMPTY and i in dist]
        if not ids:
            continue
        res.holdings += 1
        types = []
        limit = host.regular_slot_limit(f.size_level)
        if len(ids) > limit:
            res.breaches.append((pid, "over the slot limit", f"{len(ids)} districts, size level {f.size_level} gives {limit}"))
        for i in ids:
            body = dist[i]
            dt = re.search(rb"type=(\w+)", body).group(1).decode()
            types.append(dt)
            res.districts += 1
            v = host.district_enabled(dt, f.place)
            if v.ok is False:
                res.breaches.append((pid, "district disabled here", v.why))
            elif v.ok is None:
                res.unknown[f"district {dt}: enable not evaluated"] += 1
            bl = re.search(rb"buildings=\{([^{}]*)\}", body)
            bids = [b for b in (bl.group(1).split() if bl else []) if b != EMPTY]
            keys = [btype.get(b, "?") for b in bids]
            if not keys:
                continue
            primary, extra = keys[0], keys[1:]
            cap = host.building_slots(primary)
            if len(extra) > cap:
                res.unknown[f"{dt}: more buildings than the primary's base slots (culture/terrain may add)"] += 1
            for k in extra:
                res.buildings += 1
                v = host.building_legal(k, dt, primary, f.place)
                if v.ok is False:
                    res.breaches.append((pid, "building illegal here", f"{k} in {dt} ({primary}): {v.why}"))
                elif v.ok is None:
                    res.unknown[f"building {re.sub(r'_[0-9]+$', '', k)}: not evaluated"] += 1
        for dt in types:
            need = host.districts[dt].unlocked_by if dt in host.districts else None
            if need and need not in types:
                res.breaches.append((pid, "district without its prerequisite", f"{dt} needs {need}"))
        if "villages_district" in types and "urban_housing_district" in types:
            res.breaches.append((pid, "villages and urban housing together", "00_holdings.txt: do not build both"))
    return res
