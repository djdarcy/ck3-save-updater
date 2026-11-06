"""Transplant rules for 1.8.1 -> 1.20.1.2: bring 1.20's new map regions in from a reference save.

1.20 added 3,609 provinces and 5,655 titles (East and Southeast Asia, Tibet, Japan, ...) that a 1.8.1 save has
never heard of; loaded as is, every one of those titles is unheld and the engine hands them to the player. These
rules copy them from a save written by 1.20 at the campaign's date (the reference), with every id translated by
R13 (``translate.py``) and the campaign's own world left as it is.

The rules PLAN into one ``transplant.Transplant`` kept in ``ctx.state``; R17 writes the plan in one pass (the edge
policy must know every copied object before any reference is kept). Selecting R14, R15 or R16 brings R17 along.

* R14 new-titles: every reference title whose key the save does not have (runtime ``x_`` titles excepted), with
  the province entries of the provinces the save does not have. New titles under an existing parent are stitched
  into that parent's de jure list when R17 writes.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

from .. import translate as T
from ..transplant import TITLES, Transplant
from ..savefile import CK3Save
from .religion_1_20 import reference_gamestate

_HOLDING = re.compile(rb"holding=\{[^}]*?type=")     # a province entry that has a holding (1.8.1 or 1.20 form)

# Reference titles the engine is measured to create by itself in a migrated campaign, so a copy would duplicate it
# ("Duplicate landed title name", 2026-10-25). Measured key by key in the game's own saves of the migrated founding
# campaign at 990.1.1 and 1003.1.1: of the 340 titles 1.20 defines that the save lacked, only this one appeared. It
# is the save's own d_knights_hospitaler renamed on load by the game's common/landed_titles/title_conversion.lookup
# (same id, holder kept; measured on the game's re-save of play7, 2026-10-31; R6 reads the same file as
# "converted_by_game"), so carrying it would make a second one. Any other title a fresh game
# has is carried, empty if the fresh game has it empty (DWP 2026-10-27 05-49-04, option B; djdarcy: carry only
# what a fresh game has, as it has it).
ENGINE_CREATED = frozenset({"d_knights_hospitaller"})


def transplant_of(save: CK3Save, ctx) -> Transplant:
    """The context's shared transplant plan (built on first use, against the save as the earlier rules left it)."""
    if "transplant" not in ctx.state:
        ctx.state["transplant"] = Transplant(save.gamestate, reference_gamestate(ctx))
        ctx.state["transplant"].game_dir = ctx.game_dir   # attach_plan reads common/governments from it
    return ctx.state["transplant"]


def _skip(rule, why: str):
    return rule.result(extra={"skipped": why})


