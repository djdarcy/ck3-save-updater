"""Religion rules for 1.8.1 -> 1.20.1.2: transplant the 1.20 religion databases, remap faiths to rites.

1.20 ("By God Alone") replaced the per-save faith list with three databases --
``religion`` (religions, holy sites), top-level ``faiths`` and ``rites`` -- plus an
``organization_manager``; characters and counties now point at a rite (``rite=``),
not a faith. A fresh 1.20 game instantiates every faith and rite the game defines
(measured: 103 faiths = every faith_type, 152 rites), so these rules copy those
databases from a 1.20 *reference save* and remap the old save's faith ids onto them.

Ids inside the copied blocks are translated, never trusted (measured on the 987
reference): ``religious_head`` and holy-site ``barony`` are title ids (remapped by
title key), ``head_of_rite`` is a character id (84/84 resolve to living characters;
cleared), rite ``cultures`` are culture ids (remapped by template), holy-site
inventories hold artifact ids (cleared), ``saints`` are characters (cleared),
organization coats of arms are reference CoA ids (dropped).

Rule order: R11 R8 R10 R9 R12. R8 records the old faith table in ``ctx.state`` because
it removes the old religion section that R9 and R10 need.
"""

from __future__ import annotations

import re
from collections import Counter

from .. import gamestate as gs
from ..savefile import CK3Save, read_save

NONE = b"4294967295"

# Old faith templates whose 1.20 key does not exist as a rite. catholic/orthodox are NOT overridden:
# in this campaign the schism has happened (1.8.1 has separate catholic/orthodox faiths, each with a
# head), so they map to 1.20's own catholic/orthodox faiths and those faiths' main rites (ruling
# "option B", design session 2026-10-24 ~22:45; the earlier roman_rite/byzantine_rite overrides
# described 1.20's 987 world, not this save). The four Sunni schools only survive as icon names;
# nearest madhhab rite chosen 2026-10-24.
TEMPLATE_TO_RITE = {
    "coptic": "coptic_rite",
    "ashari": "shafii",
    "maturidi": "hanafi",
    "mutazila": "hanafi",
    "muwalladi": "maliki",
}

WOS_SHAPES = ("faith", "rite")


# --------------------------------------------------------------------------- helpers
def _raw(d: bytes, block: gs.Block, key: str) -> bytes | None:
    h = gs.find_keys(d, block, key)
    return d[h[0].value_start:h[0].value_end] if h else None


def _str(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    s = raw.decode("utf-8", errors="replace")
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] == '"' else s


def _entries(d: bytes, path: str):
    try:
        return list(gs.iter_entries(d, *gs.locate(d, path).body))
    except gs.GamestateError:
        return []


def _title_keys(d: bytes) -> dict[str, str]:
    """title id -> title key."""
    return {t.key.decode(): _str(_raw(d, t, "key")) for t in _entries(d, "landed_titles/landed_titles")}


def _culture_keys(d: bytes) -> dict[str, str]:
    """culture id -> culture_template (or name)."""
    out = {}
    for c in _entries(d, "culture_manager/cultures"):
        out[c.key.decode()] = _str(_raw(d, c, "culture_template")) or _str(_raw(d, c, "name"))
    return out


def reference_gamestate(ctx) -> bytes:
    """The reference save's gamestate, read once per context."""
    if "reference_gamestate" not in ctx.state:
        if ctx.reference is None:
            raise ValueError("no reference save (--reference)")
        ctx.state["reference_gamestate"] = read_save(ctx.reference).gamestate
    return ctx.state["reference_gamestate"]


def _skip(rule, why: str):
    return rule.result(extra={"skipped": why})


def _list_tokens(d: bytes, block: gs.Block) -> list[gs.Child]:
    return [c for c in gs.iter_children(d, *block.body) if c.key is None and c.block is None]


# --------------------------------------------------------------------------- R11
def r11_empty_modifiers(save: CK3Save, ctx, rule):
    """Delete modifiers with an empty name: modifier={ modifier="" ... } blocks, "" in modifiers={} lists, type="".

    1.8.1 save: 214 empty modifier blocks (character modifier / timed_modifier), 779
    modifiers={ "" } lists (artifacts) and one type="" -- written by 1.8.1 itself for
    modifiers whose definition was gone; 1.20 rejects each ("Failed to read key reference: :").
    """
    d = save.gamestate
    p = gs.EditPass()
    by = Counter()
    blocks = [m.start(1) for m in re.finditer(rb'(?m)^\t*(modifier)=""', d)]
    for pos, (parent, child) in gs.child_at(d, blocks).items():
        if child.key == b"modifier" and parent.key in (b"modifier", b"timed_modifier"):
            s, e = gs.removal_span(d, parent.start, parent.end)
            p.add(gs.Edit(s, e, b"", rule.name, "modifier block"))
            by["modifier blocks"] += 1
    lists = [m.start() for m in re.finditer(rb"(?<![\w.])modifiers=\{", d)]
    for pos, (parent, child) in gs.child_at(d, lists).items():
        if child.block is None:
            continue
        for tok in _list_tokens(d, child.block):
            if d[tok.start:tok.end] == b'""':
                s, e = gs.removal_span(d, tok.start, tok.end)
                p.add(gs.Edit(s, e, b"", rule.name, "modifiers list"))
                by["modifiers list entries"] += 1
    types = [m.start(1) for m in re.finditer(rb'(?m)^\t*(type)=""', d)]
    for pos, (parent, child) in gs.child_at(d, types).items():
        if child.key == b"type":
            s, e = gs.removal_span(d, child.start, child.end)
            p.add(gs.Edit(s, e, b"", rule.name, f"type in {(parent.key or b'').decode()}"))
            by["type"] += 1
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.edited, edited=c.edited, extra={"by_kind": dict(by)})


