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
        for m in re.finditer(r"\b([cb]_[\w-]+)\s*=\s*\{", text):
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
    tkey = lambda gg, e: re.search(rb'\bkey="?([\w-]+)', gg[e.open:min(e.close, e.open + 400)])
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
        k, t = re.search(rb'\bkey="?([\w-]+)', head), re.search(rb'\btype="?(\w*)"?', head)
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