def r14_new_titles(save: CK3Save, ctx, rule):
    """Plan every reference title the save lacks (by key, runtime x_ titles excepted) and every reference
    province entry whose id the save lacks. Writes nothing; R17 does."""
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference): the new titles come from a 1.20 save")
    t = transplant_of(save, ctx)
    t.r15_kept = ctx.state.get("r15_kept", [])        # held titles R15 removed: their successors go to the holder
    save_keys = set(T.keyed(save.gamestate, TITLES))
    ref_keys = t.title_keys()
    new = {i for i, k in ref_keys.items() if k.encode() not in save_keys and not k.startswith("x_")}
    # every title a fresh 1.20 game has is carried, held or not: an unheld titular title (h_roman_empire, the
    # monastic orders, e_carthage ...) is how "not yet created, can be earned" is written, and the game's scripts
    # name them (2026-10-27: 252 of 323 named 845 times; the engine created 1 of them in 16 years of play). Only the
    # titles the engine is measured to create itself are left to it.
    engine = {i for i in new if ref_keys[i] in ENGINE_CREATED}
    held = t.title_holders(new)
    unheld_titular = {i for i in new - engine if ref_keys[i][0] in "dkeh" and i not in held
                      and not any(p.startswith("de_jure_vassals") for p, _, _ in
                                  t.references(TITLES, i, t.entries(TITLES)[i]))}
    # a holy order that leases campaign land: 1.20 does not add these to an old save by itself (two months of
    # play on the migrated save created none of the 12), so they are expansion content -- added "as is" with
    # their leases unless --no-expansion-orders, and reported either way
    join = t.tr.spaces["title"].join
    ho_campaign = {own for own, leased in t.holy_order_titles().values()
                   if own is not None and any(x in join for x in leased)}
    t.expansion_orders = ctx.expansion_orders
    new -= engine
    if not ctx.expansion_orders:
        new -= ho_campaign
    save_provinces = {i: e for i, e in T.entries(save.gamestate, "provinces")}
    provinces = set(t.entries("provinces")) - set(save_provinces)
    t.add("title", new, "R14")
    t.add("province", provinces, "R14")
    # ruling B (director 2026-10-26 13:3x): a copied barony on a province the campaign kept with NO holding gets
    # the reference's province entry (the copied holder had nothing to hold, and the engine strips him on load:
    # b_luoshan, province 8985). A campaign barony the campaign never built stays unbuilt, counted.
    unbuilt = 0
    if ctx.game_dir is not None:
        from .. import deadtitles as D
        _, prov_of = D.title_tree(ctx.game_dir / "common" / "landed_titles")
        new_baronies = {prov_of[ref_keys[i]] for i in new if ref_keys[i].startswith("b_") and ref_keys[i] in prov_of}
        refp = t.entries("provinces")
        for p, e in save_provinces.items():
            r = refp.get(p)
            if r is None or _HOLDING.search(save.gamestate[e.start:min(e.end, e.start + 1500)]) or \
                    not _HOLDING.search(t.ref[r.start:min(r.end, r.start + 1500)]):
                continue
            if p in new_baronies:
                t.fill_provinces.add(p)
            else:
                unbuilt += 1
    tiers = {}
    for i in new:
        tiers[ref_keys[i][0]] = tiers.get(ref_keys[i][0], 0) + 1
    return rule.result(matched=len(new) + len(provinces),
                       extra={"titles_planned": len(new), "by_tier": dict(sorted(tiers.items())),
                              "unheld_titular_carried": len(unheld_titular),
                              "left_to_the_engine": sorted(ref_keys[i] for i in engine),
                              "holy_order_titles_leasing_campaign_land": sorted(ref_keys[i] for i in ho_campaign),
                              "expansion_orders": "added" if ctx.expansion_orders else "left out",
                              "provinces_planned": len(provinces),
                              "provinces_given_a_holding": len(t.fill_provinces),
                              "unbuilt_in_the_campaign_built_in_a_fresh_1_20_game": unbuilt,
                              "x_titles_left_out": sum(1 for k in ref_keys.values() if k.startswith("x_"))})


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def save_version(save: CK3Save) -> tuple[int, ...] | None:
    """The game version a save says it was written by (meta_data ``version="1.8.1"``), as numbers."""
    from .. import gamestate as gs
    try:
        meta = gs.find_section(save.gamestate, "meta_data")
    except gs.GamestateError:
        return None
    for c in gs.iter_children(save.gamestate, *meta.body):
        if c.key == b"version" and c.value_start is not None:
            return _version_tuple(save.gamestate[c.value_start:c.value_end].decode("ascii", "replace")) or None
    return None