# --------------------------------------------------------------------------- R8
def _old_religion_tables(d: bytes) -> tuple[dict, dict, dict]:
    """(faiths id -> info, religions id -> template, holy site id -> template) from a 1.8-layout religion section."""
    faiths = {}
    for f in _entries(d, "religion/faiths"):
        info = {"template": _str(_raw(d, f, "template")), "name": _str(_raw(d, f, "name")),
                "religion": _str(_raw(d, f, "religion")), "religious_head": _str(_raw(d, f, "religious_head")),
                "block": d[f.start:f.end]}
        faiths[f.key.decode()] = info
    religions = {r.key.decode(): _str(_raw(d, r, "template")) for r in _entries(d, "religion/religions")}
    holy = {h.key.decode(): _str(_raw(d, h, "holy_site_template")) for h in _entries(d, "religion/holy_sites")}
    return faiths, religions, holy


def custom_faith_names(d: bytes) -> list[str]:
    """Names of the save's own custom faiths (1.8-layout faiths with a name=); [] when none or not that layout.

    Cheap -- reads only the religion section -- so the CLI can decide its outputs before any rule runs.
    """
    try:
        faiths, _, _ = _old_religion_tables(d)
    except gs.GamestateError:
        return []
    return [f["name"] for _, f in sorted(faiths.items(), key=lambda kv: int(kv[0])) if f.get("name")]


