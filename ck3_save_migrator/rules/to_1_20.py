"""Subtractive rules (and the version bump) for bringing a 1.8.1 save to CK3 1.20.1.2.

Each rule cites the measurement it rests on. "1.8.1 save" = the Beidh 987.10.27
save; "1.20 reference" = ref_1_20_persia_867, a fresh 1.20.1.2 manual save.
"""

from __future__ import annotations

import base64
import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .. import gamestate as gs
from ..savefile import CK3Save

UNKNOWN_SINCE = "1.8.1<v<=1.20.1.2"

# 1.20 reference: 468 of 468 scripted_relations flags are 1 byte ("AA=="); 1.8.1 writes 4 ("AAAAAA==").
TARGET_FLAG_BYTES = 1

# 1.20 reference: title_name_data children appear in this order (name, article, adj, pre).
TITLE_NAME_KEYS = (b"name", b"article", b"adj", b"pre")


def _opinion_entries(data: bytes):
    try:
        ao = gs.locate(data, "opinions/active_opinions")
    except gs.GamestateError:
        return
    yield from gs.iter_entries(data, *ao.body)


# --------------------------------------------------------------------------- R2
def _relation_flags(d: bytes):
    """Every scripted_relations/<kind>/flags value: (kind, the value's key block, its raw bytes, its decoded bits or
    None when it is not base64). R2 and its detector read the same matches."""
    for e in _opinion_entries(d):
        for sr in gs.find_keys(d, e, "scripted_relations"):
            if sr.block is None:
                continue
            for kind in gs.iter_children(d, *sr.block.body):
                if kind.block is None:
                    continue
                for f in gs.find_keys(d, kind.block, "flags"):
                    raw = d[f.value_start:f.value_end]
                    try:
                        bits = base64.b64decode(raw.strip(b'"'), validate=True)
                    except ValueError:
                        bits = None
                    yield kind, f, raw, bits


def _r2_would_edit(bits) -> bool:
    return bits is not None and len(bits) != TARGET_FLAG_BYTES and not any(bits[TARGET_FLAG_BYTES:])


def r2_detect(d: bytes) -> tuple[int, list[str]]:
    """Read only: the flags bitsets wider than 1.20's 1 byte that R2 re-encodes (its edits), and up to five."""
    hits = [f"{kind.key.decode()} flags={raw.decode(errors='replace')}" for kind, _, raw, bits in _relation_flags(d)
            if _r2_would_edit(bits)]
    return len(hits), hits[:5]


def r2_relation_flags(save: CK3Save, ctx, rule) -> object:
    """Re-encode scripted_relations/<kind>/flags bitsets from 4 bytes to 1.20's 1 byte.

    1.8.1 save: 48,357 flags, all 4 bytes; non-zero values use only the low byte
    (AQAAAA== 437, AgAAAA== 51, AwAAAA== 41), so truncation is lossless. A value
    with a non-zero high byte is left unchanged and reported.
    """
    d = save.gamestate
    p = gs.EditPass()
    values: Counter = Counter()
    lossy: list[dict] = []
    for kind, f, raw, bits in _relation_flags(d):
        if bits is None:
            lossy.append({"offset": f.value_start, "value": raw.decode(errors="replace"), "why": "not base64"})
            continue
        p.count(rule.name).matched += 1
        values[raw.decode()] += 1
        if len(bits) == TARGET_FLAG_BYTES:
            continue
        if not _r2_would_edit(bits):
            lossy.append({"offset": f.value_start, "value": raw.decode(), "kind": kind.key.decode(),
                          "why": "high bytes set"})
            continue
        new = b'"' + base64.b64encode(bits[:TARGET_FLAG_BYTES]) + b'"'
        p.add(gs.Edit(f.value_start, f.value_end, new, rule.name))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"values": dict(values.most_common()), "left_unchanged": lossy})


# --------------------------------------------------------------------------- R3
def _unquote(raw: bytes) -> str:
    s = raw.decode("utf-8", errors="replace")
    if len(s) >= 2 and s[0] == s[-1] == '"':
        s = s[1:-1].replace('\\"', '"')
    return s


def r3_title_names(save: CK3Save, ctx, rule) -> object:
    """Move each title's inline name/adj/pre/article into title_name_data={...} after coat_of_arms_id.

    1.8.1 save: 12,702 titles, name 12,702, adj 3,508, article 45, pre 43; the 1.20
    parser rejects all four inline keys. 1.20 reference: every title has
    title_name_data, always right after coat_of_arms_id, children in the order
    name, article, adj, pre (title_history_names only on 27%, so not written).
    """
    d = save.gamestate
    p = gs.EditPass()
    side: dict[str, dict] = {}
    try:
        lt = gs.locate(d, "landed_titles/landed_titles")
    except gs.GamestateError:
        return rule.result()
    for t in gs.iter_entries(d, *lt.body):
        kids = list(gs.iter_children(d, *t.body))
        names = {c.key: c for c in kids if c.key in TITLE_NAME_KEYS}
        if not names:
            continue
        if any(c.block is not None for c in names.values()):
            continue                                    # already a block form; not ours to move
        p.count(rule.name).matched += 1
        anchor = next((c for c in kids if c.key == b"coat_of_arms_id"), None) or names[min(names, key=lambda k: names[k].start)]
        line_start = d.rfind(b"\n", 0, anchor.start) + 1
        indent = d[line_start:anchor.start]
        if indent.strip(b" \t"):
            indent = b"\t"
        body = b"".join(indent + b"\t" + k + b"=" + d[names[k].value_start:names[k].value_end] + b"\n"
                        for k in TITLE_NAME_KEYS if k in names)
        block = indent + b"title_name_data={\n" + body + indent + b"}\n"
        if anchor.key == b"coat_of_arms_id":
            nl = d.find(b"\n", anchor.end)
            at = len(d) if nl < 0 else nl + 1
        else:
            at = line_start
        p.add(gs.Edit(at, at, block, rule.name, "title_name_data"))
        for c in names.values():
            s, e = gs.removal_span(d, c.start, c.end)
            p.add(gs.Edit(s, e, b"", rule.name, c.key.decode()))
        key_child = next((c for c in kids if c.key == b"key"), None)
        tkey = _unquote(d[key_child.value_start:key_child.value_end]) if key_child else f"id:{t.key.decode()}"
        side[tkey] = {k.decode(): _unquote(d[c.value_start:c.value_end]) for k, c in names.items()}
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited, extra={"titles_touched": c.matched, "names": side})


# --------------------------------------------------------------------------- R21
DEAD_SECTIONS = ("dead_unprunable", "characters/dead_prunable")
_DEAD_LIEGE = re.compile(rb"[\n\t ]liege=(\d+)")


def dead_lieges(d: bytes) -> dict[int, tuple[int, int]]:
    """dead character id -> (liege id, offset of the character's "{"), read from each dead_data block."""
    out = {}
    for path in DEAD_SECTIONS:
        try:
            sec = gs.locate(d, path)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(d, *sec.body):
            if not (e.key and e.key.isdigit()):
                continue
            at = d.find(b"dead_data={", e.open, e.close)
            if at < 0:
                continue
            close = gs.match_brace(d, at + len(b"dead_data="))
            m = _DEAD_LIEGE.search(d, at, close)
            if m:
                out[int(e.key)] = (int(m.group(1)), e.open)
    return out


def _r21_members(d: bytes) -> tuple[dict, list[int]]:
    """The dead characters' lieges, and the members of every liege cycle of two or more (what R21 matches)."""
    lieges = dead_lieges(d)
    parent = {c: l for c, (l, _) in lieges.items() if l != c and l in lieges}
    return lieges, [c for cyc in gs.parent_cycles(parent) if len(cyc) > 1 for c in cyc]


def r21_detect(d: bytes) -> tuple[int, list[str]]:
    """Read only: the dead characters on a liege cycle that R21 breaks, and up to five."""
    lieges, members = _r21_members(d)
    return len(members), [f"character {c} (liege {lieges[c][0]})" for c in members[:5]]


def r21_dead_liege_cycles(save: CK3Save, ctx, rule) -> object:
    """Drop liege=/liege_title= from the dead_data of every dead character on a liege cycle of two or more.

    1.8.1 save: one cycle, Al-Mansur (2974, d. 775) -> Al-Mahdi (3595, d. 785) -> Al-Mansur, written by the 1.8.1
    game's history setup (both were independent caliphs). The 1.20 game writes a dead independent ruler as his
    own liege (3,513 such in its own 989 autosave) and never a longer loop; a fresh 1.20 game records no liege for
    them at all. A walk up a liege chain ends only where the chain ends (djdarcy, 2026-10-27: fix it in case some
    part of the game walks the history graph). Self-lieges are left as the game writes them.
    """
    d = save.gamestate
    lieges, members = _r21_members(d)
    p = gs.EditPass()
    for c in members:
        p.count(rule.name).matched += 1
        op = lieges[c][1]
        entry = gs.Block(str(c).encode(), op, op, gs.match_brace(d, op))
        dd = gs.find_child(d, entry, "dead_data")
        p.delete_key(d, dd, "liege", rule.name, str(c))
        p.delete_key(d, dd, "liege_title", rule.name, str(c))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited, extra={"characters": sorted(members)})


# --------------------------------------------------------------------------- R20
_AI_FIELD = {k: re.compile(rb"[\n\t ]" + k + rb"=(\S+)") for k in (b"war_stance", b"supply_limit", b"war_coordinator")}
_WAR_PLANS = re.compile(rb"war_plans=\{([^{}]*)\}")


def unrun_war_coordinator(body: bytes) -> bool:
    """True for an AI war coordinator that was created and never run: no war_stance, or a supply limit of 0.
    The 1.20 game writes neither (0 of 204 and 214 coordinators in its own autosaves; lowest supply limit 1000)."""
    sl = _AI_FIELD[b"supply_limit"].search(body)
    return _AI_FIELD[b"war_stance"].search(body) is None or (sl is not None and float(sl.group(1)) <= 0)


