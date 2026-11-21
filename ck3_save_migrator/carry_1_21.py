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

import collections
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


def _next_index(g: bytes, path: str) -> int:
    """The first free id for a new row of a 1.21 database whose ids carry a generation in the high byte and the
    row's index in the low 24 bits (vassal_contracts: 117440512 = 0x07000000). The index is what must be unique: all
    3,529 contracts of djdarcy's re-save have distinct low-24 indexes, and a new contract given max+1 of the whole id
    (0x0F0006BB) reused an index for 56 of 63 rows, every one of which the game dropped on its next load (run
    2026-11-18__12-08-54; the 7 kept were exactly the 7 without a clash)."""
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return 1
    return 1 + max((int(e.key) & 0xFFFFFF for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()),
                   default=0)


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
                # duchy_capital: host_rules' own kind since stage two (the walls of Constantinople and Rome live there)
                if d is not None and host.districts[d].kind in ("special", "duchy_capital") and k not in built:
                    built.append(k)
        if built:
            out[e.key.decode()] = built
    return out


def carry_wonders(g: bytes, host: HostRules, witness: bytes | None = None) -> WondersResult:
    """``g`` with each holding's built wonder written as its 1.21 district. Phase one (decision C): ``g`` is the 1.20
    save itself. Phase two for a player who already re-saved in 1.21 (the Director, 2026-11-18): ``g`` is that 1.21
    re-save and ``witness`` the last 1.20 save, whose wonders are read and written into ``g`` by province."""
    res = WondersResult(g)
    # a fresh low-24 index for each new building and district, as for contracts: 1.21's ids carry a generation in the
    # high byte (the 1.21 reference: generations 0-2 in both databases), and the largest whole id + 1 lands on an index
    # already in use there (measured 2026-11-18, the test plan's C4)
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
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
            if d.kind not in ("special", "duchy_capital"):
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


@dataclass
class DuchyResult:
    gamestate: bytes
    written: list = field(default_factory=list)       # (province, old building, district, primary, new building)
    named: list = field(default_factory=list)         # (province, old building, why not written)


def carry_duchy_capitals(g: bytes, host: HostRules, witness: bytes, facts: dict) -> DuchyResult:
    """``g`` with each province's 1.20 duchy-capital building written into a 1.21 duchy-capital district (goal
    2026-11-19__22-43-27, S3; R45).

    1.21 keeps 16 of 1.20's 17 duchy-capital building families under the same key, inside duchy-capital districts that
    a province may hold where its barony is the duchy's capital barony and the county's holder holds the duchy
    (``can_have_duchy_capital_building_trigger``). The game's conversion of the founding campaign kept none of v17's
    9. Each is written only where every gate the save can answer holds -- the district enabled, its own building
    (primary) and the old building legal at the place, through host_rules with the stage-two facts -- else named. A
    holding that already has a duchy-capital district is left alone, so a second run changes nothing."""
    res = DuchyResult(g)
    duchy = {k: d for k, d in host.districts.items() if d.kind == "duchy_capital" and d.primary}
    old = {}
    for e, _, hb in _holdings(witness):
        keys = [k.decode() for k in re.findall(rb'\{\s*type="?([^\s"}]+)', hb)]
        hits = [k for k in keys if any(k in d.buildings and k != d.primary for d in duchy.values())
                or re.sub(r"_\d+$", "", k) in ("tax_assessor",)]
        if hits:
            old[e.key.decode()] = hits
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
    btext, dtext, p = [], [], gs.EditPass()
    for e, h_at, hb in _holdings(g):
        pid = e.key.decode()
        for key in old.get(pid, []):
            if re.search(rb"\bduchy_capital_district=\d", hb):
                res.named.append((pid, key, "the holding already has a duchy-capital district"))
                continue
            f = facts.get(pid)
            if f is None:
                res.named.append((pid, key, "no facts for this province"))
                continue
            why = f"no 1.21 duchy-capital district lists {key}"
            for dk, d in sorted(duchy.items()):
                if key not in d.buildings:
                    continue
                checks = (host.district_enabled(dk, f.place), host.building_legal(d.primary, dk, d.primary, f.place),
                          host.building_legal(key, dk, d.primary, f.place))
                bad = next((v for v in checks if v.ok is not True), None)
                if bad is not None:
                    why = f"{dk}: {bad.why}"
                    continue
                nb += 2
                nd += 1
                btext.append(f"\t\t{nb - 1}={{\n\t\t\ttype={d.primary}\n\t\t}}\n\t\t{nb}={{\n\t\t\ttype={key}\n\t\t}}\n")
                dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {nb - 1} {nb} }}\n\t\t\ttype={dk}\n\t\t\towner={pid}\n\t\t}}\n")
                t = re.search(rb'\n\t\t\ttype="?\w+"?', hb)
                at = h_at + (t.end() if t else 0)
                p.add(gs.Edit(at, at, f"\n\t\t\tduchy_capital_district={nd}".encode(), "carry", f"{pid} {key} -> {dk}"))
                res.written.append((pid, key, dk, d.primary, key))
                break
            else:
                res.named.append((pid, key, why))
    if not res.written:
        return res
    out = p.apply(g)
    out = _append(out, "buildings/database", "buildings", "".join(btext))
    out = _append(out, "districts/database", "districts", "".join(dtext))
    res.gamestate = out
    return res


RESOURCE_FAMILIES = {   # 1.20 family -> (1.21 resource district, trade good, the minor building family) -- S5, R46
    "quarries": ("stone_district", "stone", "stone_cutters"),
    "logging_camps": ("forestry_district", "wood", "minor_forestry"),
    "orchards": ("fruit_district", "fruit", "fruit_gardens"),
    "elephant_pens": ("ivory_district", "ivory", "ivory_camp"),
}


@dataclass
class ResourceResult:
    gamestate: bytes
    written: list = field(default_factory=list)       # (province, family, district, primary)
    raised: list = field(default_factory=list)        # (province, family, old primary, new primary)
    minor: list = field(default_factory=list)         # (province, family, host district, minor building)
    replaced: list = field(default_factory=list)      # (province, family, old district, new district)
    named: list = field(default_factory=list)         # (province, family, why)