def r8_religion_transplant(save: CK3Save, ctx, rule):
    """Replace religion with the reference's religion + faiths + rites + organization_manager, ids translated.

    Titles by key (religious_head, holy-site barony, clerical electors), cultures by
    template, characters cleared (head_of_rite, saints), artifacts cleared (holy-site
    inventories), reference coats of arms dropped (organizations).
    """
    if ctx.reference is None:
        return _skip(rule, "no reference save (--reference)")
    d = save.gamestate
    ref = reference_gamestate(ctx)
    old_rel = gs.find_section(d, "religion")
    if gs.find_keys(d, old_rel, "faiths"):
        faiths, religions, holy = _old_religion_tables(d)
        ctx.state["old_faiths"], ctx.state["old_religions"], ctx.state["old_holy_sites"] = faiths, religions, holy
    else:
        return _skip(rule, "religion section is already in the 1.20 layout")

    lost: list[dict] = []
    ghw = gs.find_keys(d, old_rel, "great_holy_wars")
    if ghw and ghw[0].block is not None and d[ghw[0].block.open + 1:ghw[0].block.close].strip():
        lost.append({"what": "great_holy_war", "text": d[ghw[0].block.start:ghw[0].block.end].decode(errors="replace")})

    ref_titles = _title_keys(ref)
    our_title_id = {k: i for i, k in _title_keys(d).items() if k}
    ref_cultures = _culture_keys(ref)
    our_culture_id = {}
    for i, k in _culture_keys(d).items():
        our_culture_id.setdefault(k, i)

    def title(raw: bytes) -> bytes | None:
        key = ref_titles.get(raw.decode())
        return our_title_id[key].encode() if key in our_title_id else None

    p = gs.EditPass()
    stats = Counter()
    heads: dict[str, str | None] = {}
    # faiths/database
    for f in _entries(ref, "faiths/database"):
        for c in gs.iter_children(ref, *f.body):
            if c.key == b"religious_head":
                raw = ref[c.value_start:c.value_end]
                if raw != NONE:
                    new = title(raw)
                    p.add(gs.Edit(c.value_start, c.value_end, new or NONE, rule.name, "religious_head"))
                    stats["religious_head remapped" if new else "religious_head cleared"] += 1
            elif c.key in (b"active_clerical_electors", b"inactive_clerical_electors") and c.block is not None:
                for tok in _list_tokens(ref, c.block):
                    new = title(ref[tok.start:tok.end])
                    if new:
                        p.add(gs.Edit(tok.start, tok.end, new, rule.name, "elector"))
                        stats["electors remapped"] += 1
                    else:
                        s, e = gs.removal_span(ref, tok.start, tok.end)
                        p.add(gs.Edit(s, e, b"", rule.name, "elector"))
                        stats["electors dropped"] += 1
            elif c.key == b"saints":
                s, e = gs.removal_span(ref, c.start, c.end)
                p.add(gs.Edit(s, e, b"", rule.name, "saints"))
                stats["faith saints lists removed"] += 1
    fsec = gs.find_section(ref, "faiths")
    for c in gs.find_keys(ref, fsec, "saints"):
        if c.block is not None and ref[c.block.open + 1:c.block.close].strip():
            p.add(gs.Edit(c.block.open + 1, c.block.close, b"\n\t", rule.name, "faiths/saints"))
            stats["faiths/saints emptied"] += 1
    # rites/database
    for r in _entries(ref, "rites/database"):
        for c in gs.iter_children(ref, *r.body):
            if c.key in (b"head_of_rite", b"founder") and ref[c.value_start:c.value_end] != NONE:
                p.add(gs.Edit(c.value_start, c.value_end, NONE, rule.name, c.key.decode()))
                stats[f"{c.key.decode()} cleared"] += 1
            elif c.key == b"cultures" and c.block is not None:
                toks = _list_tokens(ref, c.block)
                keep = 0
                for tok in toks:
                    key = ref_cultures.get(ref[tok.start:tok.end].decode())
                    if key in our_culture_id:
                        p.add(gs.Edit(tok.start, tok.end, our_culture_id[key].encode(), rule.name, "culture"))
                        keep += 1
                        stats["rite cultures remapped"] += 1
                    else:
                        s, e = gs.removal_span(ref, tok.start, tok.end)
                        p.add(gs.Edit(s, e, b"", rule.name, "culture"))
                        stats["rite cultures dropped"] += 1
    # religion/holy_sites
    for h in _entries(ref, "religion/holy_sites"):
        kids = list(gs.iter_children(ref, *h.body))
        bar = next((c for c in kids if c.key == b"barony"), None)
        if bar is not None:
            new = title(ref[bar.value_start:bar.value_end])
            if new:
                p.add(gs.Edit(bar.value_start, bar.value_end, new, rule.name, "barony"))
                stats["holy site baronies remapped"] += 1
            else:
                s, e = gs.removal_span(ref, bar.start, bar.end)
                p.add(gs.Edit(s, e, b"", rule.name, "barony"))
                act = next((c for c in kids if c.key == b"is_active"), None)
                if act is not None:
                    p.add(gs.Edit(act.value_start, act.value_end, b"no", rule.name, "is_active"))
                stats["holy site baronies missing"] += 1
                lost.append({"what": "holy_site_barony", "index": h.key.decode(),
                             "type": _str(_raw(ref, h, "holy_site_type")),
                             "barony": ref_titles.get(ref[bar.value_start:bar.value_end].decode())})
                # the transplant (R14 + R17) may bring this barony in later: R17 re-attaches the site then
                ctx.state.setdefault("holy_sites_without_barony", []).append(
                    {"index": h.key.decode(), "barony": ref_titles.get(ref[bar.value_start:bar.value_end].decode()),
                     "is_active": ref[act.value_start:act.value_end].decode() if act is not None else None})
        for c in kids:
            if c.key == b"total_artifact_rarity":
                s, e = gs.removal_span(ref, c.start, c.end)
                p.add(gs.Edit(s, e, b"", rule.name, "rarity"))
            elif c.key == b"inventory" and c.block is not None:
                for ic in gs.iter_children(ref, *c.block.body):
                    if ic.key == b"equipped":
                        s, e = gs.removal_span(ref, ic.start, ic.end)
                        p.add(gs.Edit(s, e, b"", rule.name, "equipped"))
                    elif ic.key == b"artifacts" and ic.block is not None and _list_tokens(ref, ic.block):
                        p.add(gs.Edit(ic.block.open + 1, ic.block.close, b" ", rule.name, "artifacts"))
                        stats["holy site inventories emptied"] += 1
    # organization_manager
    for o in _entries(ref, "organization_manager/database"):
        for c in gs.find_keys(ref, o, "coat_of_arms_id"):
            s, e = gs.removal_span(ref, c.start, c.end)
            p.add(gs.Edit(s, e, b"", rule.name, "org coa"))
            stats["organization coats dropped"] += 1

    clean = p.apply(ref)
    texts = []
    for sec in ("religion", "faiths", "rites", "organization_manager"):
        try:
            b = gs.find_section(clean, sec)
        except gs.GamestateError:
            continue
        texts.append(clean[b.start:b.end])
    # put them in place of the old religion section; replace any 1.20-layout copies already present
    q = gs.EditPass()
    q.add(gs.Edit(old_rel.start, old_rel.end, b"\n".join(texts), rule.name, "religion transplant"))
    for sec in ("faiths", "rites", "organization_manager"):
        for b in gs.find_sections(d, sec):
            s, e = gs.removal_span(d, b.start, b.end)
            q.add(gs.Edit(s, e, b"", rule.name, f"old {sec}"))
    q.apply_to(save)

    g = save.gamestate
    title_by_id = _title_keys(g)
    for f in _entries(g, "faiths/database"):
        rh = _str(_raw(g, f, "religious_head"))
        heads[_str(_raw(g, f, "tag")) or f.key.decode()] = title_by_id.get(rh) if rh and rh != NONE.decode() else None
    ctx.state["transplanted"] = True
    return rule.result(matched=1, edited=p.count(rule.name).edited + 1,
                       extra={"reference": str(ctx.reference), "stats": dict(stats), "lost": lost,
                              "faith_heads": {k: v for k, v in heads.items() if v}})


# --------------------------------------------------------------------------- shared lookups on the transplanted databases
def _db(g: bytes):
    rites = {r.key.decode(): r for r in _entries(g, "rites/database")}
    faiths = {f.key.decode(): f for f in _entries(g, "faiths/database")}
    rite_by_type = {}
    for i, r in rites.items():
        t = _str(_raw(g, r, "rite_type"))
        if t:
            rite_by_type.setdefault(t, i)
    faith_by_type = {}
    for i, f in faiths.items():
        t = _str(_raw(g, f, "faith_type"))
        if t:
            faith_by_type.setdefault(t, i)
    return rites, faiths, rite_by_type, faith_by_type