def r15_dead_titles(save: CK3Save, ctx, rule):
    """Settle the save's titles the target no longer defines, and its moved baronies, by place: a clean mapping
    renames the save's title to its successor (id and holder kept); any other is removed with every reference
    to it, and the reference's titles for that land come in through R14. Runs before R14, edits the save at
    once so the joins see the new keys, and leaves its table in ctx.state for the report."""
    from .. import deadtitles as D
    from .. import gamestate as gs
    from ..lint import defined_title_keys
    # S11 (measured 2026-10-26): the mapping comes from the two maps' files, which still differ on a save that is
    # already on the target map; re-run on the founding save's migrated output, R15 swapped b_darlington and
    # b_hartlepool back and removed 8 moved baronies. A save already at the target version is on the target map.
    have = save_version(save)
    if have is not None and have >= _version_tuple(ctx.target_version):
        return _skip(rule, f"the save is already at {'.'.join(map(str, have))} (the target map); nothing to settle")
    if ctx.old_game_dir is None or ctx.game_dir is None:
        return _skip(rule, "needs --old-game-dir (the save's own version's game folder) and --game-dir")
    _, conversion = defined_title_keys(ctx.game_dir)
    maps = D.classify(save.gamestate, ctx.old_game_dir / "common" / "landed_titles",
                      ctx.game_dir / "common" / "landed_titles", set(conversion))
    # djdarcy 2026-10-27 (~06:30): "any titles that were in play that are still existent in the game that were
    # present in our original game should be upgraded if possible so the correct holder still has their title."
    # A held title R15 removes because 1.20 split or redrew its land: its successors go to the campaign holder
    # (the transplant does it, Transplant.holdings_plan). Recorded here, before the removal, with the title's old
    # de facto liege (by key), which the removal strips.
    blocks = dict(T.entries(save.gamestate, TITLES))
    key_of = {i: (k.decode() if (k := T._depth0(save.gamestate, e, T._KEY)) else "") for i, e in blocks.items()}
    kept = []
    for m in maps:
        if m.holder is None or m.cls != "unclean" or not m.successors:
            continue
        e = blocks[m.save_id]
        df = re.search(rb"\n\tde_facto_liege=(\d+)", save.gamestate[e.open:min(e.close, e.open + 4096)])
        kept.append({"key": m.key, "holder": m.holder, "successors": list(m.successors), "id": m.save_id,
                     "old_liege_key": key_of.get(int(df.group(1))) if df else None})
    ctx.state["r15_kept"] = kept
    ep = gs.EditPass()
    applied = D.apply(save.gamestate, maps, ep)
    ep.apply_to(save)
    ctx.state["dead_titles"] = maps
    by = {}
    for m in maps:
        by[f"{m.kind} {m.cls}"] = by.get(f"{m.kind} {m.cls}", 0) + 1
    return rule.result(matched=len(maps), edited=len(ep.edits),
                       extra={"by_class": by, "renamed": applied.renamed, "removed": applied.removed,
                              "references_removed": dict(applied.references_removed),
                              "table": [m.row() for m in maps]})