def carry_resource_districts(g: bytes, host: HostRules, witness: bytes, facts: dict, asker) -> ResourceResult:
    """``g`` with each 1.20 resource-type building carried into the province's 1.21 resource slot (goal
    2026-11-19__22-43-27, S5; R46). A 1.21 resource district is player-built where the county has the trade good's
    potential, one per province. Per province, for quarries, logging camps, orchards and elephant pens: an empty slot
    gets the district, its primary at the old tier (at most 2 -- higher tiers need innovations no converted culture
    has -- and only as far as host_rules allows); the same district is raised to the old tier; another district asks
    the player (``resources``: keep, add the game's minor building inside it, or replace a district holding nothing but
    its primary). Two families for one empty slot are named. A second run changes nothing it already wrote."""
    res = ResourceResult(g)
    old = {}
    for e, _, hb in _holdings(witness):
        for k in re.findall(rb'\{\s*type="?([a-z_]+)_(\d+)', hb):
            fam, t = k[0].decode(), int(k[1])
            if fam in RESOURCE_FAMILIES:
                old.setdefault(e.key.decode(), {})[fam] = max(t, old.get(e.key.decode(), {}).get(fam, 0))
    D = {e.key.decode(): (e, g[e.open:e.close]) for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body) if e.key}
    B = {e.key.decode(): g[e.open:e.close] for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body) if e.key}
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
    btext, dtext, p = [], [], gs.EditPass()

    def primary_at(district, tier, place):
        best = None
        for n in range(1, min(tier, 2) + 1):
            k = f"{host.districts[district].primary.rsplit('_', 1)[0]}_{n}"
            if host.building_legal(k, district, k, place).ok is True:
                best = k
        return best

    for e, h_at, hb in _holdings(g):
        pid = e.key.decode()
        fams = old.get(pid)
        f = facts.get(pid)
        if not fams or f is None:
            continue
        goods = f.place.county_goods or frozenset()
        able = {fam: t for fam, t in fams.items() if RESOURCE_FAMILIES[fam][1] in goods}
        for fam in fams.keys() - able.keys():
            res.named.append((pid, fam, "the county has no potential for its trade good"))
        if not able:
            continue
        slot = re.search(rb"\n\t\t\tresource_district=(\d+)", hb)
        if slot is None:
            if len(able) > 1:
                res.named.append((pid, "+".join(sorted(able)), "several families for one empty resource slot"))
                continue
            fam, t = next(iter(able.items()))
            dk = RESOURCE_FAMILIES[fam][0]
            prim = primary_at(dk, t, f.place)
            if prim is None:
                res.named.append((pid, fam, f"{dk}'s primary is not legal here"))
                continue
            nb += 1
            nd += 1
            btext.append(f"\t\t{nb}={{\n\t\t\ttype={prim}\n\t\t}}\n")
            dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {nb} }}\n\t\t\ttype={dk}\n\t\t\towner={pid}\n\t\t}}\n")
            t_ = re.search(rb'\n\t\t\ttype="?\w+"?', hb)
            at = h_at + (t_.end() if t_ else 0)
            p.add(gs.Edit(at, at, f"\n\t\t\tresource_district={nd}".encode(), "carry", f"{pid} {fam} -> {dk}"))
            res.written.append((pid, fam, dk, prim))
            continue
        ent, body = D.get(slot.group(1).decode(), (None, b""))
        cur = re.search(rb"\btype=([a-z_]+)", body)
        cur = cur.group(1).decode() if cur else None
        ids = re.findall(rb"\d+", re.search(rb"buildings=\{([^}]*)\}", body).group(1)) if b"buildings=" in body else []
        types = [re.search(rb'type="?([a-z_0-9]+)', B.get(i.decode(), b"")) for i in ids]
        types = [m.group(1).decode() for m in types if m]
        for fam, t in sorted(able.items()):
            dk, _, minor = RESOURCE_FAMILIES[fam]
            if cur == dk:
                prim = primary_at(dk, t, f.place)
                if prim and types and host.level(prim) > host.level(types[0]) and ent is not None and ids:
                    bid = ids[0].decode()
                    m = re.search(rb'type="?' + types[0].encode(), B[bid])
                    be = next(x for x in gs.iter_entries(g, *gs.locate(g, "buildings/database").body) if x.key == ids[0])
                    p.add(gs.Edit(be.open + m.start(), be.open + m.end(), f"type={prim}".encode(), "carry", f"{pid} raise"))
                    res.raised.append((pid, fam, types[0], prim))
                continue
            label = f"province {pid}: your {fam.replace('_', ' ')} (tier {t}); the slot holds {cur}"
            a = asker.ask("resources", label)
            if a == "k":
                res.named.append((pid, fam, f"kept the game's {cur} (answer k)"))
            elif a == "m":
                mk = f"{minor}_1"
                free = host.building_slots(types[0]) - (len(types) - 1) if types else 0
                if cur not in host.districts or mk not in host.districts[cur].buildings or free < 1 or ent is None:
                    res.named.append((pid, fam, f"{cur} has no room for {mk}"))
                    continue
                v = host.building_legal(mk, cur, types[0], f.place)
                if v.ok is not True:
                    res.named.append((pid, fam, v.why))
                    continue
                nb += 1
                btext.append(f"\t\t{nb}={{\n\t\t\ttype={mk}\n\t\t}}\n")
                bl = re.search(rb"buildings=\{([^}]*)\}", body)
                at = ent.open + bl.end(1)
                p.add(gs.Edit(at, at, f" {nb} ".encode(), "carry", f"{pid} minor {mk}"))
                res.minor.append((pid, fam, cur, mk))
                types.append(mk)
            elif a == "r":
                if len(types) > 1 or ent is None:
                    res.named.append((pid, fam, f"{cur} holds buildings beyond its primary; not replaced"))
                    continue
                prim = primary_at(dk, t, f.place)
                if prim is None:
                    res.named.append((pid, fam, f"{dk}'s primary is not legal here"))
                    continue
                m = re.search(rb"\btype=" + cur.encode(), body)
                p.add(gs.Edit(ent.open + m.start(), ent.open + m.end(), f"type={dk}".encode(), "carry", f"{pid} replace"))
                be = next(x for x in gs.iter_entries(g, *gs.locate(g, "buildings/database").body) if x.key == ids[0])
                mb = re.search(rb'type="?' + types[0].encode(), B[ids[0].decode()])
                p.add(gs.Edit(be.open + mb.start(), be.open + mb.end(), f"type={prim}".encode(), "carry", f"{pid} replace primary"))
                res.replaced.append((pid, fam, cur, dk))
                # one resource slot: the families still to come in this province are named, not edited against text
                # this pass has already rewritten (a second family crashed here, found by its test 2026-11-20)
                for rest, _ in sorted(able.items()):
                    if rest > fam:
                        res.named.append((pid, rest, f"the slot was given to {fam}"))
                break
    if not (res.written or res.raised or res.minor or res.replaced):
        return res
    out = p.apply(g)
    if btext:
        out = _append(out, "buildings/database", "buildings", "".join(btext))
    if dtext:
        out = _append(out, "districts/database", "districts", "".join(dtext))
    res.gamestate = out
    return res