def _known_doctrines(g: bytes, ctx) -> set[str]:
    known = set()
    for sec in ("faiths", "rites"):
        try:
            b = gs.find_section(g, sec)
        except gs.GamestateError:
            continue
        known.update(m.group(1).decode() for m in re.finditer(rb"\b(?:doctrine|tenet)=([a-z][a-z0-9_]*)", g[b.open:b.end]))
    if ctx.game_dir is not None:
        for folder in ("doctrine_types", "tenet_types"):
            for f in (ctx.game_dir / "common" / "religion" / folder).glob("*.txt"):
                known.update(m.group(1).decode() for m in
                             re.finditer(rb"(?m)^\s*([a-z][a-z0-9_]*)\s*=\s*\{", f.read_bytes()))
    return known


# --------------------------------------------------------------------------- R10
def _custom_faiths(ctx) -> dict[str, dict]:
    return {i: f for i, f in ctx.state.get("old_faiths", {}).items() if f.get("name")}


def _old_field(block: bytes, key: str) -> bytes | None:
    m = re.search(rb"(?m)^\s*" + key.encode() + rb"=(.*)$", block)
    return m.group(1).strip() if m else None


def _rite_text(rid: int, faith_id: str, origin: str, data_lines: list[bytes], founder: bytes = NONE) -> bytes:
    t3, t4 = b"\t\t\t", b"\t\t\t\t"
    body = b"".join(t4 + line + b"\n" for line in data_lines)
    return (b"\t\t" + str(rid).encode() + b"={\n" +
            t3 + b"faith=" + faith_id.encode() + b"\n" +
            t3 + b"founder=" + founder + b"\n" + t3 + b"head_of_rite=" + NONE + b"\n" +
            t3 + b"origin_rite=" + origin.encode() + b"\n" +
            t3 + b"data={\n" + body + t3 + b"}\n" +
            t3 + b"convert=yes\n" + t3 + b"enabled=yes\n" + t3 + b"override_name=no\n" + t3 + b"source=fallback\n" +
            b"\t\t}\n")


def _identity_lines(block: bytes, tag: str, fervor: bytes) -> list[bytes]:
    lines = [b'tag="' + tag.encode() + b'"']
    for k in ("name", "adjective", "adherent", "adherent_plural", "desc", "color", "icon", "texticon",
              "graphical_faith", "piety_icon_group"):
        v = _old_field(block, k)
        if v is not None:
            lines.append(k.encode() + b"=" + v)
    lines += [b'tenet_background_icon=""', b'tenet_heretical_background_icon=""',
              b'tenet_neutral_background_icon=""', b'tenet_unknown_background_icon=""',
              b"fervor=" + fervor]
    return lines


def _doctrine_lines(block: bytes, known: set[str]) -> tuple[list[bytes], list[bytes], list[str]]:
    tenets, doctrines, dropped = [], [], []
    for m in re.finditer(rb'(?m)^\s*doctrine="?([a-z][a-z0-9_]*)"?\s*$', block):
        key = m.group(1).decode()
        if known and key not in known:
            dropped.append(key)
        elif key.startswith("tenet_"):
            tenets.append(b"tenet=" + m.group(1))
        else:
            doctrines.append(b"doctrine=" + m.group(1))
    return tenets, doctrines, dropped


# a faith's dated history: changes={ 977.2.1="..." ... } -- braces inside the quoted text do not close it
_CHANGES = re.compile(rb'(?m)^\s*changes=\{((?:[^{}"]|"(?:[^"\\]|\\.)*")*)\}')
_CHANGE_DATE = re.compile(rb'(?:^|\s)\d+\.\d+\.\d+=')


def _character_section(g: bytes, cid: str) -> str | None:
    """'living' or 'dead_unprunable' when character cid is an entry there (entries sit at column 0), else None."""
    pat = re.compile(rb"\n" + re.escape(cid.encode()) + rb"=\{")
    for sec in ("living", "dead_unprunable"):
        b = next(gs.find_sections(g, sec), None)
        if b is not None and pat.search(g, b.open, b.close):
            return sec
    return None


def _insert_before_close(g: bytes, block: gs.Block, payload: bytes, p: gs.EditPass, rule: str, note: str):
    line_start = g.rfind(b"\n", 0, block.close) + 1
    p.add(gs.Edit(line_start, line_start, payload, rule, note))