def r16_people(save: CK3Save, ctx, rule):
    """Plan the people the planned titles need: their holders, the holders' courtiers, and the close family of
    both (one hop, living and dead). History characters the campaign already has stay the campaign's (joined:
    the reference's references to them are redirected, nothing of the reference is written into them)."""
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference): the people come from a 1.20 save")
    t = transplant_of(save, ctx)
    holders = t.title_holders(t.carry["title"])
    rulers = set(holders.values())
    # displaced (design ruling 06:58): a reference ruler whose every title went to a campaign holder through a
    # clean R15 rename comes in landless, in the court of that campaign holder, with their own dependants
    taker: dict[int, int] = {}
    displaced_rows = []
    ref_ids = {k: i for i, k in t.title_keys().items()}
    taken: dict[int, set[int]] = {}
    for m in ctx.state.get("dead_titles", []):
        if m.cls != "clean" or m.holder is None:
            continue
        rid = ref_ids.get(m.successors[0])
        h = t.title_holders([rid]).get(rid) if rid is not None else None
        if h is not None:
            taken.setdefault(h, set()).add(rid)
            taker.setdefault(h, m.holder)
    all_held = t.title_holders(t.entries(TITLES))
    for h, rids in taken.items():
        own = {i for i, x in all_held.items() if x == h}
        if own <= rids and h not in rulers and h not in t.tr.spaces["character"].join:
            t.employer[h] = taker[h]
            displaced_rows.append({"reference_character": h, "court_of": taker[h],
                                   "titles_taken": sorted(t.title_keys()[i] for i in rids)})
    c = t.people_closure(rulers | set(t.employer))
    people = c["rulers"] | c["courtiers"] | c["family"]
    joined = {p for p in people if p in t.tr.spaces["character"].join}
    t.add("character", people, "R16")
    # Unit 5b (director, 2026-10-25): every culture template the save lacks (not only the closure's), and
    # China's system state -- the situations, which bring their sub-regions and participant groups
    t.add("culture", set(t.entries("culture_manager/cultures")), "R16")
    # only the situation types the save lacks (S11, measured 2026-10-26: re-run on the founding save's migrated
    # output, R16 planned all 4 again, and R17 inserted them a second time with their 11 sub-regions and 55
    # groups; cultures are safe, they join by template)
    def sit_type(g, e):
        m = re.search(rb"\n\t+type=\"?(\w+)", g[e.start:min(e.end, e.start + 2000)])
        return m.group(1) if m else None
    try:
        have = {sit_type(save.gamestate, e) for _, e in T.entries(save.gamestate, "situation_manager/database")}
    except T.TranslationError:
        have = set()
    t.add("situation", {i for i, e in t.entries("situation_manager/database").items()
                        if sit_type(t.ref, e) not in have}, "R16")
    dead = sum(1 for p in people - joined if t.character(p)[0] == "dead_unprunable")
    # history ids the campaign holds for a different person (translate.implausible_join): such a reference person
    # is copied, not joined; listed so a reader can see who would otherwise have been merged with whom
    refused = [{"history_id": h, "reference_character": r, "campaign_character": s, "why": why}
               for r, (h, s, why) in sorted(t.tr.spaces["character"].join_rejected.items())]
    return rule.result(matched=len(people - joined),
                       extra={"titles_with_a_holder": len(holders), "rulers": len(rulers),
                              "displaced_landless": len(t.employer), "displaced": displaced_rows,
                              "courtiers": len(c["courtiers"]), "family": len(c["family"]),
                              "left_to_the_campaign": len(joined), "dead": dead,
                              "history_ids_not_joined": refused})


def r17_transplant_write(save: CK3Save, ctx, rule):
    """Write the transplant plan in one pass: carried objects closed, entries rewritten with the edge policy and
    inserted at column 0, seams stitched, the coat counter raised, lookups extended."""
    t = ctx.state.get("transplant")
    if t is None:
        # S2: name only the rules that plan a write; R15 renames titles in place and plans nothing for R17
        return _skip(rule, "nothing planned: R14 (titles, provinces) and R16 (people) plan what this rule writes")
    ep = t.edits()
    ep.apply_to(save)
    # the characters the transplant added (output ids): R19 reads their faces in the reference save's layout
    cm = t.tr.spaces["character"]
    ctx.state["transplanted_characters"] = {str(cm.translate(i)) for i in t.carry["character"] if i not in cm.join}
    rep = t.report.as_dict()
    rep["kept_scopes_remapped"] = _remap_kept_scopes(save, t)
    rep["holy_sites"] = _reattach_holy_sites(save, ctx)
    # R8 reported these as lost before the transplant existed; the report moves them to "recovered" (#6)
    rep["recovered"] = [{"what": "holy_site_barony", "index": i} for i in rep["holy_sites"].pop("reattached_indices")]
    rep["lock_step"] = _lock_step(save, ctx)
    return rule.result(matched=sum(t.report.inserted.values()), edited=len(ep.edits), extra=rep)


def _contract_groups(game_dir) -> dict[bytes, bytes]:
    """government -> the vassal contract group its vassals get (common/governments, vassal_contract_group)."""
    from .. import gamestate as gs
    out: dict[bytes, bytes] = {}
    base = Path(game_dir) / "common" / "governments" if game_dir else None
    for f in sorted(base.glob("*.txt")) if base is not None and base.is_dir() else []:
        t = re.sub(rb"#[^\n]*", b"", f.read_bytes().removeprefix(b"\xef\xbb\xbf"))
        for m in re.finditer(rb"(?m)^(\w+_government)\s*=\s*\{", t):
            try:
                body = t[m.end() - 1:gs.match_brace(t, m.end() - 1)]
            except gs.GamestateError:
                continue
            g = re.search(rb"vassal_contract_group\s*=\s*(\w+)", body)
            if g:
                out[m.group(1)] = g.group(1)
    return out