def r20_unrun_war_coordinators(save: CK3Save, ctx, rule) -> object:
    """Delete AI war coordinators that were created and never run, and the war plans that name them.

    1.8.1 save: 6 of 172 coordinators with no war_stance and supply_limit=0 (garrison_limit and stack_size 0, every
    update tick 0); 1.20 writes none. 1.20 loads them and never computes their stance or limits; when armies are
    assigned to one, the AI's unit stack splits its groups to stay under a supply limit of 0, one new group per pass
    without end (ck3+0x19f93e0 reads the coordinator's +0x78, which its loader fills from supply_limit; the 20 March
    989 / 990 stops: 265 million groups, 130 GB). Each is named by exactly one war plan (ai/war_plan_db). The game
    builds coordinators and plans for wars itself.
    """
    d = save.gamestate
    p = gs.EditPass()
    unrun = set()
    try:
        db, plans = gs.locate(d, "ai/war_coordinator_db"), gs.locate(d, "ai/war_plan_db")
    except gs.GamestateError:
        return rule.result(matched=0, edited=0)
    for e in gs.iter_entries(d, *db.body):
        if e.key and unrun_war_coordinator(d[e.open:e.close]):
            unrun.add(e.key)
            p.count(rule.name).matched += 1
            p.delete_block(d, e, rule.name, "coordinator " + e.key.decode())
    dropped_plans = set()
    for e in gs.iter_entries(d, *plans.body):
        wc = _AI_FIELD[b"war_coordinator"].search(d, e.open, e.close)
        if e.key and wc and wc.group(1) in unrun:
            dropped_plans.add(e.key)
            p.delete_block(d, e, rule.name, "war plan " + e.key.decode())
    # each plan is also listed by its owner's AI strategy (ai/ai_strategies/<char>/advanced_ai_data/war_plans); a
    # dangling id there crashes the load (2026-10-27, measured). 1.20 never writes an empty list (0 of 310), and
    # leaves the key out when there is none, so a list that empties goes too.
    lists = 0
    try:
        st = gs.locate(d, "ai/ai_strategies")
    except gs.GamestateError:
        st = None
    if st is not None and dropped_plans:
        for m in _WAR_PLANS.finditer(d, st.open, st.close):
            ids = m.group(1).split()
            kept = [i for i in ids if i not in dropped_plans]
            if len(kept) == len(ids):
                continue
            lists += 1
            if kept:
                p.add(gs.Edit(m.start(1), m.end(1), b" " + b" ".join(kept) + b" ", rule.name, "strategy war_plans"))
            else:
                s, e = gs.removal_span(d, m.start(), m.end())
                p.add(gs.Edit(s, e, b"", rule.name, "strategy war_plans emptied"))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"coordinators": sorted(int(k) for k in unrun),
                              "war_plans": sorted(int(k) for k in dropped_plans), "strategy_lists": lists})


# --------------------------------------------------------------------------- R22
_UNIT_LOC = re.compile(rb"\n\t+location=(\d+)")
_UNIT_PREV = re.compile(rb"\n\t+prev=(\d+)")
_UNIT_MOVE = re.compile(rb"\n\t+(?:path=\{[^}]*\}|total_cost=[\d.]+|movement_progress=[\d.]+)")


_POOL_REF = re.compile(rb"\n\t+(?:levy|garrison)=(\d+)")
_TASK_TARGET = re.compile(rb"\n\t+target=\{\s*type=prov\s+identity=(\d+)")
_TITLE_KEY_LINE = re.compile(rb"(?m)^(\d+)=\{\n\tkey=\"?([\w\-']+)")
_CHUNK_POOL = re.compile(rb"[\n\t ]regiment=(\d+)")


def _locate_or_none(d: bytes, path: str):
    try:
        return gs.locate(d, path)
    except gs.GamestateError:
        return None


def r22_impassable_provinces(save: CK3Save, ctx, rule) -> object:
    """Clear what the old map left on provinces the target map makes impassable.

    1.20's map rework made 1.8.1 land impassable (1,204 provinces; 9542 and 9532 in the Ordos among them). A 1.20
    game has an empty holding there (no type, no levy or garrison); the founding save kept the old ones: a castle on
    9542 and a tribal holding on 9532 with their buildings, fort, and levy and garrison soldier pools, a siege of the
    castle, and an army standing on it. When the game files such a holding's pools under its province (when the
    holder changes: R15's hand-back does that) the province has no barony and the game crashes (2026-10-27, 989.1.1,
    ck3+0xb064e8: the write through the province's +0x848 pointer; moving the army alone did not stop it).

    So, on each impassable province: the holding becomes the empty one 1.20 writes (``income=0``) and the fort level
    goes; its soldier pools (and any pool whose origin is there) are deleted, with the army-regiment chunks that draw
    on them (a regiment left with none is deleted and leaves its army's list); a siege there is deleted; a map unit
    there goes back to its ``prev`` province when that is passable, dropping any unfinished path (one with no
    passable ``prev`` is reported and left).
    """
    if ctx.game_dir is None:
        return rule.result(matched=0, edited=0, extra={"skipped": "no --game-dir: the target map is unknown"})
    from ..mapdata import impassable_provinces
    bad = impassable_provinces(Path(ctx.game_dir))
    d = save.gamestate
    p = gs.EditPass()
    ex = {"holdings": [], "pools": [], "regiments": [], "chunks": 0, "sieges": [], "moved": [], "left": []}
    pools: set[bytes] = set()
    pb = _locate_or_none(d, "provinces")
    for e in gs.iter_entries(d, *pb.body) if pb is not None else []:
        if not (e.key and e.key.isdigit()) or int(e.key) not in bad:
            continue
        for c in gs.iter_children(d, *e.body):
            if c.key == b"holding" and c.block is not None:
                h = d[c.block.open:c.block.end]
                if b"type=" not in h and _POOL_REF.search(h) is None:
                    continue                                  # already the empty 1.20 form
                pools.update(m.group(1) for m in _POOL_REF.finditer(h))
                ind = d[d.rfind(b"\n", 0, c.start) + 1:c.start]
                p.add(gs.Edit(c.block.open, c.block.end, b"{\n" + ind + b"\tincome=0\n" + ind + b"}", rule.name,
                              f"province {e.key.decode()} holding"))
                ex["holdings"].append(int(e.key))
            elif c.key == b"fort_level":
                s, t = gs.removal_span(d, c.start, c.end)
                p.add(gs.Edit(s, t, b"", rule.name, f"province {e.key.decode()} fort"))
    rp = _locate_or_none(d, "armies/regiments")
    for e in gs.iter_entries(d, *rp.body) if rp is not None else []:
        o = re.search(rb"\n\t+origin=(\d+)", d[e.open:e.close])
        if e.key in pools or (o and int(o.group(1)) in bad):
            pools.add(e.key)
            p.delete_block(d, e, rule.name, f"pool {e.key.decode()}")
            ex["pools"].append(int(e.key))
    gone_regs: dict[bytes, bytes] = {}                      # army regiment -> its army
    ar = _locate_or_none(d, "armies/army_regiments")
    for e in gs.iter_entries(d, *ar.body) if ar is not None and pools else []:
        ch = next((c for c in gs.iter_children(d, *e.body) if c.key == b"chunks" and c.block is not None), None)
        if ch is None:
            continue
        items = [c for c in gs.iter_children(d, *ch.block.body) if c.block is not None]
        drop = [c for c in items if (m := _CHUNK_POOL.search(d, c.block.open, c.block.close)) and m.group(1) in pools]
        if not drop:
            continue
        if len(drop) == len(items):
            army = re.search(rb"\n\t+army=(\d+)", d[e.open:e.close])
            gone_regs[e.key] = army.group(1) if army else b""
            p.delete_block(d, e, rule.name, f"regiment {e.key.decode()}")
            ex["regiments"].append(int(e.key))
        else:
            for c in drop:
                s, t = gs.removal_span(d, c.start, c.end)
                p.add(gs.Edit(s, t, b"", rule.name, f"regiment {e.key.decode()} chunk"))
            ex["chunks"] += len(drop)
    aa = _locate_or_none(d, "armies/armies")
    if aa is not None and gone_regs:
        armies = set(gone_regs.values())
        for e in gs.iter_entries(d, *aa.body):
            if e.key not in armies:
                continue
            m = re.search(rb"\n\t+regiments=\{([^}]*)\}", d[e.open:e.close])
            if m:
                ids = m.group(1).split()
                kept = [i for i in ids if i not in gone_regs]
                if len(kept) != len(ids):
                    a = e.open + m.start(1)
                    p.add(gs.Edit(a, e.open + m.end(1), b" " + b" ".join(kept) + b" ", rule.name,
                                  f"army {e.key.decode()} regiments"))
    sb = _locate_or_none(d, "sieges/sieges")
    for e in gs.iter_entries(d, *sb.body) if sb is not None else []:
        pv = re.search(rb"\n\t+province=(\d+)", d[e.open:e.close])
        if e.key and pv and int(pv.group(1)) in bad:
            p.delete_block(d, e, rule.name, f"siege {e.key.decode()}")
            ex["sieges"].append(int(e.key))
    # a council task aimed at such a province (the crash itself: 50350018's task_increase_control on 9542, filed
    # under the province when a councillor is appointed) is aimed at a passable province of its court owner
    ct = _locate_or_none(d, "council_task_manager/active")
    aimed = []
    for e in gs.iter_entries(d, *ct.body) if ct is not None else []:
        m = _TASK_TARGET.search(d, e.open, e.close)
        if e.key and m and int(m.group(1)) in bad:
            co = re.search(rb"\n\t+court_owner=(\d+)", d[e.open:e.close])
            aimed.append((e, m, co.group(1) if co else None))
    if aimed:
        from ..mapdata import barony_provinces
        bprov = barony_provinces(Path(ctx.game_dir))
        lt = _locate_or_none(d, "landed_titles/landed_titles")
        keys = {m.group(1): m.group(2).decode() for m in _TITLE_KEY_LINE.finditer(d, lt.open, lt.close)} \
            if lt is not None else {}
        lv = _locate_or_none(d, "living")
        doms = {}
        for e in gs.iter_entries(d, *lv.body) if lv is not None else []:
            dm = re.search(rb"\n\t\tdomain=\{([^}]*)\}", d[e.open:e.close])
            if dm:
                doms[e.key] = dm.group(1).split()
        for e, m, co in aimed:
            to = next((bprov[keys[t]] for t in doms.get(co, []) if keys.get(t, "").startswith("b_")
                       and bprov.get(keys[t]) is not None and bprov[keys[t]] not in bad), None)
            if to is None:
                ex["tasks_left"] = ex.get("tasks_left", []) + [int(e.key)]
                continue
            p.add(gs.Edit(m.start(1), m.end(1), str(to).encode(), rule.name, f"council task {e.key.decode()}"))
            ex.setdefault("tasks", []).append({"task": int(e.key), "from": int(m.group(1)), "to": to})
    ub = _locate_or_none(d, "units")
    for e in gs.iter_entries(d, *ub.body) if ub is not None else []:
        t = d[e.start:e.end]
        loc = _UNIT_LOC.search(t)
        if not (e.key and loc) or int(loc.group(1)) not in bad:
            continue
        prev = _UNIT_PREV.search(t)
        to = int(prev.group(1)) if prev and int(prev.group(1)) not in bad else None
        if to is None:
            ex["left"].append({"unit": int(e.key), "location": int(loc.group(1))})
            continue
        new = _UNIT_MOVE.sub(b"", t[:loc.start(1)] + str(to).encode() + t[loc.end(1):])
        p.add(gs.Edit(e.start, e.end, new, rule.name, f"unit {e.key.decode()}"))
        ex["moved"].append({"unit": int(e.key), "from": int(loc.group(1)), "to": to})
    p.count(rule.name).matched = len(ex["holdings"]) + len(ex["pools"]) + len(ex["sieges"]) + len(ex["moved"]) \
        + len(ex["left"]) + len(ex.get("tasks", [])) + len(ex.get("tasks_left", []))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited, extra=ex)