def r10_custom_faith(save: CK3Save, ctx, rule):
    """Bring custom faiths (the save's own, e.g. 102 "Way of Scarcity") into 1.20, as a faith or as a rite.

    shape 'faith': a new faith (historical=no) in the Christian religion with its own main
    rite (the reference's dynamic-rite shape), its doctrines/tenets, its saved fervor and
    religious head (a title in this save's numbering), and its holy sites mapped by
    holy_site_template onto the transplanted list; origin= the faith its template rite
    belongs to, and its dated changes={} history. shape 'rite': a new rite of the
    parent faith of its template's rite (insular_celtic -> christian_faith), origin_rite =
    that rite, fervor 50, no holy sites (rites have none), no change history (reported lost).
    Both shapes: founder= on the (main) rite when that character is still in the save.
    """
    if not ctx.state.get("transplanted"):
        return _skip(rule, "needs R8 (religion transplant) in the same run")
    shape = ctx.wos_shape
    if shape not in WOS_SHAPES:
        raise ValueError(f"wos shape must be one of {WOS_SHAPES}, not {shape!r}")
    g = save.gamestate
    rites, faiths, rite_by_type, faith_by_type = _db(g)
    known = _known_doctrines(g, ctx)
    old_holy = ctx.state.get("old_holy_sites", {})
    hs_entries = _entries(g, "religion/holy_sites")
    hs_by_type = {}
    for h in hs_entries:
        hs_by_type.setdefault(_str(_raw(g, h, "holy_site_type")), h)
    rel_entries = _entries(g, "religion/religions")
    p = gs.EditPass()
    out = {}
    lost = []
    next_rite = max(int(i) for i in rites) + 1
    next_faith = max(int(i) for i in faiths) + 1
    orgs = _entries(g, "organization_manager/database")
    next_org = max((int(o.key) for o in orgs), default=-1) + 1
    custom = ctx.state.setdefault("custom_rites", {})
    for old_id, info in sorted(_custom_faiths(ctx).items(), key=lambda kv: int(kv[0])):
        block = info["block"]
        t = info["template"]
        parent_rite = rite_by_type.get(t) or rite_by_type.get(f"{t}_rite")
        if parent_rite is not None:
            parent_faith = _str(_raw(g, rites[parent_rite], "faith"))
        elif t in faith_by_type:
            parent_faith = faith_by_type[t]
            parent_rite = _str(_raw(g, faiths[parent_faith], "main_rite"))
        else:
            out[old_id] = {"error": f"template {t!r} has no 1.20 rite or faith"}
            continue
        tenets, doctrines, dropped = _doctrine_lines(block, known)
        head = _old_field(block, "religious_head") or NONE
        title_by_id = _title_keys(g)
        # lineage: the founder (a character id in this save's numbering, kept only if the character is still
        # in the save) goes on the rite -- 1.20 keeps founder= on rites, not faiths; the dated change history
        # goes on the faith (1.20 faiths keep changes={}; rites have no such field)
        founder_id = (_old_field(block, "founder") or NONE).decode()
        founder_in = _character_section(g, founder_id) if founder_id != NONE.decode() else None
        founder = founder_id.encode() if founder_in else NONE
        cm = _CHANGES.search(block)
        changes = cm.group(1).strip() if cm else b""
        n_changes = len(_CHANGE_DATE.findall(changes))
        rec = {"name": info["name"], "template": t, "shape": shape, "dropped_doctrines": dropped,
               "religious_head": {"id": head.decode(), "title": title_by_id.get(head.decode())},
               "tenets": [x[6:].decode() for x in tenets], "doctrines": len(doctrines),
               "founder": {"id": founder_id, "kept": founder_in is not None, "found_in": founder_in},
               "changes_entries": n_changes}
        if founder_id != NONE.decode() and founder_in is None:
            lost.append({"what": "founder", "faith": info["name"], "character": founder_id,
                         "why": "not in living or dead_unprunable"})
        if shape == "rite":
            rid = next_rite
            next_rite += 1
            data = _identity_lines(block, f"dynamic_rite_{rid + 1}", b"50") + [b"religious_head=" + NONE] + tenets + doctrines
            _insert_before_close(g, gs.locate(g, "rites/database"),
                                 _rite_text(rid, parent_faith, parent_rite, data, founder), p, rule.name, "custom rite")
            custom[old_id] = str(rid)
            rec.update(rite_id=rid, faith_id=parent_faith, origin_rite=parent_rite)
            if n_changes:
                lost.append({"what": "faith_changes", "faith": info["name"], "entries": n_changes,
                             "why": "1.20 rites keep no change history (the faith shape carries it)"})
        else:
            fid, rid, oid = next_faith, next_rite, next_org
            next_faith, next_rite, next_org = fid + 1, rid + 1, oid + 1
            fervor = _old_field(block, "fervor") or b"50"
            # holy sites: old index -> template -> index in the transplanted list
            holy_idx = []
            hs = re.search(rb"holy_sites=\{([^}]*)\}", block)
            for tok in (hs.group(1).split() if hs else []):
                tmpl = old_holy.get(tok.decode())
                h = hs_by_type.get(tmpl)
                if h is None:
                    lost.append({"what": "holy_site_type", "faith": info["name"], "template": tmpl,
                                 "why": "not a 1.20 holy site type"})
                    continue
                holy_idx.append(h.key.decode())
                fl = gs.find_keys(g, h, "faiths")
                if fl and fl[0].block is not None:
                    p.add(gs.Edit(fl[0].block.close, fl[0].block.close, str(fid).encode() + b" ", rule.name, "holy site faith"))
                else:   # a holy site no faith claims has no faiths list at all (iona in the 987 reference)
                    _insert_before_close(g, h, b"\t\t\tfaiths={ " + str(fid).encode() + b" }\n", p, rule.name,
                                         "holy site faiths list")
            christian = next((r for r in rel_entries if _str(_raw(g, r, "religion_type")) ==
                              (ctx.state.get("old_religions", {}).get(info["religion"]) or "christianity_religion")), None)
            christian = christian or next((r for r in rel_entries if _str(_raw(g, r, "religion_type")) == "christianity_religion"), None)
            rel_id = christian.key.decode() if christian is not None else "0"
            t3 = b"\t\t\t"
            faith_lines = [b"religion=" + rel_id.encode(), b"main_rite=" + str(rid).encode(),
                           b"organization=" + str(oid).encode(),
                           b"holy_sites={ " + b" ".join(x.encode() for x in holy_idx) + b" }",
                           b"changes={"] + ([b"\t" + changes] if changes else []) + [
                           b"}",
                           # origin is a faith id (1.20's catholic/orthodox say origin=<christian_faith>);
                           # the template rite's faith is the nearest 1.20 has to "came from insular_celtic"
                           b"origin=" + parent_faith.encode(),
                           b"historical=no"]
            faith_lines += _identity_lines(block, f"dynamic_faith_{fid}", fervor)
            faith_lines += [b"religious_head=" + head] + tenets + doctrines
            ftext = b"\t\t" + str(fid).encode() + b"={\n" + b"".join(t3 + x + b"\n" for x in faith_lines) + b"\t\t}\n"
            _insert_before_close(g, gs.locate(g, "faiths/database"), ftext, p, rule.name, "custom faith")
            data = _identity_lines(block, f"dynamic_rite_{rid + 1}", fervor) + [b"religious_head=" + NONE] + tenets + doctrines
            _insert_before_close(g, gs.locate(g, "rites/database"), _rite_text(rid, str(fid), NONE.decode(), data, founder),
                                 p, rule.name, "custom faith main rite")
            org = b"\t\t" + str(oid).encode() + b"={\n\t\t\tfaith=" + str(fid).encode() + b"\n\t\t}\n"
            _insert_before_close(g, gs.locate(g, "organization_manager/database"), org, p, rule.name, "organization")
            if christian is not None:
                fl = gs.find_keys(g, christian, "faiths")[0]
                p.add(gs.Edit(fl.block.close, fl.block.close, str(fid).encode() + b" ", rule.name, "religion faiths"))
            custom[old_id] = str(rid)
            rec.update(faith_id=fid, rite_id=rid, organization_id=oid, religion_id=rel_id, fervor=fervor.decode(),
                       origin_faith=parent_faith,
                       holy_sites={x: _str(_raw(g, hs_entries[int(x)], "holy_site_type")) if int(x) < len(hs_entries)
                                   else None for x in holy_idx})
        p.count(rule.name).matched += 1
        out[old_id] = rec
    p.apply_to(save)
    return rule.result(matched=p.count(rule.name).matched, edited=p.count(rule.name).edited,
                       extra={"shape": shape, "custom": out, "lost": lost})