@dataclass
class TiersResult:
    gamestate: bytes
    restored: list = field(default_factory=list)      # (province, conversion's key, witness's key)
    skipped: list = field(default_factory=list)       # (province, witness's key, why)


def _witness_mains(w: bytes) -> dict[str, list[str]]:
    """province id -> the building keys of the 1.20 witness's holding (its own line is among them: castle_02)."""
    out = {}
    for e, at, hb in _holdings(w):
        bl = re.search(rb"\n\t\t\tbuildings=\{", hb)
        if bl:
            start = at + bl.end() - 1
            out[e.key.decode()] = [k.decode() for k in
                                   re.findall(rb'\{\s*type="?([^\s"}]+)', w[start + 1:gs.match_brace(w, start)])]
    return out


def carry_holding_tiers(g: bytes, host: HostRules, witness: bytes) -> TiersResult:
    """Each holding's main building back at the witness's tier. The game's 1.21 conversion resets every main building
    above tier 1 (275 of 275 on the founding campaign: 165 tribe_02, 56 city_02, 51 temple_02, 3 castle_02; the
    built-state review, 2026-11-19 13:35); djdarcy, 01:3x: restore from the witness ("We can try that sure"). Only a
    raise, only to a key 1.21 defines in the holding district's own line, and only where the witness holds the same line.
    Runs before the district carry: the holding's tier is where 1.21's tier chain starts."""
    res = TiersResult(g)
    mains = _witness_mains(witness)
    dist = _entries(g, "districts/database")
    blds = _entries(g, "buildings/database")
    p = gs.EditPass()
    for e, _, hb in _holdings(g):
        pid = e.key.decode()
        hd = re.search(rb"\bholding_district=(\d+)", hb)
        if not hd or hd.group(1).decode() not in dist or pid not in mains:
            continue
        db = dist[hd.group(1).decode()]
        dbody = g[db.open:db.close]
        dtype = re.search(rb"\btype=(\w+)", dbody).group(1).decode()
        first = re.search(rb"buildings=\{\s*(\d+)", dbody)
        if not first or first.group(1).decode() not in blds:
            continue
        bb = blds[first.group(1).decode()]
        tm = re.search(rb"\btype=(\S+)", g[bb.open:bb.close])
        now = tm.group(1).decode()
        fam = re.sub(r"_\d+$", "", now)
        old = next((k for k in mains[pid] if re.sub(r"_\d+$", "", k) == fam), None)
        if old is None:
            continue
        lvl = lambda k: int(k.rsplit("_", 1)[1]) if k.rsplit("_", 1)[-1].isdigit() else 0  # noqa: E731
        if lvl(old) <= lvl(now):
            continue
        v = host.building_in(old, dtype)
        if v.ok is not True:
            res.skipped.append((pid, old, v.why))
            continue
        at = bb.open + tm.start(1)
        p.add(gs.Edit(at, at + len(now), old.encode(), "tiers", f"{pid} {now} -> {old}"))
        res.restored.append((pid, now, old))
    if res.restored:
        res.gamestate = p.apply(g)
    return res


@dataclass
class DistrictsResult:
    gamestate: bytes
    written: list = field(default_factory=list)       # (province, district, [building keys], primary)
    open: list = field(default_factory=list)          # (province, old key, why): no successor chosen yet
    refused: list = field(default_factory=list)       # (province, old key, why): illegal or not evaluable here
    dropped: list = field(default_factory=list)       # (province, old key, why): over the slots, by the keep-order


def load_successors(path=None) -> dict:
    """The hand-maintained successor table (ck3_save_migrator/successors/successors_1_21.toml): family -> row."""
    from pathlib import Path

    from .patches.model import tomllib   # the shared reader: tomllib, or tomli on Python 3.10 (CI run 44663465967)
    p = Path(path) if path else Path(__file__).with_name("successors") / "successors_1_21.toml"
    return tomllib.loads(p.read_text(encoding="utf-8"))["families"]


def _chain(host: HostRules, family: str) -> list[str]:
    return sorted((b for b in host.buildings if re.fullmatch(re.escape(family) + r"_\d+", b)),
                  key=lambda k: int(k.rsplit("_", 1)[1]))


def _lvl(k: str) -> int:
    t = k.rsplit("_", 1)[-1]
    return int(t) if t.isdigit() else 1