# --------------------------------------------------------------------------- R6
_TITLE_DEF =re.compile(rb"(?<![\w.])([hekdcb]_[\w\-']+)\s*=\s*\{")
_LOOKUP_LINE = re.compile(r"^\s*([\w\-']+)\s*=\s*([\w\-']+)", re.M)


def defined_title_keys(game_dir: Path) -> tuple[set[str], dict[str, str]]:
    """Title templates the installed game defines, and its own old->new key conversions."""
    defined: set[str] = set()
    lt_dir = game_dir / "common" / "landed_titles"
    for f in sorted(lt_dir.glob("*.txt")):
        txt = re.sub(rb"#[^\n]*", b"", f.read_bytes())
        defined.update(m.group(1).decode() for m in _TITLE_DEF.finditer(txt))
    conv: dict[str, str] = {}
    lookup = lt_dir / "title_conversion.lookup"
    if lookup.exists():
        text = re.sub(r"#[^\n]*", "", lookup.read_text(encoding="utf-8-sig", errors="replace"))
        conv = {m.group(1): m.group(2) for m in _LOOKUP_LINE.finditer(text)}
    return defined, conv


def r6_dead_titles(save: CK3Save, ctx, rule) -> object:
    """Report (no edit) every title whose key the game no longer defines, with its links and references.

    1.8.1 save vs the installed game's common/landed_titles: 96 keys the 1.20 game
    logs as "not a valid title template" (d_knights_hospitaler is converted by the
    game's own title_conversion.lookup and is not counted). Dynamic x_ titles are skipped.
    """
    game_dir = ctx.game_dir
    if game_dir is None or not (game_dir / "common" / "landed_titles").is_dir():
        return rule.result(extra={"skipped": f"no game data at {game_dir}"})
    defined, conv = defined_title_keys(game_dir)
    d = save.gamestate
    try:
        lt = gs.locate(d, "landed_titles/landed_titles")
    except gs.GamestateError:
        return rule.result()
    dead: list[dict] = []
    converted: dict[str, str] = {}
    for t in gs.iter_entries(d, *lt.body):
        kids = {c.key: c for c in gs.iter_children(d, *t.body) if c.key in
                (b"key", b"holder", b"de_facto_liege", b"de_jure_liege")}
        if b"key" not in kids:
            continue
        key = _unquote(d[kids[b"key"].value_start:kids[b"key"].value_end])
        if key.startswith("x_") or key in defined:
            continue
        if key in conv:
            converted[key] = conv[key]
            continue
        dead.append({"id": t.key.decode(), "key": key,
                     **{k.decode(): d[c.value_start:c.value_end].decode() for k, c in kids.items() if k != b"key"}})
    if dead:
        ids = {row["id"] for row in dead}
        alt = re.compile(rb"(?<![\w.\-])(" + b"|".join(re.escape(i.encode()) for i in sorted(ids, key=len, reverse=True))
                         + rb")(?![\w.])")
        refs: Counter = Counter()
        ref_keys: dict[str, Counter] = {i: Counter() for i in ids}
        for m in alt.finditer(d):
            i = m.group(1).decode()
            refs[i] += 1
            s = m.start()
            if s and d[s - 1] == 0x3D:            # key=<id>
                k_end = s - 1
                k = k_end
                while k > 0 and d[k - 1] not in b" \t\r\n{}=":
                    k -= 1
                ref_keys[i][d[k:k_end].decode(errors="replace") or "<empty>"] += 1
            else:
                ref_keys[i]["<list or other>"] += 1
        for row in dead:
            row["refs_whole_token"] = refs[row["id"]]
            row["ref_keys"] = dict(ref_keys[row["id"]].most_common(8))
    return rule.result(matched=len(dead), edited=0,
                       extra={"dead": dead, "converted_by_game": converted,
                              "game_title_templates": len(defined)})


# --------------------------------------------------------------------------- R23
NICK_SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
_NICK_ENTRY = re.compile(rb"(?m)^(\d+)=\{")
_NICKNAME = re.compile(rb'(?m)^\tnickname=("?)([^"\s{}]+)\1[ \t]*\r?$')
_LOC_LINE = re.compile(r'^\s*([^\s:#"]+):\d*\s*"((?:[^"\\]|\\.)*)"')
_TEMPLATE_CODE = re.compile(r"\[([^\]]*)\]")


def english_localization(roots: list[tuple[str, Path]], wanted: set[str]) -> dict[str, tuple[str, str]]:
    """key -> (text, source) for the ``wanted`` keys, from ``<root>/localization/**/*_l_english.yml``. Roots are read
    in order and a later one wins (the game's load order: the game, then the mods as the save lists them); within a
    root, the files under ``replace/`` are read last, so they win. ``_desc`` keys are skipped."""
    out: dict[str, tuple[str, str]] = {}
    for source, root in roots:
        loc = root / "localization"
        if not loc.is_dir():
            continue
        files = sorted(loc.rglob("*_l_english.yml"), key=lambda p: ("replace" in p.relative_to(loc).parts, str(p)))
        for f in files:
            text = f.read_bytes().decode("utf-8-sig", errors="replace")
            for line in text.splitlines():
                m = _LOC_LINE.match(line)
                if not m or m.group(1) not in wanted or m.group(1).endswith("_desc"):
                    continue
                value = m.group(2).replace('\\"', '"').replace("\\\\", "\\")
                out[m.group(1)] = (value, source)
    return out


def _render(text: str, female: bool, first_name: str) -> tuple[str | None, str]:
    """A nickname text with its template codes rendered for one character: (text, "") or (None, why)."""
    def code(m):
        inner = m.group(1)
        name, _, fmt = inner.partition("|")
        word = {"CHARACTER.GetSheHe": "she" if female else "he",
                "CHARACTER.GetMotherFather": "mother" if female else "father",
                "CHARACTER.GetFirstNameNoTooltip": first_name}.get(name)
        if word is None or fmt not in ("", "U"):
            raise KeyError(inner)
        return word[:1].upper() + word[1:] if fmt == "U" else word
    try:
        out = _TEMPLATE_CODE.sub(code, text)
    except KeyError as exc:
        return None, f"template code [{exc.args[0]}] is not one this rule renders"
    if "[" in out or "$" in out:
        return None, "the text carries a code this rule does not render"
    return out, ""


def _escape(text: str) -> bytes:
    return text.replace("\\", "\\\\").replace('"', '\\"').encode("utf-8")


def _r23_found(d: bytes) -> list[tuple]:
    """Every nickname with no nickname_text after it, in the three character sections: (char id, key, insert
    position, female, first name). What R23 matches; its detector counts the same."""
    found = []
    for sec in NICK_SECTIONS:
        try:
            blk = gs.locate(d, sec)
        except gs.GamestateError:
            continue
        starts = [(m.start(), m.group(1)) for m in _NICK_ENTRY.finditer(d, blk.open, blk.close)]
        if not starts:
            continue
        positions = [s for s, _ in starts]
        for m in _NICKNAME.finditer(d, blk.open, blk.close):
            i = bisect_right(positions, m.start()) - 1
            if i < 0:
                continue
            start, cid = starts[i]
            end = positions[i + 1] if i + 1 < len(positions) else blk.close
            if re.search(rb"(?m)^\tnickname_text=", d[start:end]):
                continue
            body = d[start:end]
            fn = re.search(rb'(?m)^\tfirst_name="?([^"\n]*)"?', body)
            nl = d.find(b"\n", m.end() - 1)
            at = nl + 1 if nl >= 0 else m.end()
            found.append((cid.decode(), m.group(2).decode("utf-8", "replace"), at,
                          re.search(rb"(?m)^\tfemale=yes", body) is not None,
                          fn.group(1).decode("utf-8", "replace") if fn else ""))
    return found


NO_TEXT = "no English localization in the game or its mods"


def _r23_texts(found: list, game_dir, mod_dirs) -> tuple[list, bool]:
    """For each nickname R23 found: (char id, key, insert position, text or None, source, templated, why). The
    text is the one R23 writes; None when it can write none (no localization for the key in the game or the listed
    mods, or a template code it does not render), with why. The rule and its detector both judge by this."""
    roots = ([("game", game_dir)] if game_dir is not None else []) + \
        [(f"mod {p.name}", p) for p in mod_dirs or []]
    wanted = {k for _, k, _, _, _ in found} | {fn for _, _, _, _, fn in found if fn}
    loc = english_localization(roots, wanted)
    out = []
    for cid, key, at, female, first in found:
        hit = loc.get(key)
        if hit is None:
            out.append((cid, key, at, None, None, False,
                        NO_TEXT if roots else "no game folder to read the localization from"))
            continue
        text, source = hit
        templated = False
        if "[" in text or "$" in text:
            rendered, why = _render(text, female, loc.get(first, (first, ""))[0] if first else "")
            if rendered is None:
                out.append((cid, key, at, None, None, False, why))
                continue
            text, templated = rendered, True
        out.append((cid, key, at, text, source, templated, ""))
    return out, bool(roots)