# --------------------------------------------------------------------------- R9
CHAR_SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")


def faith_to_rite_table(g: bytes, ctx) -> dict[str, dict]:
    """old faith id -> {template, rite_id, rite_type, faith_id, faith_type} on the transplanted databases."""
    rites, faiths, rite_by_type, faith_by_type = _db(g)
    custom = ctx.state.get("custom_rites", {})
    table = {}
    for fid, info in ctx.state.get("old_faiths", {}).items():
        t = info["template"]
        rid, how = None, None
        if fid in custom:
            rid, how = custom[fid], "custom (R10)"
        elif t in TEMPLATE_TO_RITE and TEMPLATE_TO_RITE[t] in rite_by_type:
            rid, how = rite_by_type[TEMPLATE_TO_RITE[t]], f"override -> {TEMPLATE_TO_RITE[t]}"
        elif t in rite_by_type:
            rid, how = rite_by_type[t], "rite_type"
        elif f"{t}_rite" in rite_by_type:
            rid, how = rite_by_type[f"{t}_rite"], "<template>_rite"
        elif t in faith_by_type:
            rid, how = _str(_raw(g, faiths[faith_by_type[t]], "main_rite")), "faith_type main_rite"
        row = {"template": t, "name": info.get("name"), "how": how, "rite_id": rid}
        if rid is not None and rid in rites:
            row["rite_type"] = _str(_raw(g, rites[rid], "rite_type"))
            row["faith_id"] = _str(_raw(g, rites[rid], "faith"))
            row["faith_type"] = _str(_raw(g, faiths[row["faith_id"]], "faith_type")) if row["faith_id"] in faiths else None
        table[fid] = row
    return table