def carry_districts(g: bytes, host: HostRules, witness: bytes, facts: dict, table: dict,
                    tier_policy: str = "raise", insert: bool = False) -> DistrictsResult:
    """Phase two of the built-state carry: each holding's 1.20 regular buildings (from ``witness``) written into the
    regular districts the game's conversion left empty (``g``), legal by the game's own gates.

    The design of record: the collabN-local 1 final assessment, 2026-11-19 13:49. Per holding:
    - each old building -> the first of its family's successors (``table``) whose district is enabled here, at the old
      tier capped at the successor line's top; a family with no successor is named (``open``), never guessed;
    - ``tier_policy``: "raise" sets each district's primary to the level its buildings need (keeps the player's tiers;
      djdarcy's recommended answer, pending, HOLD 13:49), "cap" keeps primaries at tier 1 and caps the buildings there;
    - each building checked by host.building_legal at that primary: refused when illegal, and refused when a trigger
      cannot be evaluated (the game keeps illegal states silently, so nothing is written blind);
    - districts kept by: a prerequisite present (unlocked_by), never villages and urban housing together, then the sum of
      old tiers, then the count, then the table's order; at most the size's slot limit; buildings at most the
      primary's slots, lowest tiers dropped first. Every building not written is named with its reason.
    ``facts``: province id -> district_lint.Facts (county capital, holding type, county goods, size level)."""
    from .district_lint import EMPTY
    res = DistrictsResult(g)
    mains = _witness_mains(witness)
    holding_lines = {re.sub(r"_\d+$", "", d.primary) for d in host.districts.values()
                     if d.kind == "holding" and d.primary}
    order = {f: i for i, f in enumerate(table)}
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
    btext, dtext, p = [], [], gs.EditPass()
    for e, h_at, hb in _holdings(g):
        pid = e.key.decode()
        f = facts.get(pid)
        m = re.search(rb"\bdistricts=\{([^{}]*)\}", hb)
        if f is None or pid not in mains or (not m and not insert):
            continue
        # phase one (insert=True, R41): a 1.20 holding has no districts line; the game's conversion gives every held
        # holding two regular slots, so the carry writes into two (R33 showed the game keeps districts written into a
        # 1.20 save)
        slots = m.group(1).split() if m else [EMPTY, EMPTY]
        if any(s != EMPTY for s in slots):
            continue                                     # the player has districts already: never replaced
        plan = {}                                        # district -> [(old key, new key)]
        for old in mains[pid]:
            fam = re.sub(r"_\d+$", "", old)
            if fam in holding_lines or host.wonder_district(old)[0]:
                continue                                 # the holding's own line (R44), wonders (R35)
            row = table.get(fam)
            if row is None or not row["successors"]:
                res.open.append((pid, old, (row or {}).get("open", "not in the successor table")))
                continue
            for s in row["successors"]:
                if host.district_enabled(s["district"], f.place).ok is not True:
                    continue
                chain = _chain(host, s["building"])
                if not chain:
                    continue
                want = min(_lvl(old), _lvl(chain[-1])) if tier_policy == "raise" else 1
                plan.setdefault(s["district"], []).append((old, next(k for k in chain if _lvl(k) >= want)))
                break
            else:
                res.refused.append((pid, old, "no successor's district is enabled here"))
        # prerequisites, and never villages with urban housing
        for d in list(plan):
            need = host.districts[d].unlocked_by
            if need and need not in plan:
                res.dropped.extend((pid, o, f"{d} needs {need}") for o, _ in plan.pop(d))
        if "villages_district" in plan and "urban_housing_district" in plan:
            lose = min(("villages_district", "urban_housing_district"),
                       key=lambda d: (sum(_lvl(o) for o, _ in plan[d]), len(plan[d])))
            res.dropped.extend((pid, o, "villages and urban housing are not built together") for o, _ in plan.pop(lose))
        ranked = sorted(plan.items(), key=lambda kv: (-sum(_lvl(o) for o, _ in kv[1]), -len(kv[1]),
                                                       min(order.get(re.sub(r"_\d+$", "", o), 9999) for o, _ in kv[1])))
        limit = min(host.regular_slot_limit(f.size_level), len(slots))
        decided = []                                     # (district, primary, [kept keys], [(old, key)] kept)
        for d, pairs in ranked:
            line = _chain(host, re.sub(r"_\d+$", "", host.districts[d].primary))
            need = max(host.level_req.get(k, 1) for _, k in pairs) if tier_policy == "raise" else 1
            primary = next((k for k in line if host.level(k) >= need), line[-1])
            keep, kept_pairs = [], []
            for o, k in sorted(pairs, key=lambda x: -_lvl(x[0])):
                v = host.building_legal(k, d, primary, f.place)
                if v.ok is not True:
                    res.refused.append((pid, o, f"{k}: {v.why}"))
                elif len(keep) >= host.building_slots(primary):
                    res.dropped.append((pid, o, f"{d} has {host.building_slots(primary)} building slots"))
                else:
                    keep.append(k)
                    kept_pairs.append((o, k))
            if keep:
                decided.append((d, primary, keep, kept_pairs))
        # the slot limit, then prerequisites again: a dependent district whose prerequisite was refused or cut is
        # dropped too (the lint caught one: a manor district whose villages district had lost its buildings)
        for d, _, _, kp in decided[limit:]:
            res.dropped.extend((pid, o, f"over the {limit} district slots of this province") for o, _ in kp)
        decided = decided[:limit]
        kept_types = {d for d, *_ in decided}
        for item in list(decided):
            need = host.districts[item[0]].unlocked_by
            if need and need not in kept_types:
                decided.remove(item)
                res.dropped.extend((pid, o, f"{item[0]} needs {need}") for o, _ in item[3])
        new_ids = []
        for d, primary, keep, _ in decided:
            ids = []
            for k in [primary] + keep:
                nb += 1
                ids.append(str(nb))
                btext.append(f"\t\t{nb}={{\n\t\t\ttype={k}\n\t\t}}\n")
            nd += 1
            dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {' '.join(ids)} }}\n\t\t\ttype={d}\n\t\t\towner={pid}\n\t\t}}\n")
            new_ids.append(str(nd))
            res.written.append((pid, d, keep, primary))
        if new_ids:
            filled = new_ids + [s.decode() for s in slots[len(new_ids):]]
            line = f"districts={{ {' '.join(filled)} }}".encode()
            if m:
                at = h_at + m.start()
                p.add(gs.Edit(at, at + len(m.group(0)), line, "districts", f"{pid}: {len(new_ids)} districts"))
            else:
                t = re.search(rb'\n\t\t\ttype="?\w+"?', hb)
                at = h_at + (t.end() if t else 0)
                p.add(gs.Edit(at, at, b"\n\t\t\t" + line, "districts", f"{pid}: {len(new_ids)} districts (inserted)"))
    if not res.written:
        return res
    out = p.apply(g)
    out = _append(out, "buildings/database", "buildings", "".join(btext))
    out = _append(out, "districts/database", "districts", "".join(dtext))
    res.gamestate = out
    return res