def r23_detect(d: bytes, game_dir=None, mod_dirs=()) -> tuple[int, list[str], Counter]:
    """Read only: the nicknames without their text that R23 can write (from the game's and the listed mods'
    localization), up to five of them, and the ones it cannot, counted by why."""
    found = _r23_found(d)
    if not found:
        return 0, [], Counter()
    texts, _ = _r23_texts(found, game_dir, mod_dirs)
    fixable = [t for t in texts if t[3] is not None]
    left = Counter("no text" if t[6] == NO_TEXT else "unrendered" for t in texts if t[3] is None)
    return len(fixable), [f"character {t[0]} ({t[1]})" for t in fixable[:5]], left


def r23_nickname_text(save: CK3Save, ctx, rule) -> object:
    """Write ``nickname_text`` after every ``nickname`` that lacks it, in all three character sections.

    1.20 stores a nickname twice: the key (``nickname=nick_the_victorious``) and, on the next line, its rendered
    English text (``nickname_text="the Victorious"``); the game's own 987 save writes ``nickname_text`` on every
    character. A 1.8.1 save has only the key, and the game then shows the founder as ``Uilleam of " of Ireland``
    (2026-10-30: 851 nicknamed characters in the founding save, 89 distinct keys). The text comes from the English
    localization of the game folder, then of the save's mods in its listed order (a later one wins); two vanilla
    texts carry template codes (He/She, Father/Mother, the first name), rendered per character. A character that
    already has ``nickname_text``, or has no nickname, is left as it is; any other template code leaves the
    character untouched and is reported, never guessed.
    """
    d = save.gamestate
    found = _r23_found(d)
    if not found:
        return rule.result(matched=0, edited=0, extra={"found": 0})
    texts, _ = _r23_texts(found, ctx.game_dir, getattr(ctx, "mod_dirs", []) or [])
    p = gs.EditPass()
    by_source, templated, unresolved = Counter(), [], []
    for cid, key, at, text, source, was_templated, why in texts:
        p.count(rule.name).matched += 1
        if text is None:
            unresolved.append({"key": key, "id": cid, "reason": why})
            continue
        if was_templated:
            templated.append({"key": key, "id": cid, "text": text})
        p.add(gs.Edit(at, at, b'\tnickname_text="' + _escape(text) + b'"\n', rule.name, f"{cid} {key}"))
        by_source["game" if source == "game" else "mod"] += 1
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"found": len(found), "by_source": dict(by_source), "templated": templated,
                              "unresolved": unresolved})


# --------------------------------------------------------------------------- R25
class _Stack(str):
    """The ``new`` of a row whose successor is solved, not written: a tier stack (see ``stack_tiers``)."""


STACK = _Stack("<the kept tiers that add up to it>")
_TIER = re.compile(r"^(artifact_.+_)(\d+)(_modifier)$")
_OLD_TIERS = Path(__file__).resolve().parent.parent / "packs" / "to_1_20" / "R25-successor-keys" / "old_tier_values.json"