def r9_faith_to_rite(save: CK3Save, ctx, rule):
    """Replace faith=<old id> with rite=<new id> on characters, counties and holy orders; remap faith/religion variables."""
    if not ctx.state.get("transplanted"):
        return _skip(rule, "needs R8 (religion transplant) in the same run")
    g = save.gamestate
    table = faith_to_rite_table(g, ctx)
    p = gs.EditPass()
    counts = Counter()
    unresolved = Counter()

    living_by_rite = Counter()

    def swap(block: gs.Block, where: str):
        for c in gs.find_keys(g, block, "faith"):
            old = g[c.value_start:c.value_end].decode()
            row = table.get(old)
            if row is None or row["rite_id"] is None:
                unresolved[f"{where}:{old}"] += 1
                continue
            p.add(gs.Edit(c.key_start, c.value_end, b"rite=" + row["rite_id"].encode(), rule.name, where))
            counts[where] += 1
            if where == "living":
                living_by_rite[row["rite_id"]] += 1

    # religious heads: an old faith's head title carries to the 1.20 faith it maps to when that faith has
    # none (titles keep this save's numbering, so the id is copied as-is); first old faith wins a conflict
    rites_db, faiths_db, _, _ = _db(g)
    title_key = _title_keys(g)
    assigned: dict[str, str] = {}
    heads_carried, head_conflicts = {}, []
    for old_id in sorted(ctx.state.get("old_faiths", {}), key=int):
        head = ctx.state["old_faiths"][old_id].get("religious_head")
        fid = (table.get(old_id) or {}).get("faith_id")
        if not head or head == NONE.decode() or fid is None or fid not in faiths_db:
            continue
        if fid in assigned:
            if assigned[fid] != head:
                head_conflicts.append({"faith_id": fid, "kept": title_key.get(assigned[fid]), "dropped": title_key.get(head),
                                       "dropped_from_old_faith": old_id})
            continue
        fb = faiths_db[fid]
        cur = gs.find_keys(g, fb, "religious_head")
        if cur and g[cur[0].value_start:cur[0].value_end] not in (NONE, head.encode()):
            assigned[fid] = g[cur[0].value_start:cur[0].value_end].decode()     # the reference already has a head
            continue
        assigned[fid] = head
        if cur and g[cur[0].value_start:cur[0].value_end] == NONE:
            p.add(gs.Edit(cur[0].value_start, cur[0].value_end, head.encode(), rule.name, "religious_head"))
        elif not cur:
            _insert_before_close(g, fb, b"\t\t\treligious_head=" + head.encode() + b"\n", p, rule.name, "religious_head")
        heads_carried[_str(_raw(g, fb, "tag")) or fid] = {"title": title_key.get(head), "from_old_faith": old_id}

    for sec in CHAR_SECTIONS:
        for e in _entries(g, sec):
            swap(e, sec)
    for e in _entries(g, "county_manager/counties"):
        swap(e, "counties")
    for e in _entries(g, "holy_orders/holy_orders"):
        swap(e, "holy_orders")
    # saved scopes / variables: type=faith identity=<faith id>, type=religion identity=<religion id>
    new_religion = {}
    for r in _entries(g, "religion/religions"):
        new_religion[_str(_raw(g, r, "religion_type"))] = r.key.decode()
    old_rel = ctx.state.get("old_religions", {})
    for m in re.finditer(rb"type=(faith|religion)(\s+identity=)(\d+)", g):
        kind, old = m.group(1).decode(), m.group(3).decode()
        if kind == "faith":
            new = (table.get(old) or {}).get("faith_id")
        else:
            new = new_religion.get(old_rel.get(old))
        if new is None:
            unresolved[f"variable type={kind}:{old}"] += 1
            continue
        p.add(gs.Edit(m.start(3), m.end(3), new.encode(), rule.name, f"variable {kind}"))
        counts[f"variable type={kind}"] += 1
    p.apply_to(save)
    ctx.state["faith_to_rite"] = table
    g = save.gamestate
    title_key = _title_keys(g)
    faith_heads = {}
    for f in _entries(g, "faiths/database"):
        h = _str(_raw(g, f, "religious_head"))
        faith_heads[_str(_raw(g, f, "tag")) or f.key.decode()] = title_key.get(h) if h and h != NONE.decode() else None
    return rule.result(matched=sum(counts.values()), edited=p.count(rule.name).edited,
                       extra={"by_place": dict(counts), "unresolved": dict(unresolved.most_common(30)),
                              "heads_carried": heads_carried, "head_conflicts": head_conflicts,
                              "faith_heads": faith_heads, "living_explicit_by_rite": dict(living_by_rite),
                              "table": table})