def _lock_step(save: CK3Save, ctx, characters: set[int] | None = None, only: set[str] | None = None,
               tag: str = "R17") -> dict:
    """Every character the transplant copied in has a title liege and a vassal contract that agree (djdarcy
    2026-11-05: "We do want to get to 100%"; a disagreement is the play5 crash class). For each copied ruler, his
    primary title's de facto liege is the title side, his contract the other:
    - both, naming different people: the contract follows the title (a baron answers to his county's holder);
    - a contract only: the title follows the contract's liege where that liege rules, else the contract goes;
    - a title liege only: a contract is written, in a free slot, with his government's contract group.
    A tributary contract (``tributary_*``) is a contract without a title liege by design, and is left alone, as are
    the campaign's own characters (R31 is theirs).

    ``characters`` (default: the copied ones) and ``only`` (default: every case; the cases are "disagree",
    "contract only", "title only") let R31 run the title-only case for the campaign's rulers; ``tag`` names the
    rule on the edits. A character filed among the living with ``dead_data`` (the game moves him to the dead on
    load), or whose first domain entry another character holds (a stale list), is never touched."""
    from .. import gamestate as gs
    from .. import translate as T
    from ..transplant import _edit_landed_list
    copied = characters if characters is not None else {int(c) for c in ctx.state.get("transplanted_characters", ())}
    g = save.gamestate
    titles = {}
    for i, e in T.entries(g, TITLES):
        b = g[e.open:min(e.close, e.open + 4096)]
        titles[i] = tuple(int(m.group(1)) if (m := re.search(rb"\n\t" + f + rb"=(\d+)", b)) else None
                          for f in (b"holder", b"de_facto_liege")) + (
            (m.group(1) if (m := re.search(rb'\n\tkey="?([\w-]+)', b)) else b""),)
    chars = dict(T.entries(g, "living"))
    path = None
    for p in ("vassal_contracts/active", "vassal_contracts/database"):
        try:
            gs.locate(g, p)
            path = p
            break
        except gs.GamestateError:
            continue
    if path is None:
        return {}
    contracts, used = {}, set()
    for i, e in T.entries(g, path):
        b = g[e.open:e.close]
        used.add(i)
        v, lg = re.search(rb"\n\t+vassal=(\d+)", b), re.search(rb"\n\t+liege=(\d+)", b)
        grp = re.search(rb"\n\t+contract_group=(\w+)", b)
        if v and lg:
            contracts[int(v.group(1))] = (i, int(lg.group(1)), grp.group(1) if grp else b"", e)

    def domain(c):
        e = chars.get(c)
        d = re.search(rb"\n\t\tdomain=\{([^}]*)\}", g[e.start:e.end]) if e is not None else None
        return [int(x) for x in d.group(1).split()] if d else []

    def gov(c):
        e = chars.get(c)
        m = re.search(rb'\n\t+government="?(\w+)', g[e.start:e.end]) if e is not None else None
        return m.group(1) if m else b""

    def listed(c):
        e = chars.get(c)
        m = re.search(rb"\n\t\tvassal_contracts=\{([^}]*)\}", g[e.start:e.end]) if e is not None else None
        return {int(x) for x in m.group(1).split()} if m else set()

    groups = _contract_groups(ctx.game_dir)
    dm = re.search(rb"(?m)^date=([\d.]+)", g)
    date = dm.group(1).decode() if dm else "1.1.1"
    nxt = max((T.index(i) for i in used), default=0) + 1          # a free slot (see transplant: shared slots crash)
    ep, rows = gs.EditPass(), Counter()
    ops: dict[int, dict] = defaultdict(lambda: {"add": [], "drop": set()})
    stitles = dict(T.entries(g, TITLES))
    created = []
    def dead(c):
        e = chars.get(c)
        return e is not None and b"dead_data={" in g[e.start:e.end]

    for c in sorted(copied):
        dom = domain(c)
        if not dom or dead(c):
            continue
        p = dom[0]
        holder, tl, key = titles.get(p, (None, None, b""))
        if holder != c:
            continue                                  # a stale domain list: the title is someone else's
        th = titles.get(tl, (None, None, b""))[0] if tl is not None else None
        th = None if th == c else th
        ct = contracts.get(c)
        if ct is not None and ct[2].startswith(b"tributary"):
            continue
        case = ("disagree" if th is not None and ct is not None and th != ct[1] else
                "contract only" if th is None and ct is not None else
                "title only" if th is not None and ct is None else None)
        if only is not None and case not in only:
            continue
        if th is not None and ct is not None:
            if th == ct[1]:
                if ct[0] not in listed(th):
                    ops[th]["add"].append(ct[0])
                    rows["contract added to its liege's list"] += 1
                continue
            m = re.search(rb"(\n\t+liege=)(\d+)", g[ct[3].open:ct[3].close])
            ep.add(gs.Edit(ct[3].open + m.start(2), ct[3].open + m.end(2), str(th).encode(), tag, "lock-step"))
            ops[ct[1]]["drop"].add(ct[0])
            ops[th]["add"].append(ct[0])
            rows["contract follows the title's liege"] += 1
        elif ct is not None:
            ldom = domain(ct[1])
            e = stitles.get(p)
            if ldom and not key.startswith(b"b_") and e is not None:
                m = re.search(rb"(\n\tde_facto_liege=)(\d+)", g[e.open:e.close])
                if m:
                    ep.add(gs.Edit(e.open + m.start(2), e.open + m.end(2), str(ldom[0]).encode(), tag, "lock-step"))
                else:
                    at = g.rfind(b"\n", 0, e.close) + 1
                    ep.add(gs.Edit(at, at, f"\tde_facto_liege={ldom[0]}\n".encode(), tag, "lock-step"))
                if ct[0] not in listed(ct[1]):
                    ops[ct[1]]["add"].append(ct[0])
                rows["title follows the contract's liege"] += 1
            else:
                a, b = gs.removal_span(g, ct[3].start, ct[3].end)
                ep.add(gs.Edit(a, b, b"", tag, "lock-step"))
                ops[ct[1]]["drop"].add(ct[0])
                rows["contract removed: its liege rules nothing"] += 1
        elif th is not None:
            grp = groups.get(gov(c))
            created.append(f"{nxt}={{\n\t\t\tvassal={c}\n\t\t\tliege={th}\n\t\t\tdate={date}\n\t\t\tlevels={{ 1 }}\n"
                           + (f"\t\t\tcontract_group={grp.decode()}\n" if grp else "") + "\t\t}\n")
            ops[th]["add"].append(nxt)
            nxt += 1
            rows["contract written for a title liege"] += 1
    if created:
        sec = gs.locate(g, path)
        at = g.rfind(b"\n", 0, sec.close) + 1
        ep.add(gs.Edit(at, at, "".join(created).encode(), tag, "lock-step contracts"))
    for c, op in ops.items():
        e = chars.get(c)
        if e is None:
            continue
        text = g[e.start:e.end]
        new = _edit_landed_list(text, b"vassal_contracts", add=op["add"], drop=op["drop"])
        if new != text:
            ep.add(gs.Edit(e.start, e.end, new, tag, "lock-step lists"))
    ep.apply_to(save)
    return dict(rows)