def carry_reference_districts(g: bytes, ref: bytes, host: HostRules, facts: dict, pids) -> DistrictsResult:
    """Phase one on the route from an old save fed a 1.21 reference: a province the transplant copied from the reference
    has the reference's state, and the down-shaper stripped its 1.21 districts (downshape.py). Here those districts come
    back, the reference's own types and buildings, through the same gates as the carry (enabled here, legal at the
    district's level), into the conversion's two slots. On v17's K7 route the transplant copied 3,814 holdings in 1,001
    counties (the K7 results note, 2026-11-18 19:46). A province that already has districts is never touched."""
    from .district_lint import EMPTY
    res = DistrictsResult(g)
    rdist = _entries(ref, "districts/database")
    rbld = _entries(ref, "buildings/database")
    rprov = {e.key.decode(): ref[e.open:e.close] for e in gs.iter_entries(ref, *gs.locate(ref, "provinces").body)
             if e.key}
    want = set(pids)
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
    btext, dtext, p = [], [], gs.EditPass()
    for e, h_at, hb in _holdings(g):
        pid = e.key.decode()
        f = facts.get(pid)
        if pid not in want or f is None or re.search(rb"\bdistricts=\{", hb) or pid not in rprov:
            continue
        rh = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", rprov[pid], re.S)
        m = re.search(rb"\bdistricts=\{([^{}]*)\}", rh.group(1)) if rh else None
        cands = []
        for did in (m.group(1).split() if m else []):
            if did == EMPTY or did.decode() not in rdist:
                continue
            body = ref[rdist[did.decode()].open:rdist[did.decode()].close]
            dtype = re.search(rb"\btype=(\w+)", body).group(1).decode()
            bl = re.search(rb"buildings=\{([^{}]*)\}", body)
            keys = [re.search(rb"\btype=(\S+)", ref[rbld[b.decode()].open:rbld[b.decode()].close]).group(1).decode()
                    for b in (bl.group(1).split() if bl else []) if b != EMPTY and b.decode() in rbld]
            if not keys:
                continue
            if host.district_enabled(dtype, f.place).ok is not True:
                res.refused.append((pid, dtype, "district not enabled here"))
                continue
            primary, extra = keys[0], []
            for k in keys[1:]:
                v = host.building_legal(k, dtype, primary, f.place)
                (extra.append(k) if v.ok is True else res.refused.append((pid, k, v.why)))
            cands.append((dtype, primary, extra))
        kept = cands[:2]                                 # the conversion's two slots, in the reference's order
        types = {c[0] for c in kept}
        for c in list(kept):                             # a dependent district only with its prerequisite
            need = host.districts[c[0]].unlocked_by if c[0] in host.districts else None
            if need and need not in types:
                kept.remove(c)
                res.dropped.append((pid, c[0], f"{c[0]} needs {need}"))
        new_ids = []
        for dtype, primary, extra in kept:
            ids = []
            for k in [primary] + extra:
                nb += 1
                ids.append(str(nb))
                btext.append(f"\t\t{nb}={{\n\t\t\ttype={k}\n\t\t}}\n")
            nd += 1
            dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {' '.join(ids)} }}\n\t\t\ttype={dtype}\n\t\t\towner={pid}\n\t\t}}\n")
            new_ids.append(str(nd))
            res.written.append((pid, dtype, extra, primary))
        if new_ids:
            line = f"districts={{ {' '.join(new_ids + [EMPTY.decode()] * (2 - len(new_ids)))} }}".encode()
            t = re.search(rb'\n\t\t\ttype="?\w+"?', hb)
            at = h_at + (t.end() if t else 0)
            p.add(gs.Edit(at, at, b"\n\t\t\t" + line, "districts", f"{pid}: the reference's districts"))
    if not res.written:
        return res
    out = p.apply(g)
    out = _append(out, "buildings/database", "buildings", "".join(btext))
    out = _append(out, "districts/database", "districts", "".join(dtext))
    res.gamestate = out
    return res


@dataclass
class BaroniesResult:
    gamestate: bytes
    carried: list = field(default_factory=list)       # (barony key, old holder, county holder, liege changed?)
    skipped: list = field(default_factory=list)       # (barony key, old holder, why)


def _common(game_dir):
    """The game's common/ folder, given the install folder or its game/ folder (the rules get the latter)."""
    from pathlib import Path
    d = Path(game_dir)
    return d / "common" if (d / "common").is_dir() else d / "game" / "common"


def barony_counties(game_dir) -> dict[str, str]:
    """barony key -> its county key, from the game's own title files (a barony nests in its county)."""
    out = {}
    for f in sorted((_common(game_dir) / "landed_titles").rglob("*.txt")):
        county = None
        text = re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))
        for m in re.finditer(r"\b([cb]_[\w\-']+)\s*=\s*\{", text):
            k = m.group(1)
            if k.startswith("c_"):
                county = k
            elif county:
                out[k] = county
    return out


def _entries(g: bytes, path: str) -> dict[str, gs.Block]:
    return {e.key.decode(): e for e in gs.iter_entries(g, *gs.locate(g, path).body) if e.key}


def _field(body: bytes, key: str) -> re.Match | None:
    """The first ``key=value`` line of ``body`` at its own top level (the indentation of its first line)."""
    first = re.search(rb"\n(\s*)\S", body)
    ind = first.group(1) if first else b"\t"
    return re.search(rb"\n" + re.escape(ind) + re.escape(key.encode()) + rb'="?([^\s"]+)', body)


def defined_governments(game_dir) -> set[str]:
    """The government keys the game defines (common/governments)."""
    out = set()
    for f in sorted((_common(game_dir) / "governments").glob("*.txt")):
        out |= set(re.findall(r"(?m)^(\w+_government)\s*=", f.read_text(encoding="utf-8-sig", errors="replace")))
    return out