def modifier_effects(roots, keys) -> dict[str, dict[str, float]]:
    """The numeric effects of the given modifier keys, from ``common/modifiers`` over every root (later roots win)."""
    out: dict[str, dict[str, float]] = {}
    want = set(keys)
    for root in roots:
        base = Path(root) / "common" / "modifiers"
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.txt")):
            t = re.sub(r"#[^\n]*", "", f.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace"))
            for m in re.finditer(r"(?m)^([A-Za-z0-9_]+)\s*=\s*\{([^{}]*)\}", t):
                if m.group(1) in want:
                    out[m.group(1)] = {k: float(v) for k, v in
                                       re.findall(r"([a-z_]+)\s*=\s*(-?\d+(?:\.\d+)?)", m.group(2))}
    return out


def stack_tiers(target: dict[str, float], tiers: dict[str, dict[str, float]], most: int = 4) -> list[str] | None:
    """The fewest distinct tiers whose single stat adds up exactly to ``target`` (one stat), larger tiers first;
    None when no exact sum exists."""
    from itertools import combinations
    if len(target) != 1:
        return None
    (stat, want), = target.items()
    pool = sorted(((k, v[stat]) for k, v in tiers.items() if set(v) == {stat}), key=lambda kv: -abs(kv[1]))
    for n in range(1, most + 1):
        for combo in combinations(pool, n):
            if round(sum(v for _, v in combo) * 10000) == round(want * 10000):
                return [k for k, _ in combo]
    return None


def _old_tier_values(old_game_dir, key: str) -> dict[str, float] | None:
    if old_game_dir:
        got = modifier_effects([old_game_dir], [key]).get(key)
        if got:
            return got
    try:
        import json
        return json.loads(_OLD_TIERS.read_text(encoding="utf-8"))["values"].get(key)
    except (OSError, ValueError, KeyError):
        return None


@dataclass(frozen=True)
class Successor:
    """One row of R25's table: a key the target game no longer defines, and the key that took its place."""
    kind: str       # perk | men-at-arms | modifier
    field: str      # the save field whose value, or one-line list, holds the key
    old: str        # the key, or a pattern whose groups name a family of keys (matched whole)
    new: str        # the successor, or a template filled from old's groups (\1, \2)
    folder: str     # the common/ folder that defines keys of this kind
    how: str        # what the match rests on
    source: str     # the definitions compared
    changed_in: str = ""  # the game version that dropped the old key: the last version defining it, the first not


# Matched on what each thing is, never on the name alone (tests/one-offs/successor_finder.py; the culture goal's U2,
# 2026-11-04). Old definitions: the 1.8.2 game; new: the installed 1.20.1.2. Unsure matches wait on djdarcy (HOLD).
# changed_in: tests/one-offs/thinking/successor_versions.py over the versions held (1.8.2, 1.9.2, 1.10.2, 1.11.5,
# 1.12.5, 1.13.2, 1.14.3, 1.15.0, 1.16.2, 1.17.1, 1.18.4, 1.19.0, 1.20.0, 1.20.1.2), 2026-11-05; the major version is
# exact, a minor one between two held versions is not known.
SUCCESSORS = (
    Successor("perk", "perk", "scholar_perk", "erudite_perk", "lifestyle_perks",
              "the same tree (scholarship), the same position {1 5}, the same parent (sanctioned_loopholes_perk)",
              "00_learning_2_scholarship_tree_perks.txt, 1.8.2 and 1.20.1.2",
              "1.20 (defined through 1.19.0, gone in 1.20.0)"),
    Successor("men-at-arms", "type", "teutonic_knights", "order_serjeants", "men_at_arms_types",
              "holy-order heavy infantry with the nearest damage and toughness (36/26 -> 36/24)",
              "00_holy_order_maa_types.txt, 1.8.2 and 1.20.1.2",
              "1.20 (defined through 1.19.0, gone in 1.20.0)"),
    Successor("modifier", "modifiers", r"artifact_([a-z_]+)_scheme_power_add_(\d+)_modifier",
              r"artifact_\1_scheme_phase_duration_add_\2_modifier", "modifiers",
              "the scheme rework replaced scheme power with phase duration; the same scheme and tier",
              "00_artifact_modifiers.txt, 1.20.1.2",
              "1.13 (defined through 1.12.5, gone in 1.13.2)"),
    # djdarcy's answers, 2026-11-04 (HOLD 18:05)
    Successor("men-at-arms", "type", "chu_ko_nu", "shenbigong", "men_at_arms_types",
              "the game's own lineage: 1.20's innovation_repeating_crossbow (same era, icon and Chinese heritage) now "
              "unlocks shenbigong where 1.8's unlocked chu_ko_nu",
              "culture/innovations/00_cultural_maa_innovations.txt, 1.8.2 and 1.20.1.2",
              "1.18 (defined through 1.17.1, gone in 1.18.4)"),
    Successor("innovation", "type", "innovation_bombard", "innovation_gunpowder", "culture/innovations",
              "the same group and era; 1.20's innovation_gunpowder uses the icon innovation_bombards.dds",
              "culture/innovations/00_late_medieval_innovations.txt, 1.20.1.2",
              "1.18 (defined through 1.17.1, gone in 1.18.4)"),
    Successor("artifact look", "type", "medium_animal_hide", "large_animal_hide", "artifacts/visuals",
              "1.20 keeps the small (wall_small) and large (wall_big) hides; the medium one was wall_big",
              "artifacts/visuals/00_court_artifacts.txt, 1.8.2 and 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("stack", "modifiers", r"artifact_build_gold_cost_[5-9]_modifier", STACK,
              "modifiers", "1.20 keeps building-cost tiers -1% to -4% only; the old tier becomes the fewest kept tiers "
              "of the same bonus that add up to it exactly (-7% = -4% -3%), djdarcy 2026-11-05: 'Let's stack those "
              "bonuses ... that is what a player wanting to resume a game would want'",
              "00_artifact_modifiers.txt, 1.8.2 and 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("modifier", "modifiers", "artifact_vassal_tax_contribution_mult_1_modifier",
              "artifact_vassal_tax_contribution_mult_2_modifier", "modifiers",
              "1.20 keeps vassal tax contribution steps +2% and +4% only: the nearest kept step",
              "00_artifact_modifiers.txt, 1.8.2 and 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    # item 6 (goal S2): 1.20 dropped the plain "+N opinion with all vassals" artifact bonus; djdarcy wants it kept
    # universal with base-game definitions. The only pure all-vassal opinion modifiers 1.20 defines are -10, -3, +5, +10.
    Successor("modifier", "modifiers", "artifact_vassal_opinion_4_modifier",
              "artifact_killer_3_artifact_modifier unity_harmonious_placation_modifier",
              "modifiers", "+4 with all vassals -> +3 and +1 with all vassals, exactly +4: the same two keys as the +3 and "
              "+1 rows, with their small extras (djdarcy's call 2026-11-05, over the earlier nearest +5; 1.20's one "
              "bare +4, artifact_armor_3, brings +3 prowess too)",
              "00_artifact_modifiers.txt and 00_unity_modifiers.txt, 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("modifier", "modifiers", "artifact_vassal_opinion_3_modifier", "artifact_killer_3_artifact_modifier",
              "modifiers", "+3 with all vassals -> exactly +3 with all vassals, bundled with +0.03 prestige a month "
              "(djdarcy's call 2026-11-05: 'Seems fair'; found by the modifier catalogue)",
              "00_artifact_modifiers.txt, 1.20.1.2 (vassal_opinion = 3, monthly_prestige = 0.03)",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("modifier", "modifiers", "artifact_vassal_opinion_2_modifier",
              "hold_court_8010_vassal_modifier artifact_vassal_opinion_penalty_1_modifier",
              "modifiers", "+2 with all vassals -> +5 and -3 with all vassals: 1.20 has no +2 (bare or bundled); the "
              "pair adds up to +2. djdarcy looked at the tooltip in game (2026-11-05): 'It looks good'",
              "01_dlc_roco_modifiers_joe.txt and 00_artifact_modifiers.txt, 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("modifier", "modifiers", "artifact_vassal_opinion_1_modifier", "unity_harmonious_placation_modifier",
              "modifiers", "+1 with all vassals -> +1 with all vassals (plus +2% personal scheme success and +1% tax "
              "from happy powerful vassals), the only +1 all-vassal opinion 1.20 defines",
              "00_unity_modifiers.txt, 1.20.1.2",
              "1.9 (defined through 1.8.2, gone in 1.9.2)"),
    Successor("modifier", "modifier", r"fp2_hawk_of_quarysh_(\w+?)_modifier", r"fp2_hawk_of_quraysh_\1_modifier",
              "modifiers", "a spelling fix: the same definition (effect, file, place) under the corrected name",
              "03_dlc_fp2_modifiers.txt, 1.8.2 line 566 and 1.20.1.2 line 571",
              "1.19 (defined through 1.18.4, gone in 1.19.0)"),
    Successor("modifier", "modifier", "rice_fields_modifier", "terraced_hills_modifier",
              "modifiers", "a rename: the same Iberian event (fp2_yearly.3000, 'A Crop of New Ideas', still keyed on "
              "rice_field_potential: a Muslim Iberian ruler copying a neighbour's crops) gives terraced_hills_modifier "
              "('Agricultural Innovation') from 1.18 on, with the identical effect (+0.2 development growth, -10% "
              "build cost, +5 county opinion)",
              "fp2_yearly_events.txt and 03_dlc_fp2_modifiers.txt, 1.17.1 and 1.18.4",
              "1.18 (defined through 1.17.1, gone in 1.18.4)"),
    Successor("modifier", "modifier", "hold_court_7040_tax_cut", "court_tax_relief_county_modifier",
              "modifiers", "the same idea and name, 'Tax Relief' a ruler grants at court: 1.13 removed the hold-court "
              "event that gave the old one, and 1.20's 'Empty Granaries' (hold_court.6000) grants this one, which is "
              "stronger (-50% tax, +15 county opinion against -20% tax, -50% development growth); djdarcy's call, "
              "2026-11-04: let it through",
              "01_dlc_roco_modifiers_george.txt (1.12.5) and 00_court_event_modifiers_claudia.txt (1.20.1.2)",
              "1.13 (defined through 1.12.5, gone in 1.13.2)"),
)
_DEFINED = re.compile(rb"(?m)^([A-Za-z0-9_][\w.\-]*)\s*=\s*\{")


def defined_keys(roots, folder: str) -> set[str]:
    """The top-level keys ``<root>/common/<folder>/**/*.txt`` define, over every root (the game, then the mods)."""
    keys: set[str] = set()
    for root in roots:
        base = Path(root) / "common" / folder
        if base.is_dir():
            for f in sorted(base.rglob("*.txt")):
                text = f.read_bytes().removeprefix(b"\xef\xbb\xbf")       # the game's files carry a BOM
                keys.update(m.group(1).decode() for m in _DEFINED.finditer(text))
    return keys


def _in_field(d: bytes, s: int, field: bytes) -> bool:
    """Whether the token at ``s`` is ``field``'s value (``field=x``, ``field="x"``) or in its one-line list
    (``field={ a x b }``)."""
    q = s - 1 if s and d[s - 1] == 0x22 else s                      # step over an opening quote
    if d[q - len(field) - 1:q] == field + b"=":
        k = q - len(field) - 1
    else:
        brace = d.rfind(b"{", 0, s)
        if brace < 0 or d.rfind(b"}", brace, s) >= 0 or d.rfind(b"\n", brace, s) >= 0 or \
                d[brace - len(field) - 1:brace] != field + b"=":
            return False
        k = brace - len(field) - 1
    return k == 0 or d[k - 1] in b" \t\r\n{"


def _solve_stack(old: str, roots, defined: set[str], old_game_dir) -> str | None:
    """A stack row's successor: the kept tiers of ``old``'s family that add up to its old value, space-separated."""
    m = _TIER.match(old)
    target = _old_tier_values(old_game_dir, old) if m else None
    if not target:
        return None
    family = [k for k in defined if (t := _TIER.match(k)) and (t.group(1), t.group(3)) == (m.group(1), m.group(3))]
    keys = stack_tiers(target, modifier_effects(roots, family))
    return " ".join(keys) if keys else None


def r25_found(d: bytes, game_dir, mod_dirs=(), old_game_dir=None) -> tuple[list[tuple], Counter]:
    """Every old key of the table in its field: ``(start, end, old, new)`` for those it maps, and a count of those it
    leaves, by why (the old key is still defined; no successor is defined)."""
    roots = [game_dir, *mod_dirs]
    found, left = [], Counter()
    defined: dict[str, set[str]] = {}
    stacks: dict[str, str | None] = {}
    for row in SUCCESSORS:
        # the pattern starts with the key itself so the regex engine can scan for its literal prefix (a lookbehind
        # first made the scan of a 222 MB save take 10 s); the byte before is checked here instead
        token = re.compile(rb"(" + row.old.encode() + rb")(?![\w.\-])")
        field = row.field.encode()
        for m in token.finditer(d):
            if m.start() and (chr(d[m.start() - 1]).isalnum() or d[m.start() - 1] in b"_.-") or \
                    not _in_field(d, m.start(), field):
                continue
            if row.folder not in defined:
                defined[row.folder] = defined_keys(roots, row.folder)
            old = m.group(1).decode()
            if isinstance(row.new, _Stack):
                if old not in stacks:
                    stacks[old] = _solve_stack(old, roots, defined[row.folder], old_game_dir)
                if stacks[old] is None:
                    left[f"{old}: no exact stack of kept tiers"] += 1
                    continue
                new = stacks[old]
            else:
                new = re.fullmatch(row.old, old).expand(row.new)
            if old in defined[row.folder]:
                left[f"{old}: still defined"] += 1
            elif any(n not in defined[row.folder] for n in new.split()):   # a pair (two keys) needs both
                left[f"{old}: no {new} defined"] += 1
            else:
                found.append((m.start(), m.end(), old, new))
    return found, left


def r25_detect(d: bytes, game_dir, mod_dirs=()) -> tuple[int, list[str], Counter]:
    found, left = r25_found(d, game_dir, mod_dirs)
    by = Counter(f"{old} -> {new}" for _, _, old, new in found)
    return len(found), [f"{k} ({n:,})" for k, n in by.most_common(5)], left


def r25_successor_keys(save: CK3Save, ctx, rule) -> object:
    """Map each key the target game no longer defines to the key that took its place, from a cited table
    (``SUCCESSORS``), in the field that holds it: a character's ``perk={ ... }``, a regiment's ``type=``, an
    artifact's ``modifiers={ ... }``.

    Measured on the founding save (2026-11-04): 1.20 deletes on load what it cannot read, so 142 characters lose
    ``scholar_perk``, 11 regiments of ``teutonic_knights`` are disbanded, and 246 artifact modifiers of the
    ``artifact_<scheme>_scheme_power_add_<n>_modifier`` family vanish. Each successor was matched on what the thing
    is (the perk's tree, position and parent; the regiment's class, type and stats; the scheme rework's family),
    never on the name alone. A key is mapped only when the game and the save's listed mods no longer define it and
    do define its successor, so the rule never writes a key the game does not know; the rest is reported. A list
    that already holds the successor loses the old key instead.
    """
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "common").is_dir():
        return rule.result(extra={"skipped": f"no game data at {ctx.game_dir}"})
    d = save.gamestate
    found, left = r25_found(d, ctx.game_dir, getattr(ctx, "mod_dirs", []) or [], getattr(ctx, "old_game_dir", None))
    p = gs.EditPass()
    mapped, dropped = Counter(), Counter()
    for s, e, old, new in found:
        p.count(rule.name).matched += 1
        line_start, line_end = d.rfind(b"\n", 0, s) + 1, d.find(b"\n", e)
        others = d[line_start:line_end]
        if d[s - 1:s] != b'"' and re.search(rb"(?<![\w.\-])" + re.escape(new.encode()) + rb"(?![\w.\-])", others):
            a, b = (s, e + 1) if d[e:e + 1] == b" " else (s - 1 if d[s - 1:s] == b" " else s, e)
            p.add(gs.Edit(a, b, b"", rule.name, f"{old} (its list already has {new})"))
            dropped[f"{old} -> {new}"] += 1
        else:
            p.add(gs.Edit(s, e, new.encode(), rule.name, f"{old} -> {new}"))
            mapped[f"{old} -> {new}"] += 1
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"mapped": dict(mapped.most_common()), "dropped_duplicates": dict(dropped),
                              "left": dict(left.most_common()),
                              "table": [{"kind": r.kind, "old": r.old, "new": r.new, "how": r.how, "source": r.source}
                                        for r in SUCCESSORS]})


# --------------------------------------------------------------------------- R27
FEUD_FRACTION = "-0.9"   # within-level score, about -1..+1 (1.20 save, 1,216 relations); deep in the feud level
_FEUD_STORY = re.compile(rb'story_cycle="?story_cycle_house_feud"?')


def _character_house(d: bytes, cid: bytes) -> bytes | None:
    for sec in ("living", "dead_unprunable"):
        try:
            b = gs.find_section(d, sec)
        except gs.GamestateError:
            continue
        m = re.compile(rb"\n" + cid + rb"=\{").search(d, b.start, b.end)
        if m:
            h = re.search(rb"(?m)^\tdynasty_house=(\d+)", d[m.end():d.find(b"\n}", m.end())])
            return h.group(1) if h else None
    return None


def r27_found(d: bytes) -> list[tuple[bytes, bytes]]:
    """The house pairs of 1.8's house-feud stories: (the owner's house, the rival house in house_feud_house)."""
    try:
        st = gs.locate(d, "stories/active")
    except gs.GamestateError:
        return []
    pairs = []
    for e in gs.iter_entries(d, *st.body):
        body = d[e.body[0]:e.body[1]]
        if not _FEUD_STORY.search(body):
            continue
        owner = re.search(rb"(?m)^\t*owner=(\d+)", body)
        rival = re.search(rb'flag="?house_feud_house"?\s*data=\{\s*type=dyn_house\s*identity=(\d+)', body)
        house = _character_house(d, owner.group(1)) if owner else None
        if house and rival and house != rival.group(1):
            pairs.append((house, rival.group(1)))
    return pairs