_LT_SCOPE = re.compile(rb"(type=lt\s+identity=)(\d+)")


def _remap_kept_scopes(save: CK3Save, t) -> dict:
    """Stored title scopes (``type=lt identity=<id>``: character variables, lists, event scopes) that named a held
    title R15 removed now name its successor, the one its holder regained (else the first successor the output
    has). 2026-10-27: the hand-back left 113 such scopes dangling on the founding campaign (``title1``..,
    ``chronicle_primary_title``), read by no script in the 1.20 playset but by mods the campaign used; djdarcy:
    "if it does make sense for us to remap to keep events active that were active before it might be worth a check
    to see if we can migrate successfully so we don't break old quests". Only ids that name no title in the output
    are touched, so a live title's id is never rewritten."""
    remap = t.kept_scope_remap()
    if not remap:
        return {"scopes": 0, "titles": {}}
    g = save.gamestate
    live = {i for i, _ in T.entries(g, TITLES)}
    hits: dict[str, int] = {}

    def sub(m: re.Match) -> bytes:
        i = int(m.group(2))
        if i in live or i not in remap:
            return m.group(0)
        new, key = remap[i]
        hits[key] = hits.get(key, 0) + 1
        return m.group(1) + str(new).encode()

    out = _LT_SCOPE.sub(sub, g)
    if hits:
        save.set_gamestate(out)
    return {"scopes": sum(hits.values()), "titles": hits}


