"""Subtractive rules (and the version bump) for bringing a 1.8.1 save to CK3 1.20.1.2.

Each rule cites the measurement it rests on. "1.8.1 save" = the Beidh 987.10.27
save; "1.20 reference" = ref_1_20_persia_867, a fresh 1.20.1.2 manual save.
"""

from __future__ import annotations

import base64
import re
from collections import Counter
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
                        lossy.append({"offset": f.value_start, "value": raw.decode(errors="replace"), "why": "not base64"})
                        continue
                    p.count(rule.name).matched += 1
                    values[raw.decode()] += 1
                    if len(bits) == TARGET_FLAG_BYTES:
                        continue
                    if any(bits[TARGET_FLAG_BYTES:]):
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


def r21_dead_liege_cycles(save: CK3Save, ctx, rule) -> object:
    """Drop liege=/liege_title= from the dead_data of every dead character on a liege cycle of two or more.

    1.8.1 save: one cycle, Al-Mansur (2974, d. 775) -> Al-Mahdi (3595, d. 785) -> Al-Mansur, written by the 1.8.1
    game's history setup (both were independent caliphs). The 1.20 game writes a dead independent ruler as his
    own liege (3,513 such in its own 989 autosave) and never a longer loop; a fresh 1.20 game records no liege for
    them at all. A walk up a liege chain ends only where the chain ends (djdarcy, 2026-10-27: fix it in case some
    part of the game walks the history graph). Self-lieges are left as the game writes them.
    """
    d = save.gamestate
    lieges = dead_lieges(d)
    parent = {c: l for c, (l, _) in lieges.items() if l != c and l in lieges}
    members = [c for cyc in gs.parent_cycles(parent) if len(cyc) > 1 for c in cyc]
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
]