def carry_baronies(g: bytes, witness: bytes, counties: dict[str, str],
                   governments: set[str] | None = None) -> BaroniesResult:
    """Phase two (the Director's two-phase DWP, unit 5): give back the baronies the game's conversion took from their
    holders. 1.21 moved some baronies to another county, and the conversion hands such a barony to its new county's
    holder (measured on djdarcy's re-save of v17, 2026-11-18: all 63 of the 66 stripped one-barony vassals; the 2,070
    kept were untouched). ``g`` is the 1.21 re-save; ``witness`` the 1.20 save it came from, the same date (the rule
    guards that). A barony is carried when its witness holder is alive in ``g``, lost it, and its holder in ``g`` holds
    its 1.21 county, the conversion's signature; anything else is left alone. The old holder becomes the county
    holder's vassal, with the contract levels the game writes for that pair of governments."""
    res = BaroniesResult(g)
    tw, tg = _entries(witness, "landed_titles/landed_titles"), _entries(g, "landed_titles/landed_titles")
    # a title's own key is its first key= (1.21 writes it on the type= line: "type=title_type_default_static\tkey=b_x")
    # an apostrophe belongs to a key (1.21: b_mansa'l-kharaz, b_ka'abir; F7 audit 2026-11-18)
    tkey = lambda gg, e: re.search(rb'\bkey="?([\w\-\']+)', gg[e.open:min(e.close, e.open + 400)])
    key_w = {i: tkey(witness, e) for i, e in tw.items()}
    by_key = {}
    for i, e in tg.items():
        k = tkey(g, e)
        if k:
            by_key[k.group(1).decode()] = i
    hold = lambda gg, e: (_field(gg[e.open:e.close], "holder") or [None, b""])[1].decode()
    lg, lw = _entries(g, "living"), _entries(witness, "living")
    gov_of = lambda gg, L, i: (re.search(rb'\bgovernment="?(\w+)', gg[L[i].open:L[i].close])
                               or [None, b"none"])[1].decode() if i in L else "none"
    gov = lambda i: gov_of(g, lg, i)
    # 1.21 keeps government= inside landed_data, and the conversion drops it from a holder it left landless (measured
    # 2026-11-18: without it the game's next load dropped 56 of 63 restored contracts). It is written back from the
    # witness, only when the game still defines it
    back = {}
    # the levels the game itself writes in g, per (vassal government, liege government): 1.21 renumbered contract types
    levels, cdb = {}, gs.locate(g, "vassal_contracts/database")
    for e in gs.iter_entries(g, *cdb.body):
        c = g[e.open:e.close]
        v, li = re.search(rb"\bvassal=(\d+)", c), re.search(rb"\bliege=(\d+)", c)
        lv = re.search(rb"\blevels=\{[^}]*\}", c)
        if v and li and lv and v.group(1).decode() in lg and li.group(1).decode() in lg:
            levels.setdefault((gov(v.group(1).decode()), gov(li.group(1).decode())), []).append(lv.group(0).decode())
    wanted = {}                                       # old holder -> [(barony key, title id, county holder)]
    for i, e in tw.items():
        k = key_w[i]
        if not (k and k.group(1).startswith(b"b_")):
            continue
        key, h = k.group(1).decode(), hold(witness, e)
        gi = by_key.get(key)
        if not h or gi is None:
            if h and gi is None:
                res.skipped.append((key, h, "the barony is not in 1.21"))
            continue
        now = hold(g, tg[gi])
        if now == h or not now:
            continue
        ci = by_key.get(counties.get(key, ""))
        if ci is None or hold(g, tg[ci]) != now:
            continue                                  # not the conversion's signature: left alone
        if h not in lg:
            res.skipped.append((key, h, "the old holder is not alive in the 1.21 save"))
            continue
        wanted.setdefault(h, []).append((key, gi, now))
    p, rows, nc = gs.EditPass(), [], _next_index(g, "vassal_contracts/database") - 1   # a fresh low-24 index each
    lists, gives, adds = {}, {}, {}   # liege -> new contract ids; character -> title ids leaving / joining its domain
    for h, items in wanted.items():
        hb = g[lg[h].open:lg[h].close]
        ld = re.search(rb"\n([ \t]*)landed_data=\{", hb)
        if not ld:
            for key, _, _ in items:
                res.skipped.append((key, h, "the old holder has no landed_data to write into"))
            continue
        dm = re.search(rb"\bdomain=\{([^}]*)\}", hb)
        if dm:
            # a holder who kept other land (16 in djdarcy's re-save of v17): the barony joins the domain they have;
            # their government and capital are still in place
            for key, gi, liege in items:
                adds.setdefault(h, []).append(gi.encode())
                gives.setdefault(liege, []).append(gi.encode())
                t = tg[gi]
                hm = _field(g[t.open:t.close], "holder")
                p.add(gs.Edit(t.open + hm.start(1), t.open + hm.end(1), h.encode(), "carry", f"{key} -> {h}"))
                res.carried.append((key, h, liege, "kept their own liege: holds other land"))
            continue
        wg = gov_of(witness, lw, h)
        if not re.search(rb"\bgovernment=", hb) and (wg == "none" or (governments is not None and wg not in governments)):
            for key, _, _ in items:
                res.skipped.append((key, h, f"the witness government {wg} is not defined in 1.21"))
            continue
        ids = " ".join(gi for _, gi, _ in items)
        at = lg[h].open + ld.end()
        inner = ld.group(1) + b"\t"
        add = b"\n" + inner + f"domain={{ {ids} }}".encode()
        if not re.search(rb"\bgovernment=", hb):
            add += b"\n" + inner + f"government={wg}".encode()
            back[h] = wg
        if not re.search(rb"\brealm_capital=", hb):
            rc = re.search(rb"\brealm_capital=(\d+)", witness[lw[h].open:lw[h].close]) if h in lw else None
            cap = rc.group(1).decode() if rc and rc.group(1).decode() in ids.split() else items[0][1]
            add += b"\n" + inner + f"realm_capital={cap}".encode()
        p.add(gs.Edit(at, at, add, "carry", f"{h} domain {ids}"))
        for key, gi, liege in items:
            gives.setdefault(liege, []).append(gi.encode())
            # the holder line of the title
            t = tg[gi]
            hm = _field(g[t.open:t.close], "holder")
            p.add(gs.Edit(t.open + hm.start(1), t.open + hm.end(1), h.encode(), "carry", f"{key} -> {h}"))
            pair = (back.get(h) or gov(h), gov(liege))
            lv = max(set(levels.get(pair, [])), key=levels.get(pair, []).count) if levels.get(pair) else None
            if lv is None:
                res.carried.append((key, h, liege, "no contract: the game writes none for " + "/".join(pair)))
                continue
            nc += 1
            rows.append(f"\t\t{nc}={{\n\t\t\tvassal={h}\n\t\t\tliege={liege}\n\t\t\tdate={_date(g)}\n"
                        f"\t\t\tliege_dynasty_date=1.1.1\n\t\t\t{lv}\n\t\t}}\n")
            lists.setdefault(liege, []).append(str(nc))
            res.carried.append((key, h, liege, lv))
    if not res.carried:
        return res
    for c in set(gives) | set(adds):                  # one edit per domain: what leaves and what joins
        cb = g[lg[c].open:lg[c].close]
        d = re.search(rb"\bdomain=\{([^}]*)\}", cb)
        if d:
            gone = set(gives.get(c, []))
            now = [x for x in d.group(1).split() if x not in gone]
            now += [x for x in adds.get(c, []) if x not in now]
            p.add(gs.Edit(lg[c].open + d.start(1), lg[c].open + d.end(1), b" " + b" ".join(now) + b" ", "carry",
                          f"{c} domain -{len(gone)} +{len(adds.get(c, []))}"))
    for liege, cids in lists.items():
        lb = g[lg[liege].open:lg[liege].close]
        vl = re.search(rb"\n(\s*)vassal_contracts=\{", lb)
        if vl:
            at = lg[liege].open + vl.end()
            p.add(gs.Edit(at, at, (" " + " ".join(cids)).encode(), "carry", f"{liege} contracts"))
        else:
            first = re.search(rb"\n(\s*)\S", lb)
            at = lg[liege].open + 1
            p.add(gs.Edit(at, at, b"\n" + first.group(1) + f"vassal_contracts={{ {' '.join(cids)} }}".encode(),
                          "carry", f"{liege} contracts (new list)"))
    out = p.apply(g)
    if rows:
        b = gs.locate(out, "vassal_contracts/database")
        out = out[:b.close] + "".join(rows).encode() + b"\t" + out[b.close:]
    res.gamestate = out
    return res


@dataclass
class TypesResult:
    gamestate: bytes
    typed: list = field(default_factory=list)         # (title key, type, why)
    unknown: list = field(default_factory=list)       # title keys left empty: no rule decides them


def _title_rows(g: bytes):
    """(title block, key, type or None, holder government) for every title of a 1.21 save."""
    L = _entries(g, "living")
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        if not e.key:
            continue
        head = g[e.open:min(e.close, e.open + 400)]
        k, t = re.search(rb'\bkey="?([\w\-\']+)', head), re.search(rb'\btype="?(\w*)"?', head)
        h = (_field(g[e.open:e.close], "holder") or [None, b""])[1].decode()
        yield e, (k.group(1).decode() if k else ""), (t.group(1).decode() if t else None), \
            (gov_of_landed(g, L[h]) if h in L else "")