def r27_house_feuds(save: CK3Save, ctx, rule) -> object:
    """Carry 1.8's house feuds into 1.20's house relations at the feud level.

    1.8 (bp1) ran each house feud as a story (``story_cycle_house_feud``: an owner and the rival house in its
    ``house_feud_house`` variable). 1.20 comments that story cycle out and tracks feuds as house relations
    (``common/house_relation_types/00_house_relations.txt``; feud: -30 opinion, the eradicate casus belli), saved in
    ``house_relations={ database={ ... } }``. Each feud becomes one relation between the owner's house and the rival
    house at ``default_house_relation_level_feud``, scored -0.9 within the level so it lasts until the houses
    reconcile (the PoC of 2026-11-04 at score 0 eased to rivalry in 14 months). The old story is left for the game
    to drop. A pair that already has a relation is left as it is. Measured: the founding save's 2 feuds kept at the
    feud level by the game's own re-save.
    """
    d = save.gamestate
    pairs = r27_found(d)
    if not pairs:
        return rule.result(matched=0, edited=0)
    p = gs.EditPass()
    try:
        hr = gs.locate(d, "house_relations/database")
    except gs.GamestateError:
        hr = None
    have, next_id = set(), 0
    if hr is not None:
        for e in gs.iter_entries(d, *hr.body):
            next_id = max(next_id, int(e.key) + 1) if e.key.isdigit() else next_id
            hs = re.search(rb"houses=\{\s*(\d+)\s+(\d+)", d[e.body[0]:e.body[1]])
            if hs:
                have.add(frozenset(hs.groups()))
    entries, added = b"", 0
    for a, b in pairs:
        p.count(rule.name).matched += 1
        if frozenset((a, b)) in have:
            continue
        have.add(frozenset((a, b)))
        entries += (b"\t\t%d={\n\t\t\thouses={ %s %s }\n\t\t\ttype=default_house_relation\n"
                    b"\t\t\tlevel=default_house_relation_level_feud\n\t\t\tfraction=%s\n\t\t}\n"
                    % (next_id, a, b, FEUD_FRACTION.encode()))
        next_id += 1
        added += 1
    if entries:
        if hr is not None:
            p.add(gs.Edit(hr.body[1], hr.body[1], entries, rule.name, f"{added} feuds"))
        else:
            tail = len(d)
            p.add(gs.Edit(tail, tail, (b"" if d.endswith(b"\n") else b"\n") +
                          b"house_relations={\n\tdatabase={\n" + entries + b"\t}\n}\n", rule.name, f"{added} feuds"))
    p.apply_to(save)
    return rule.result(matched=len(pairs), edited=added, extra={"pairs": [[a.decode(), b.decode()] for a, b in pairs]})


# --------------------------------------------------------------------------- R28
MARRIAGE_BED = b"rejected_from_marriage_bed_modifier"
NO_FERTILITY_RELATION = b"wedding_very_bad_fertility"
_MARRIAGE_BED_BLOCK = re.compile(rb'modifier=\{\s*modifier="?' + MARRIAGE_BED + rb'"?\s*expiration_date=\S+\s*\}')


def _character_spans(d: bytes, sec: str) -> dict[bytes, tuple[int, int]]:
    """Each character's body span in ``living`` or ``dead_unprunable`` (entries ``id={`` at column 0)."""
    try:
        b = gs.find_section(d, sec)
    except gs.GamestateError:
        return {}
    return {e.key: e.body for e in gs.iter_entries(d, *b.body) if e.key and e.key.isdigit()}


def r28_found(d: bytes) -> list[tuple[bytes, list[bytes], list[tuple[int, int]]]]:
    """The living holders of 1.8's marriage-bed modifier: (character, its living spouses, the modifier blocks)."""
    if MARRIAGE_BED not in d:
        return []
    living = _character_spans(d, "living")
    out = []
    for cid, (lo, hi) in living.items():
        if d.find(MARRIAGE_BED, lo, hi) < 0:
            continue
        blocks = [m.span() for m in _MARRIAGE_BED_BLOCK.finditer(d, lo, hi)]
        if not blocks:
            continue
        fam = re.search(rb"family_data=\{(.*?)\n\t\}", d[lo:hi], re.S)
        spouses = []
        for s in re.findall(rb"(?m)^\t\tspouse=(\d+)", fam.group(1)) if fam else []:
            if s in living and s != cid and s not in spouses:
                spouses.append(s)
        out.append((cid, spouses, blocks))
    return out


def r28_marriage_bed(save: CK3Save, ctx, rule) -> object:
    """Carry 1.8's "Rejected From Marriage Bed" into 1.20's no-fertility relation with the spouse.

    The modifier (``rejected_from_marriage_bed_modifier``: fertility -100, never expiring, "this character's marriage
    will produce no offspring") was last defined in 1.19; 1.20 checks a hidden pair relation instead,
    ``wedding_very_bad_fertility`` (``common/scripted_relations``: fertility -1.4, corresponding, removed on divorce),
    in the same health events that checked the modifier. So each living holder gets that relation with each living
    spouse, stored both ways as the game stores a corresponding relation (``opinions/active_opinions``,
    ``scripted_relations={ name={ flags="AA==" } }``), and the modifier the game no longer defines is removed. A
    holder with no living spouse loses only the modifier: the relation has no one to attach to.
    """
    d = save.gamestate
    found = r28_found(d)
    if not found:
        return rule.result(matched=0, edited=0)
    p = gs.EditPass()
    wanted: set[tuple[bytes, bytes]] = set()
    for cid, spouses, blocks in found:
        p.count(rule.name).matched += 1
        for s, e in blocks:
            a, b = gs.removal_span(d, s, e)
            p.add(gs.Edit(a, b, b"", rule.name, "marriage-bed modifier"))
        for sp in spouses:
            wanted.update({(cid, sp), (sp, cid)})
    pairs = 0
    if wanted:
        try:
            ao = gs.locate(d, "opinions/active_opinions")
        except gs.GamestateError:
            ao = None
        if ao is not None:
            for e in gs.iter_entries(d, *ao.body):
                body = d[e.body[0]:e.body[1]]
                m = re.search(rb"owner=(\d+)\s+target=(\d+)", body)
                if not m or (m.group(1), m.group(2)) not in wanted:
                    continue
                wanted.discard((m.group(1), m.group(2)))
                if NO_FERTILITY_RELATION + b"={" in body:
                    continue
                sr = re.search(rb"scripted_relations=\{", body)
                rel = b"\t\t\t\t" + NO_FERTILITY_RELATION + b'={\n\t\t\t\t\tflags="AA=="\n\t\t\t\t}\n'
                if sr:
                    at = e.body[0] + sr.end()
                    p.add(gs.Edit(at, at, b"\n" + rel, rule.name, "relation"))
                else:                             # before the entry's closing line
                    at = d.rfind(b"\n", e.body[0], e.close) + 1 or e.close
                    p.add(gs.Edit(at, at, b"\t\t\tscripted_relations={\n" + rel + b"\t\t\t}\n", rule.name, "relation"))
                pairs += 1
        new = b"".join(b' {\n\t\t\towner=%s\n\t\t\ttarget=%s\n\t\t\tscripted_relations={\n\t\t\t\t%s={\n'
                       b'\t\t\t\t\tflags="AA=="\n\t\t\t\t}\n\t\t\t}\n\t\t}\n' % (a, b, NO_FERTILITY_RELATION)
                       for a, b in sorted(wanted))
        if new and ao is not None:
            p.add(gs.Edit(ao.close, ao.close, new, rule.name, "relations"))
            pairs += len(wanted)
    p.apply_to(save)
    return rule.result(matched=len(found), edited=pairs,
                       extra={"holders": len(found), "with_spouse": sum(1 for f in found if f[1]),
                              "relations": pairs})


# --------------------------------------------------------------------------- R29
SECRECY_BASE = b"20"   # secrecy_base_value's BASE (common/script_values/00_scheme_values.txt, 1.20.1.2)
SECRECY_NONE = b"100"  # what 1.20 holds for a type with no base_secrecy (measured 2026-11-04: its own fresh sway
#                        403/403, learn_language 151/151, courting 14/14, befriend 7/7 at 100)
_FALLBACK_AGENTS = re.compile(rb"agents_added\s*\}\s*\}\s*\}((?:\s*add_agent_slot\s*=\s*\w+)+)")
_NO_CHARACTER = b"4294967295"
_OWNER_AGENT = re.compile(rb"(?m)^\t*owner_agent=\{\s*character=(\d+)\s*influence=(-?\d+)[^{}]*\}[ \t]*$")


# The order 1.20 writes a scheme's fields in (measured 2026-11-05 on its day-one re-save of 1,334 carried plots and on
# 1,062 plots it started itself). A field not listed keeps its place after the one before it.
_SCHEME_ORDER = {k: i for i, k in enumerate((
    b"type", b"status", b"owner", b"target", b"artifact", b"progress", b"opportunities", b"agent_slots", b"variables",
    b"update_days", b"semiyearly_update_days", b"scheme_exposed", b"scheme_exposed_date", b"secrecy", b"date",
    b"last_update", b"ramping_success_chance", b"breach", b"phases", b"next_id", b"timed_modifier", b"freeze_data"))}
_SCHEME_DROPPED = (b"owner_influence", b"chance", b"ready", b"scheme_freeze_days", b"owner_agent")
_SCHEME_START = ((b"status", None), (b"opportunities", b"0"), (b"semiyearly_update_days", b"0"),
                 (b"last_update", b"1.1.1"), (b"ramping_success_chance", b"0"), (b"breach", b"0"), (b"phases", b"0"),
                 (b"next_id", b"0"))


def scheme_fields(body: bytes) -> tuple[bytes, list[tuple[bytes, bytes]]]:
    """A scheme entry's inner text as (indent, [(key, field text without indent or newline)]), top level only."""
    first = re.search(rb"\n(\t*)\w", body)
    if not first:
        return b"", []
    ind = first.group(1)
    pat = re.compile(rb"(?m)^" + re.escape(ind) + rb"(\w+)=")
    out, pos = [], 0
    while m := pat.search(body, pos):
        j = m.end()
        if body[j:j + 1] == b"{":
            end = gs.match_brace(body, j) + 1
        else:
            end = body.find(b"\n", j)
            end = len(body) if end < 0 else end
        out.append((m.group(1), body[m.start() + len(ind):end]))
        pos = end
    return ind, out