def _reattach_holy_sites(save: CK3Save, ctx) -> dict:
    """R8 copies 1.20's holy sites before the transplant exists, so a site on a barony the save did not have yet
    (Angkor, Borobudur, Samarkand, ...) loses its barony and goes inactive. Now that R17 has written the new
    baronies, give each such site its barony back by key, with the reference's is_active."""
    from .. import gamestate as gs
    pending = ctx.state.get("holy_sites_without_barony", [])
    if not pending:
        return {"reattached": 0, "still_without_barony": [], "reattached_indices": []}
    g = save.gamestate
    ids = {k.decode(): i for k, i in T.keyed(g, TITLES).items()}
    sites = dict(T.entries(g, "religion/holy_sites"))
    ep = gs.EditPass()
    done, missing = [], []
    for s in pending:
        e, bid = sites.get(int(s["index"])), ids.get(s["barony"] or "")
        if e is None or bid is None:
            missing.append(s["barony"])
            continue
        kids = list(gs.iter_children(g, e.open + 1, e.close))
        if any(c.key == b"barony" for c in kids):
            continue
        act = next((c for c in kids if c.key == b"is_active" and c.block is None), None)
        if act is not None and s["is_active"]:
            ep.add(gs.Edit(act.value_start, act.value_end, s["is_active"].encode(), "R17", "holy site is_active"))
        at = g.rfind(b"\n", 0, e.close) + 1
        indent = re.match(rb"[\t ]*", g[at:]).group() or b"\t\t"
        ep.add(gs.Edit(at, at, indent + b"\t" + f"barony={bid}\n".encode(), "R17", "holy site barony"))
        done.append(s["index"])
    ep.apply_to(save)
    return {"reattached": len(done), "still_without_barony": sorted(x for x in missing if x),
            "reattached_indices": done}


from . import Rule  # noqa: E402  (Rule is defined before this module is imported)

RULES = [
    Rule("R14", "new-titles", "1.13 to 1.20 (map rework: East Asia, Tibet, ...)",
         "plan the titles and provinces the save does not have, from a 1.20 reference save", r14_new_titles,
         default=False, requires=("R8",)),
    Rule("R15", "dead-titles", "1.13 to 1.20 (titles the map rework removed or moved)",
         "rename the save's dead and moved titles to their 1.20 successors where the mapping is clean; remove "
         "the rest (split, wasteland, dropped), reported", r15_dead_titles, default=False,
         requires=("R14", "R16")),
    Rule("R16", "people", "1.13 to 1.20 (the new regions' rulers, courts and families)",
         "plan the holders of the planned titles, their courts and close family, from a 1.20 reference save",
         r16_people, default=False, requires=("R8", "R14")),
    Rule("R17", "transplant-write", "1.20",
         "write everything R14-R16 planned, ids translated, references outside the output dropped, seams "
         "stitched", r17_transplant_write, default=False),
]