def _pattern(key: str) -> str:
    return "_".join(key.split("_")[:2]) + "_"


def title_type_rules(ref: bytes, floor: int = 10) -> tuple[dict, dict]:
    """What decides a title's type in a game the game started itself (the 1.21 reference): a key pattern whose
    titles all share one type (c_nf_ -> noble family, 1,242 of 1,242), and a government whose titles all share one
    type other than the default (mercenary_government -> mercenary company, 553 of 553). Each needs ``floor`` cases."""
    by_pat, by_gov = {}, {}
    for _, k, t, gv in _title_rows(ref):
        if not t:
            continue
        by_pat.setdefault(_pattern(k), set()).add(t)
        by_pat.setdefault(("n", _pattern(k)), []).append(t)
        if gv:
            by_gov.setdefault(gv, []).append(t)
    pats = {p: next(iter(ts)) for p, ts in by_pat.items() if isinstance(p, str) and len(ts) == 1
            and len(by_pat[("n", p)]) >= floor}
    govs = {gv: ts[0] for gv, ts in by_gov.items() if len(set(ts)) == 1 and len(ts) >= floor
            and ts[0] != "title_type_default_static"}
    return pats, govs


def type_titles(g: bytes, ref: bytes) -> TypesResult:
    """Fill the title types the game's 1.21 conversion leaves empty (S8). In djdarcy's re-save of v17, 2,016 titles
    carry type="" that a fresh 1.21 game types: 1,138 Japanese noble families (c_nf_), 78 ecclesiastical (d_et_),
    64 landless adventurers (d_laamp_), 54 cardinals (d_cd_), and 679 old mercenary companies (x_mc_, typed by their
    holder's government). Only an empty type is filled; a title no rule decides is reported, never guessed."""
    res = TypesResult(g)
    pats, govs = title_type_rules(ref)
    p = gs.EditPass()
    for e, k, t, gv in _title_rows(g):
        if t != "":
            continue
        new, why = pats.get(_pattern(k)), f"key pattern {_pattern(k)}"
        if new is None and gv in govs:
            new, why = govs[gv], f"holder's government {gv}"
        if new is None:
            res.unknown.append(k)
            continue
        m = re.search(rb'\btype=(""|)(?=\s)', g[e.open:min(e.close, e.open + 400)])
        p.add(gs.Edit(e.open + m.start(1), e.open + m.end(1), new.encode(), "type", f"{k} -> {new}"))
        res.typed.append((k, new, why))
    if res.typed:
        res.gamestate = p.apply(g)
    return res


def carry_province_size(g: bytes, ref: bytes) -> tuple[bytes, list]:
    """Raise each province's size to the 1.21 reference's where the game's conversion left it lower (S6, unit 2).

    1.21 replaced the county's development with a province size (province_size_value = 100 x province_size_level),
    set from history (game/history/provinces) and read by buildings. The game's conversion of v17 put all 13,474
    provinces at level 1; a fresh 1.21 game on the same date has 547 above it (Rome, Constantinople and the like, up
    to level 9). Those 547 are raised to the reference's; a size is never lowered. Returns the edited gamestate and
    (province, old level, new level) for each raise.
    """
    def sizes(gg):
        out = {}
        for e in gs.iter_entries(gg, *gs.locate(gg, "provinces").body):
            if not (e.key and e.key.isdigit()):
                continue
            b = gg[e.open:e.close]
            v, lv = re.search(rb"\bprovince_size_value=([\d.]+)", b), re.search(rb"\bprovince_size_level=(\d+)", b)
            if v and lv:
                out[e.key.decode()] = (e, v, lv)
        return out
    mine, theirs = sizes(g), sizes(ref)
    p, raised = gs.EditPass(), []
    for k, (e, v, lv) in mine.items():
        if k not in theirs:
            continue
        _, rv, rlv = theirs[k]
        if int(rlv.group(1)) <= int(lv.group(1)):
            continue
        p.add(gs.Edit(e.open + v.start(1), e.open + v.end(1), rv.group(1), "size", f"{k} value"))
        p.add(gs.Edit(e.open + lv.start(1), e.open + lv.end(1), rlv.group(1), "size", f"{k} level"))
        raised.append((k, int(lv.group(1)), int(rlv.group(1))))
    return (p.apply(g) if raised else g), raised


def drop_empty_cooldowns(g: bytes) -> tuple[bytes, int]:
    """Remove the decision cooldowns the game's 1.21 conversion writes with an empty key (S8, a neutral nothing).

    In djdarcy's re-save of v17 the game wrote 2,187 entries like ``decision_cooldowns={ =978.3.5 }``. Each came from
    a cooldown v17 held for a decision that neither 1.20 nor 1.21 defines (all 2,182 matched by date:
    go_on_pilgrimage_decision 833, start_hunt_decision 389, playdate_decision 244, ...): 1.8-era decisions the game
    replaced with activities (1.21 has hunt, feast, pilgrimage and playdate activity types), carried in the founding
    save. 1.20 kept such cooldowns by name and ignored them; 1.21's conversion blanks the name, and each logs "Trying
    to set date from an empty string" on every load. A cooldown whose decision is gone does nothing, so dropping it
    changes no play. (Checked 2026-11-18 after djdarcy doubted "1.21 removed them": it did not. 1.21 defines 587
    decisions to 1.20's 501 and dropped only four development ones.)
    """
    p, n = gs.EditPass(), 0
    for m in re.finditer(rb"\bdecision_cooldowns=\{", g):
        end = gs.match_brace(g, m.end() - 1)
        for e in re.finditer(rb"\n[ \t]*=\d+\.\d+\.\d+(?=\s)", g[m.end():end]):
            p.add(gs.Edit(m.end() + e.start(), m.end() + e.end(), b"", "cooldowns", "empty-key cooldown"))
            n += 1
    return (p.apply(g) if n else g), n


def gov_of_landed(g: bytes, e: gs.Block) -> str:
    """The government= inside a character's landed_data (where 1.21 keeps it), or "none"."""
    body = g[e.open:e.close]
    ld = re.search(rb"\blanded_data=\{", body)
    if not ld:
        return "none"
    inner = body[ld.end():gs.match_brace(body, ld.end() - 1)]
    m = re.search(rb'\bgovernment="?(\w+)', inner)
    return m.group(1).decode() if m else "none"