def is_old_scheme(fields: list[tuple[bytes, bytes]]) -> bool:
    """A scheme in the layout older games wrote: it has 1.8's fields, or a bare ``target=N``."""
    return any(k in (b"owner_influence", b"scheme_freeze_days") or (k == b"target" and not v.startswith(b"target={"))
               for k, v in fields)


def convert_old_scheme(fields: list[tuple[bytes, bytes]], ind: bytes, frozen: bool = True) -> list[tuple[bytes, bytes]]:
    """What 1.20 makes of an older game's scheme on load, field for field (measured 2026-11-05 over 1,334 plots against
    the game's own re-save; design 2026-11-05__09-48-21). It drops ``owner_influence``, ``chance`` and ``ready`` (1.20
    computes success from the type's formulas, and the ramping bonus starts at 0), unquotes the type, wraps ``target``
    in its block, and gives the plot 1.20's starting values. ``status`` is ``invalidated`` for a plot with no owner,
    target or type (20/20 on the founding save) and ``continue`` otherwise. The game keeps the plot frozen
    (``freeze_data``); ``frozen=False`` leaves that block out, as 1.20 writes a plot that runs."""
    val = {k: v.split(b"=", 1)[1] for k, v in fields if not v.endswith(b"}")}
    gone = (None, _NO_CHARACTER)
    invalid = val.get(b"owner") in gone and val.get(b"target") in gone and b"type" not in val
    out = []
    for k, v in fields:
        if k in _SCHEME_DROPPED:
            continue
        if k == b"type":
            v = b"type=" + val[k].strip(b'"')
        elif k == b"target" and k in val:
            v = (b"target={\n" + ind + b"\ttype=character\n" + ind + b"\ttarget=" + val[k] + b"\n" + ind + b"}")
        out.append((k, v))
    for k, x in _SCHEME_START:
        out.append((k, k + b"=" + (x if x is not None else b"invalidated" if invalid else b"continue")))
    if frozen:
        out.append((b"freeze_data", b"freeze_data={\n" + ind + b"\tfrozen=yes\n" + ind + b"\tscheme_freeze_days=" +
                    val.get(b"scheme_freeze_days", b"0") + b"\n" + ind + b'\treason=""\n' + ind + b"}"))
    return scheme_in_order(out)


