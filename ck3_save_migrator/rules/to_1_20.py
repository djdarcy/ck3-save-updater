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


# --------------------------------------------------------------------------- R1
def r1_converging(save: CK3Save, ctx, rule) -> object:
    """Delete converging={...} inside every opinions/active_opinions/*/temporary_opinion.

    1.8.1 save: 76,433 converging blocks, all inside temporary_opinion; 1.20 reference: 0.
    The 1.20 parser rejects each one ("Unexpected token: converging").
    """
    d = save.gamestate
    p = gs.EditPass()
    for e in _opinion_entries(d):
        for to in gs.find_keys(d, e, "temporary_opinion"):
            if to.block is not None and p.delete_key(d, to.block, "converging", rule.name):
                p.count(rule.name).matched += 1
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited)


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


# --------------------------------------------------------------------------- R4
def r4_game_rule_blanks(save: CK3Save, ctx, rule) -> object:
    """Delete empty "" tokens from game_rules settings/setting, in meta_data and in the top-level section.

    1.8.1 save: 69 blanks in meta_data/game_rules/settings and 69 in game_rules/setting;
    1.20 reference: 0 and 0. Both versions use 'settings' in meta_data and 'setting' at
    top level, so no key is renamed.
    """
    d = save.gamestate
    p = gs.EditPass()
    where = {}
    blocks = []
    try:
        blocks.append(("meta_data", gs.find_child(d, gs.find_section(d, "meta_data"), "game_rules")))
    except gs.GamestateError:
        pass
    blocks += [("top-level", b) for b in gs.find_sections(d, "game_rules")]
    for label, gr in blocks:
        n = 0
        for lst in gs.iter_children(d, *gr.body):
            if lst.key not in (b"settings", b"setting") or lst.block is None:
                continue
            p.count(rule.name).matched += 1
            for v in gs.iter_children(d, *lst.block.body):
                if v.key is None and v.block is None and d[v.start:v.end] == b'""':
                    s, e = gs.removal_span(d, v.start, v.end)
                    p.add(gs.Edit(s, e, b"", rule.name, label))
                    n += 1
        where[label] = where.get(label, 0) + n
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited, extra={"blanks_removed": where})


# --------------------------------------------------------------------------- R5
_EMPTY_KEY_LINE = re.compile(rb"(?m)^[ \t]*=")


def r5_empty_keys(save: CK3Save, ctx, rule) -> object:
    """Delete map entries whose key is empty ("=-5000.1.1"), wherever they occur.

    1.8.1 save: 99 -- 98 in decision_cooldowns, 1 in interaction_cooldowns; 1.20
    reference: 0. The 1.20 parser rejects each ("Invalid date string ... empty").
    """
    d = save.gamestate
    p = gs.EditPass()
    candidates = [m.end() - 1 for m in _EMPTY_KEY_LINE.finditer(d)]
    found = gs.child_at(d, candidates)
    parents: Counter = Counter()
    for pos in candidates:
        hit = found.get(pos)
        if hit is None:
            continue
        parent, child = hit
        if child.key != b"":
            continue
        p.count(rule.name).matched += 1
        parents[(parent.key or b"{}").decode()] += 1
        s, e = gs.removal_span(d, child.start, child.end)
        p.add(gs.Edit(s, e, b"", rule.name, (parent.key or b"").decode()))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"by_parent": dict(parents), "candidates": len(candidates)})


# --------------------------------------------------------------------------- R6
_TITLE_DEF = re.compile(rb"(?<![\w.])([hekdcb]_[\w\-']+)\s*=\s*\{")
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


# --------------------------------------------------------------------------- R7
def r7_version_bump(save: CK3Save, ctx, rule) -> object:
    """Set meta_data version and save_game_version (and portraits_version only if given) to the target.

    1.20 reference: version="1.20.1.2", save_game_version=18, portraits_version=5.
    Both meta copies change together (the plaintext block is derived from the gamestate's).
    """
    d = save.gamestate
    p = gs.EditPass()
    meta = gs.find_section(d, "meta_data")
    targets = {b"version": b'"' + ctx.target_version.encode() + b'"',
               b"save_game_version": str(ctx.target_save_game_version).encode()}
    if ctx.portraits_version is not None:
        targets[b"portraits_version"] = str(ctx.portraits_version).encode()
    before = {}
    for c in gs.iter_children(d, *meta.body):
        if c.key in targets:
            p.count(rule.name).matched += 1
            before[c.key.decode()] = d[c.value_start:c.value_end].decode()
            if d[c.value_start:c.value_end] != targets[c.key]:
                p.add(gs.Edit(c.value_start, c.value_end, targets[c.key], rule.name))
    p.apply_to(save)
    c = p.count(rule.name)
    return rule.result(matched=c.matched, edited=c.edited,
                       extra={"before": before, "after": {k.decode(): v.decode() for k, v in targets.items()}})


from . import Rule  # noqa: E402  (circular-safe: Rule is defined before this module is imported)

RULES = [
    Rule("R1", "opinions-converging", UNKNOWN_SINCE,
         "delete converging={} in opinions temporary_opinion blocks", r1_converging),
    Rule("R2", "relation-flags", UNKNOWN_SINCE,
         "re-encode scripted_relations flags bitsets to 1.20's 1-byte width", r2_relation_flags),
    Rule("R3", "title-names", UNKNOWN_SINCE,
         "move inline title name/adj/pre/article into title_name_data", r3_title_names),
    Rule("R4", "game-rule-blanks", UNKNOWN_SINCE,
         'delete empty "" entries from game_rules settings lists', r4_game_rule_blanks),
    Rule("R5", "empty-keys", UNKNOWN_SINCE,
         "delete map entries with an empty key (=-5000.1.1)", r5_empty_keys),
    Rule("R6", "dead-titles-report", "1.18.0 (map rework; exact major unverified)",
         "report titles the game no longer defines (no edit)", r6_dead_titles),
    Rule("R7", "version-bump", "n/a",
         "set meta_data version/save_game_version to the target", r7_version_bump),
]