# --------------------------------------------------------------------------- R12
def r12_faithless_rite(save: CK3Save, ctx, rule):
    """Give every character without faith=/rite= a rite: house head's, else dynasty head's, else employer's
    (or the employer's house head's), else the player's. 1.20 writes rite= on 100% of characters."""
    if not ctx.state.get("transplanted"):
        return _skip(rule, "needs R8 (religion transplant) in the same run")
    g = save.gamestate
    chars = {}
    for sec in CHAR_SECTIONS:
        for e in _entries(g, sec):
            kids = {c.key: c for c in gs.iter_children(g, *e.body) if c.key in (b"rite", b"dynasty_house", b"birth", b"court_data")}
            emp = None
            if b"court_data" in kids and kids[b"court_data"].block is not None:
                emp = _str(_raw(g, kids[b"court_data"].block, "employer"))
            chars[e.key.decode()] = {
                "rite": g[kids[b"rite"].value_start:kids[b"rite"].value_end].decode() if b"rite" in kids else None,
                "house": g[kids[b"dynasty_house"].value_start:kids[b"dynasty_house"].value_end].decode() if b"dynasty_house" in kids else None,
                "employer": emp, "birth": kids.get(b"birth"), "entry": e, "section": sec}
    houses = {h.key.decode(): (_str(_raw(g, h, "head_of_house")), _str(_raw(g, h, "dynasty")))
              for h in _entries(g, "dynasties/dynasty_house")}
    dyn_head = {x.key.decode(): _str(_raw(g, x, "dynasty_head")) for x in _entries(g, "dynasties/dynasties")}
    player = _str(_raw(g, gs.find_section(g, "played_character"), "character")) if list(gs.find_sections(g, "played_character")) else None
    player_rite = (chars.get(player) or {}).get("rite")

    def house_rite(cid):
        c = chars.get(cid or "")
        if not c or not c["house"]:
            return None
        head, dyn = houses.get(c["house"], (None, None))
        return (chars.get(head or "") or {}).get("rite"), dyn

    p = gs.EditPass()
    took = Counter()
    inherited_by_rite = Counter()
    for cid, c in chars.items():
        if c["rite"] is not None:
            continue
        rite, how = None, None
        hr = house_rite(cid)
        if hr and hr[0]:
            rite, how = hr[0], "house head"
        elif hr and hr[1] and (chars.get(dyn_head.get(hr[1]) or "") or {}).get("rite"):
            rite, how = chars[dyn_head[hr[1]]]["rite"], "dynasty head"
        elif c["employer"] and (chars.get(c["employer"]) or {}).get("rite"):
            rite, how = chars[c["employer"]]["rite"], "employer"
        elif c["employer"] and house_rite(c["employer"]) and house_rite(c["employer"])[0]:
            rite, how = house_rite(c["employer"])[0], "employer's house head"
        elif player_rite:
            rite, how = player_rite, "player"
        if rite is None:
            took["none found"] += 1
            continue
        took[f"{how} ({c['section']})"] += 1
        if c["section"] == "living":
            inherited_by_rite[rite] += 1
        anchor = c["birth"]
        e = c["entry"]
        if anchor is not None:
            ls = g.rfind(b"\n", 0, anchor.start) + 1
            indent = g[ls:anchor.start]
            p.add(gs.Edit(anchor.end, anchor.end, b"\n" + indent + b"rite=" + rite.encode(), rule.name, how))
        else:
            p.insert(e, "start", b"\n\trite=" + rite.encode(), rule.name, how)
    # counties without a rite (1.8.1 wrote faith=4294967295 on 2): the county holder's rite, else the player's
    holder_of = {}
    for t in _entries(g, "landed_titles/landed_titles"):
        k = _str(_raw(g, t, "key"))
        h = _str(_raw(g, t, "holder"))
        if k and h:
            holder_of[k] = h
    for e in _entries(g, "county_manager/counties"):
        kids = {c.key: c for c in gs.iter_children(g, *e.body) if c.key in (b"rite", b"faith")}
        if b"rite" in kids:
            continue
        rite = (chars.get(holder_of.get(e.key.decode(), "")) or {}).get("rite")
        how = "county holder" if rite else "player (county)"
        rite = rite or player_rite
        if rite is None:
            took["county: none found"] += 1
            continue
        took[how] += 1
        if b"faith" in kids:      # faith=4294967295 left by R9 -> replace it
            f = kids[b"faith"]
            p.add(gs.Edit(f.key_start, f.value_end, b"rite=" + rite.encode(), rule.name, how))
        else:
            p.insert(e, "end", b"\t\t\trite=" + rite.encode() + b"\n\t\t", rule.name, how)
    p.apply_to(save)
    # the check the design asks for: every character has a rite, every rite id exists
    g = save.gamestate
    rite_ids = {r.key.decode() for r in _entries(g, "rites/database")}
    missing = dangling = 0
    for sec in CHAR_SECTIONS:
        for e in _entries(g, sec):
            r = gs.find_keys(g, e, "rite")
            if not r:
                missing += 1
            elif g[r[0].value_start:r[0].value_end].decode() not in rite_ids:
                dangling += 1
    for e in _entries(g, "county_manager/counties"):
        r = gs.find_keys(g, e, "rite")
        if not r:
            missing += 1
        elif g[r[0].value_start:r[0].value_end].decode() not in rite_ids:
            dangling += 1
    return rule.result(matched=sum(took.values()), edited=p.count(rule.name).edited,
                       extra={"took": dict(took), "check": {"without_rite": missing, "dangling_rite_ids": dangling},
                              "living_inherited_by_rite": dict(inherited_by_rite),
                              "assumptions": ["a character without faith= in 1.8.1 follows its house head's faith "
                                              "(covers all; 82% of characters WITH faith= match their house head)"]})


from . import Rule  # noqa: E402  (Rule is defined before this module is imported)

RULES = [
    Rule("R8", "religion-transplant", "1.20.0 (By God Alone: faiths/rites databases)",
         "replace religion with a 1.20 reference's religion/faiths/rites/organizations, ids translated",
         r8_religion_transplant),
    Rule("R9", "faith-to-rite", "1.20.0 (characters and counties point at a rite)",
         "replace faith=<old id> with rite=<new id>; remap faith/religion variables", r9_faith_to_rite, requires=("R8", "R10")),
    Rule("R10", "custom-faith", "1.20.0",
         "carry the save's own custom faiths (e.g. Way of Scarcity) as a faith or a rite", r10_custom_faith,
         requires=("R8",)),
    Rule("R11", "empty-modifiers", "1.8.1<v<=1.20.1.2",
         'delete modifiers with an empty name (modifier="", "" in modifiers lists, type="")', r11_empty_modifiers),
    Rule("R12", "faithless-rite", "1.20.0 (rite on every character)",
         "give characters without a faith their house head's rite (fallbacks reported)", r12_faithless_rite,
         requires=("R8", "R9")),
]