def scheme_in_order(fields: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Sort fields into 1.20's order; an unknown field keeps its place after the known field before it."""
    keyed, last = [], -1.0
    for n, (k, v) in enumerate(fields):
        last = _SCHEME_ORDER.get(k, last + 0.001)
        keyed.append((last, n, k, v))
    return [(k, v) for _, _, k, v in sorted(keyed)]


def scheme_text(fields: list[tuple[bytes, bytes]], ind: bytes) -> bytes:
    """Fields back into an entry's inner text."""
    return b"\n" + b"".join(ind + v + b"\n" for _, v in fields) + ind[:-1]


def scheme_type_defaults(roots) -> dict[bytes, tuple[bool, list[bytes]]]:
    """Per scheme type the game and the mods define (later roots win): whether it has a ``base_secrecy``, and the
    agent slots its ``on_start`` adds for a scheme started from script -- the "fallback agents" block, taken when
    the owner lacks the ``agents_added`` variable."""
    out: dict[bytes, tuple[bool, list[bytes]]] = {}
    for root in roots:
        base = Path(root) / "common" / "schemes" / "scheme_types"
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.txt")):
            t = re.sub(rb"#[^\n]*", b"", f.read_bytes().removeprefix(b"\xef\xbb\xbf"))
            for m in _DEFINED.finditer(t):
                try:
                    body = t[m.end() - 1:gs.match_brace(t, m.end() - 1)]
                except gs.GamestateError:
                    continue
                fb = _FALLBACK_AGENTS.search(body)
                out[m.group(1)] = (b"base_secrecy" in body,
                                   re.findall(rb"add_agent_slot\s*=\s*(\w+)", fb.group(1)) if fb else [])
    return out


def r29_found(d: bytes) -> list[gs.Block]:
    """The schemes an older game wrote, in its layout (``owner_influence``, ``scheme_freeze_days``, a bare target)."""
    try:
        act = gs.locate(d, "schemes/active")
    except gs.GamestateError:
        return []
    return [e for e in gs.iter_entries(d, *act.body)
            if e.key and is_old_scheme(scheme_fields(d[e.open + 1:e.close])[1])]


def r29_scheme_thaw(save: CK3Save, ctx, rule) -> object:
    """Convert the schemes an older game wrote into 1.20's layout, thaw them, and give them what 1.20's start-up gives
    a scheme started from script.

    The conversion is the game's own (``convert_old_scheme``): what 1.20 writes for each carried plot after a load and
    a save, matched on 1,334/1,334 plots of the founding save. Three things differ from the game's result, on purpose.

    1.8 wrote ``scheme_freeze_days=0`` into every scheme, and 1.20 reads it as frozen for good: no carried plot ever
    moves (the PoC of 2026-11-04 deleted the field and 712 schemes ran again). A carried scheme also skips 1.20's
    start-up, so two things are missing. Its secrecy stays 1.8's -1, which 1.20 reads as "before on_ready"
    (``ck3+0x2b4a200``: a negative secrecy logs the error and reads as 0) until its first update recomputes it; a
    type with a ``base_secrecy`` gets the formula's base, 20, in its place, and a type without one gets 100, what 1.20
    holds for its own schemes of such types. And it has no agent slots, which only
    ``on_start`` adds; a type whose ``on_start`` has the fallback for a scheme started from script (an owner without
    ``agents_added``) gets those slots, empty, as the game's own fallback leaves them. Both come from the game's and
    the listed mods' scheme definitions, so a type the game does not define is only thawed.
    """
    d = save.gamestate
    found = r29_found(d)
    if not found:
        return rule.result(matched=0, edited=0)
    roots = ([ctx.game_dir] if ctx.game_dir else []) + list(getattr(ctx, "mod_dirs", []) or [])
    defaults = scheme_type_defaults(roots)
    p = gs.EditPass()
    secrecy = slots = seated = unseated = gone = invalid = 0
    dropped = Counter()                    # the old fields 1.20 has no place for, as the game drops them (#7)
    try:
        lv = gs.find_section(d, "living")
        living = {m.group(1) for m in re.finditer(rb"(?m)^(\d+)=\{", d[lv.start:lv.end])}
    except gs.GamestateError:
        living = set()
    for e in found:
        p.count(rule.name).matched += 1
        ind, old = scheme_fields(d[e.open + 1:e.close])
        ty = next((v.split(b"=", 1)[1].strip(b'"') for k, v in old if k == b"type"), None)
        has_base, agents = defaults.get(ty or b"", (False, []))
        old_agents = []                                   # 1.8's agents who had joined: (influence, character)
        for k, v in old:
            oa = _OWNER_AGENT.match(v) if k == b"owner_agent" else None
            if oa and oa.group(1) in living:
                old_agents.append((int(oa.group(2)), oa.group(1)))
            elif oa:
                gone += 1
        old_agents = [c for _, c in sorted(old_agents, key=lambda x: -x[0])]
        dropped.update(k.decode() for k, _ in old if k in (b"owner_influence", b"chance", b"ready"))
        f = convert_old_scheme(old, ind, frozen=False)                   # the game's conversion, thawed
        invalid += (b"status", b"status=invalidated") in f
        if ty in defaults and (b"secrecy", b"secrecy=-1") in f:
            f = [(k, b"secrecy=" + (SECRECY_BASE if has_base else SECRECY_NONE) if k == b"secrecy" else v)
                 for k, v in f]
            secrecy += 1
        if agents and not any(k == b"agent_slots" for k, _ in f):
            seat = old_agents[:len(agents)] + [_NO_CHARACTER] * max(0, len(agents) - len(old_agents))
            seated += min(len(agents), len(old_agents))
            unseated += max(0, len(old_agents) - len(agents))
            f = [(k, b"next_id=%d" % len(agents) if k == b"next_id" else v) for k, v in f]
            f += [(b"agent_slots", b"agent_slots={\n" + ind + b"\tid=%d\n" % i + ind + b"\tcharacter=" + seat[i] +
                   b"\n" + ind + b"\tcontribution=0\n" + ind + b"\ttype=" + ag + b"\n" + ind + b"\tscheme=" +
                   e.key + b"\n" + ind + b"}") for i, ag in enumerate(agents)]
            f = scheme_in_order(f)
            slots += 1
        else:
            unseated += len(old_agents)
        p.add(gs.Edit(e.open + 1, e.close, scheme_text(f, ind), rule.name, "convert"))
    p.apply_to(save)
    return rule.result(matched=len(found), edited=len(found),
                       extra={"lost": [{"what": f"plot field {k}", "plots": n,
                                        "why": "1.20 computes a plot's success from its type and members at each "
                                               "update, and drops this field on load (docs/not-carried-over.md)"}
                                       for k, n in sorted(dropped.items())],
                              "converted": len(found), "invalidated": invalid, "fields_dropped": dict(dropped),
                              "thawed": len(found),
                              "secrecy_set": secrecy, "agent_slots_added": slots, "old_agents_seated": seated,
                              "old_agents_without_a_slot": unseated, "old_agents_no_longer_living": gone})


# --------------------------------------------------------------------------- R30
@dataclass(frozen=True)
class AssetRename:
    field: str      # the save field that holds the reference (icon=, asset=, texture=)
    old: str        # regex over the old name
    new: str        # template filled from old's groups
    kind: str       # "file" (an image under gfx/) or "entity" (a 3D model named in a gfx .asset file)
    how: str
    source: str


ASSET_RENAMES = (
    AssetRename("icon", r"artefact_icons_(\w+\.dds)", r"artifact_icons_\1", "file",
                "1.20 renamed the unique-artifact icons from the spelling 'artefact' to 'artifact'; the same visual "
                "definitions now name the new file (excalibur: artefact_icons_unique_artifact_excalibur.dds -> "
                "artifact_icons_unique_artifact_excalibur.dds)",
                "common/artifacts/visuals/00_historical.txt, 1.8.2 and 1.20.1.2"),
    AssetRename("asset", r"male_(?:clothes|clothing)_secular_(\w+?)_war_nobility_(\d+)_artifact_entity",
                r"m_clothes_sec_\1_war_nob_\2_artifact_entity", "entity",
                "1.20 shortened the armour-artifact model names; the same visual definitions now reference the short "
                "name (male_clothes_secular_mena_war_nobility_01_artifact_entity -> m_clothes_sec_mena_war_nob_01_"
                "artifact_entity)",
                "common/artifacts/visuals/00_court_artifacts.txt and 00_personal_misc.txt, 1.8.2 and 1.20.1.2"),
    AssetRename("asset", r"female_(?:clothes|clothing)_secular_(\w+?)_war_nobility_(\d+)_artifact_entity",
                r"f_clothes_sec_\1_war_nob_\2_artifact_entity", "entity",
                "the same shortening for the women's armour models",
                "common/artifacts/visuals/00_court_artifacts.txt and 00_personal_misc.txt, 1.8.2 and 1.20.1.2"),
    AssetRename("texture", r"ce_african_cross_(?:NU|nu)\.dds", "ce_african_cross_nu2.dds", "file",
                "the coat-of-arms emblem list keeps the same entry (weight 50, line 179) under the new file name",
                "common/coat_of_arms/template_lists/colored_emblem_lists.txt, 1.8.2 and 1.20.1.2"),
)


def gfx_inventory(roots) -> tuple[set[str], set[str]]:
    """The image files (lower-cased names) and the 3D model entities every root's gfx/ provides."""
    files: set[str] = set()
    entities: set[str] = set()
    for root in roots:
        g = Path(root) / "gfx"
        if not g.is_dir():
            continue
        for f in g.rglob("*"):
            s = f.suffix.lower()
            if s in (".dds", ".png", ".tga"):
                files.add(f.name.lower())
            elif s == ".asset":
                text = f.read_bytes()
                entities.update(m.group(1).decode().lower() for m in re.finditer(rb'name\s*=\s*"?(\w+_entity)"?', text))
    return files, entities


def r30_found(d: bytes, roots) -> tuple[list[tuple[int, int, str, str]], Counter]:
    """Every reference the table renames: ``(start, end, old, new)`` where the old file or model is gone and the new
    one exists in some root; a count of those left, by why."""
    cand = []
    for row in ASSET_RENAMES:
        pat = re.compile(rb'(?<=\b' + row.field.encode() + rb'=")(' + row.old.encode() + rb')(?=")')
        cand += [(m.start(), m.end(), m.group(1).decode(), row) for m in pat.finditer(d)]
    if not cand:
        return [], Counter()
    files, entities = gfx_inventory(roots)
    found, left = [], Counter()
    for s, e, old, row in cand:
        new = re.fullmatch(row.old, old).expand(row.new)
        have = files if row.kind == "file" else entities
        if old.lower() in have:
            left[f"{old}: still shipped"] += 1
        elif new.lower() not in have:
            left[f"{old}: no {new}"] += 1
        else:
            found.append((s, e, old, new))
    return found, left


def r30_asset_renames(save: CK3Save, ctx, rule) -> object:
    """Point the save's file references at the names the current game ships them under.

    A save stores some looks as file names: an artifact's ``icon=`` and ``asset=`` (its picture and its 3D model), a
    coat of arms' ``texture=``. 1.20 renamed some of those files, so the game finds nothing and draws nothing (found
    2026-11-05 when Excalibur and the Skull Cap of Charlemagne showed no picture). Each rename in ``ASSET_RENAMES`` was
    confirmed in the game's own definitions -- the same visual or emblem entry names the old file in 1.8.2 and the new
    one in 1.20 -- and a reference is renamed only when the old file is gone and the new one is shipped by the game or
    a listed mod.
    """
    if ctx.game_dir is None or not (Path(ctx.game_dir) / "gfx").is_dir():
        return rule.result(extra={"skipped": f"no game data at {ctx.game_dir}"})
    d = save.gamestate
    found, left = r30_found(d, [ctx.game_dir, *(getattr(ctx, "mod_dirs", []) or [])])
    p = gs.EditPass()
    renamed = Counter()
    for s, e, old, new in found:
        p.count(rule.name).matched += 1
        p.add(gs.Edit(s, e, new.encode(), rule.name, f"{old} -> {new}"))
        renamed[f"{old} -> {new}"] += 1
    p.apply_to(save)
    return rule.result(matched=len(found), edited=len(found), extra={"renamed": dict(renamed), "left": dict(left)})


# --------------------------------------------------------------------------- R31
_R31_DOMAIN = re.compile(rb"\n\t\tdomain=\{([^}]*)\}")


def r31_found(d: bytes) -> list[tuple[int, str, str, int]]:
    """Read only: each living ruler whose primary title answers to a liege title held by someone else, and who has
    no vassal contract at all: (ruler, his primary title's key, the liege title's key, that title's holder).

    Left out: a character filed among the living with ``dead_data`` (the game moves him to the dead on load) and
    one whose first domain entry another character holds (a stale list; the founding save's Uilleam of Frisia,
    45243, is both)."""
    titles = {}
    try:
        lt = gs.locate(d, "landed_titles/landed_titles")
    except gs.GamestateError:
        return []
    for e in gs.iter_entries(d, *lt.body):
        if not (e.key and e.key.isdigit()):
            continue
        b = d[e.open:min(e.close, e.open + 4096)]
        k = re.search(rb'\n\tkey="?([\w-]+)', b)
        h, l = re.search(rb"\n\tholder=(\d+)", b), re.search(rb"\n\tde_facto_liege=(\d+)", b)
        titles[int(e.key)] = (k.group(1).decode() if k else "?", int(h.group(1)) if h else None,
                              int(l.group(1)) if l else None)
    vassals = set()
    for path in ("vassal_contracts/active", "vassal_contracts/database"):
        try:
            cb = gs.locate(d, path)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(d, *cb.body):
            v = re.search(rb"\n\t+vassal=(\d+)", d[e.open:e.close])
            if v:
                vassals.add(int(v.group(1)))
    out = []
    try:
        liv = gs.locate(d, "living")
    except gs.GamestateError:
        return []
    for e in gs.iter_entries(d, *liv.body):
        if not (e.key and e.key.isdigit()) or int(e.key) in vassals:
            continue
        body = d[e.open:e.close]
        dm = _R31_DOMAIN.search(body)
        if not dm or b"dead_data={" in body:
            continue
        ids = dm.group(1).split()
        if not ids:
            continue
        c, p = int(e.key), int(ids[0])
        key, holder, tl = titles.get(p, ("?", None, None))
        if holder != c or tl is None or tl not in titles:
            continue
        th = titles[tl][1]
        if th is not None and th != c:
            out.append((c, key, titles[tl][0], th))
    return out


def r31_detect(d: bytes) -> tuple[int, list[str]]:
    found = r31_found(d)
    return len(found), [f"{c} ({k}) under {lk} of {th}" for c, k, lk, th in found[:5]]


def r31_contract_repair(save: CK3Save, ctx, rule) -> object:
    """Write the missing vassal contract of every ruler whose title answers to a liege but who has no contract.

    Such a vassal pays no taxes and raises no levies, and 1.20 never writes one (0 of 4,179 rulers in a fresh 1.20
    game; the game's own re-save does not repair them). The founding save has two, its barons of Matera and Ainsa,
    most likely from manual save editing. djdarcy, 2026-11-05: "the default is repair but we need an override" --
    a player may have edited a save on purpose to free a vassal from his dues, so ``status`` names each one and
    ``--rules all,-R31`` (or ``ck3update disable R31``) keeps them as they are. The contract is written the way R17's
    lock-step pass writes one: in a free slot, with the contract group the ruler's government uses, and listed by
    the liege. Tributaries are not touched: a tributary has a contract and no title liege, the other way round."""
    from .transplant_1_20 import _lock_step
    found = r31_found(save.gamestate)
    if not found:
        return rule.result()
    rows = _lock_step(save, ctx, characters={c for c, *_ in found}, only={"title only"}, tag="R31")
    n = rows.get("contract written for a title liege", 0)
    return rule.result(matched=len(found), edited=n, extra={
        "repaired": [{"ruler": c, "title": k, "liege_title": lk, "liege": th} for c, k, lk, th in found]})


from . import Rule  # noqa: E402  (circular-safe: Rule is defined before this module is imported)

RULES = [
    Rule("R2", "relation-flags", UNKNOWN_SINCE,
         "re-encode scripted_relations flags bitsets to 1.20's 1-byte width", r2_relation_flags),
    Rule("R3", "title-names", UNKNOWN_SINCE,
         "move inline title name/adj/pre/article into title_name_data", r3_title_names),
    Rule("R21", "dead-liege-cycles", UNKNOWN_SINCE,
         "drop the recorded liege of dead characters whose liege chain loops", r21_dead_liege_cycles),
    Rule("R20", "unrun-war-coordinators", UNKNOWN_SINCE,
         "drop AI war coordinators that were never run (no stance, supply limit 0) and their war plans",
         r20_unrun_war_coordinators),
    Rule("R22", "impassable-provinces", "1.18.0 (map rework; exact major unverified)",
         "clear old holdings, soldier pools and sieges from provinces the target map makes impassable; move units off",
         r22_impassable_provinces),
    Rule("R6", "dead-titles-report", "1.18.0 (map rework; exact major unverified)",
         "report titles the game no longer defines (no edit)", r6_dead_titles),
    Rule("R23", "nickname-text", UNKNOWN_SINCE,
         "write the nickname's text (nickname_text) after every nickname that lacks it", r23_nickname_text),
    Rule("R25", "successor-keys", UNKNOWN_SINCE,
         "map perks, regiment types and artifact modifiers the game no longer defines to their successors",
         r25_successor_keys),
    Rule("R27", "house-feuds", UNKNOWN_SINCE,
         "carry 1.8's house feuds into 1.20's house relations at the feud level", r27_house_feuds),
    Rule("R28", "marriage-bed", UNKNOWN_SINCE,
         "carry 1.8's 'Rejected From Marriage Bed' into 1.20's no-fertility relation with the spouse",
         r28_marriage_bed),
    Rule("R29", "scheme-thaw", UNKNOWN_SINCE,
         "thaw the old game's frozen schemes, with the secrecy and agent slots 1.20's start-up gives them",
         r29_scheme_thaw),
    Rule("R30", "asset-renames", UNKNOWN_SINCE,
         "point artifact pictures, armour models and coat-of-arms emblems at the names the current game ships",
         r30_asset_renames),
    Rule("R31", "contract-repair", "1.8.1<v<=1.20.1.2",
         "write the missing vassal contract of a ruler whose title answers to a liege (a save edit's leftover)",
         r31_contract_repair),
]