def _date(g: bytes) -> str:
    m = re.search(rb"\bdate=(\d+\.\d+\.\d+)", g[:4096])
    return m.group(1).decode() if m else "1.1.1"


def _append(g: bytes, path: str, top: str, rows: str) -> bytes:
    """Rows at the end of ``path``'s body; the section is created at the end of the gamestate when absent."""
    try:
        b = gs.locate(g, path)
        return g[:b.close] + rows.encode() + b"\t" + g[b.close:]
    except gs.GamestateError:
        return g + f"{top}={{\n\tdatabase={{\n{rows}\t}}\n}}\n".encode()


# --------------------------------------------------------------------------------------------- innovations (F5)

ERAS = ("culture_era_tribal", "culture_era_early_medieval", "culture_era_high_medieval", "culture_era_late_medieval")


@dataclass
class InnovationsResult:
    gamestate: bytes
    missing: list = field(default_factory=list)       # innovation keys added to at least one culture
    added: int = 0                                    # entries written, over all cultures
    discovered: list = field(default_factory=list)    # (culture id, template, innovation) written with progress=100
    cultures: int = 0                                 # cultures that gained entries
    partial: list = field(default_factory=list)       # keys the reference lists on some cultures only: never spread (G1)


def _cultures(g: bytes):
    """(entry, template, era index reached, {innovation: progress or None}, (start, end) of culture_innovation's body)
    for every culture. An innovation is listed for every culture; ``progress=100`` marks it discovered."""
    for e in gs.iter_entries(g, *gs.locate(g, "culture_manager/cultures").body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        t = re.search(rb'culture_template="?([a-z_0-9]+)', b)
        era = -1
        ed = re.search(rb"culture_era_data=\{", b)
        if ed:
            body = b[ed.end():gs.match_brace(b, ed.end() - 1)]
            for m in re.finditer(rb'type="?(culture_era_[a-z_]+)"?\s*(?:progress=([\d.]+))?', body):   # 1.20 quotes
                if m.group(2) and float(m.group(2)) >= 100 and m.group(1).decode() in ERAS:
                    era = max(era, ERAS.index(m.group(1).decode()))
        inn, span = {}, None
        ci = re.search(rb"culture_innovation=\{", b)
        if ci:
            close = gs.match_brace(b, ci.end() - 1)
            # DLC innovations carry a prefix (fp3_innovation_fritware, fp3_innovation_mural_sextant): the pattern must
            # take any key ending in an innovation_ name, or those stay invisible (missed by R47 until 2026-11-20)
            for m in re.finditer(rb'\{\s*type="?([a-z0-9_]*innovation_[a-z_0-9]+)"?\s*(?:progress=([\d.]+))?',
                                 b[ci.end():close]):
                inn[m.group(1).decode()] = float(m.group(2)) if m.group(2) else None
            span = (e.open + ci.end(), e.open + close)
        yield e, (t.group(1).decode() if t else None), era, inn, span


def innovation_eras(game_dir) -> dict[str, str]:
    """innovation key -> its culture_era, from the game's common/culture/innovations."""
    from .host_rules import _blocks
    out = {}
    for f in sorted((_common(game_dir) / "culture" / "innovations").glob("*.txt")):
        for k, body, _ in _blocks(f):
            m = re.search(r"culture_era\s*=\s*(culture_era_\w+)", body)
            if "innovation_" in k and m:     # fp3_innovation_fritware too (2026-11-20)
                out[k] = m.group(1)
    return out


def insert_missing_innovations(g: bytes, ref: bytes, eras: dict[str, str]) -> InnovationsResult:
    """Give every culture each innovation the new version's own fresh game lists and that culture does not list.

    A fresh 1.21 game lists all 131 innovations for every culture; a culture researches only what it lists. The game's
    1.21 conversion of a 1.20 save leaves gaps: 18 innovations new in 1.21 (prospecting, coppicing, heavy plow,
    monasticism, ...) on all 284 cultures of the converted campaign, and 7 more (coat of plates, pole vault, glassmaking,
    ...) on 55 to 229 of them; two years of play added none (measure 2026-11-19, goal 22:43 S1). Written undiscovered
    into a copy, the 18 were researched in play: 678 culture entries in progress after two years, against 0.

    Each is written undiscovered (``{ type=X }``, the fresh game's own form), except where the evidence says the culture
    starts with it: the fresh game's culture of the same template has it discovered, and this culture has reached the
    innovation's era (12 entries on the founding campaign; djdarcy 2026-11-19: "Evidence, measured first"). An entry the
    culture already has is never altered, so a second run changes nothing.

    Shared by R47 (1.21, the 1.21 reference) and R49 (1.20, the 1.20 reference). Three guardrails (DWP
    2026-11-20__15-17-51), answering djdarcy's "I don't want innovations that are truly meant to be limited to cultures
    / religious groups / regions / etc to be applied universally": G1, only a key the reference lists on EVERY culture
    is spread (a key on some cultures only is left alone and reported in ``partial``; none in ref-1.20 or ref-1.21,
    measured 2026-11-20); G2, discovered only by the evidence above; G3, an existing entry is never touched."""
    ref_by_template = collections.defaultdict(set)
    lists = []
    for _, t, _, inn, span in _cultures(ref):
        if span is not None:
            lists.append(set(inn))
        ref_by_template[t].update(i for i, p in inn.items() if (p or 0) >= 100)
    fresh_all = set.intersection(*lists) if lists else set()         # G1
    partial = sorted(set().union(*lists) - fresh_all) if lists else []
    cults = list(_cultures(g))
    missing = sorted({i for _, _, _, inn, span in cults if span is not None for i in fresh_all - set(inn)})
    res = InnovationsResult(gamestate=g, missing=missing, partial=partial)
    if not missing:
        return res
    out, last = [], 0
    for e, t, era, inn, span in cults:
        here = sorted(fresh_all - set(inn))
        if span is None or not here:
            continue
        rows = []
        for i in here:
            era_ok = eras.get(i) in ERAS and era >= ERAS.index(eras[i])
            if i in ref_by_template.get(t, ()) and era_ok:
                rows.append(f" {{\n\t\t\t\t\ttype={i}\n\t\t\t\t\tprogress=100\n\t\t\t\t}}\n")
                res.discovered.append((e.key.decode(), t, i))
            else:
                rows.append(f" {{\n\t\t\t\t\ttype={i}\n\t\t\t\t}}\n")
        out.append(g[last:span[1]])
        out.append("".join(rows).encode())
        last = span[1]
        res.cultures += 1
        res.added += len(rows)
    out.append(g[last:])
    res.gamestate = b"".join(out)
    return res
