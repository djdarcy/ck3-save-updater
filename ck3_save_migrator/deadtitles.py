"""R15's input: the save's titles the target version no longer has, their successors, and the clean rule.

A save from an older version can hold titles the target version's map no longer defines (1.8.1 -> 1.20: 96, most
on the old Chinese and Tibetan frontier), and baronies the target moved to another province (10). Both are
settled by place: what the target version calls the land the save's title covered.

* a barony's successor is the target barony on the barony's old province (none: the province is wasteland);
* a county's or higher title's successors are the target parents, one tier up, of its de jure children's
  successors (old children from the old version's map);
* a title the target defines only under another tier's prefix (e_india -> h_india) maps by key;
* a MOVED barony (defined in both, on another province) is renamed to the target barony on its old province:
  no province entry moves (place-faithful, design ruling 2026-10-25 10:05).

The clean rule (design R15, approved): a mapping is clean iff it has exactly one successor, the successor's
land under the target map is the title's land under the old map, no other title maps to the same successor,
and the successor is not a key the save keeps. Clean -> the save's title is renamed to the successor (its id and
holder kept). Anything else is reported with its class: unclean (split, land mismatch, shared or occupied
successor), wasteland, by-key, dropped.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import translate as T

_TOK = re.compile(r'"[^"]*"|[{}=]|[^\s{}="]+')
_TITLE = re.compile(r"^[hekdcb]_")


def title_tree(landed_titles_dir: Path) -> tuple[dict[str, str | None], dict[str, int]]:
    """From a version's ``common/landed_titles`` folder: key -> de jure parent key, and barony -> province."""
    parent: dict[str, str | None] = {}
    prov: dict[str, int] = {}
    for p in sorted(Path(landed_titles_dir).glob("*.txt")):
        text = re.sub(r"#[^\n]*", "", p.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8", "replace"))
        toks = _TOK.findall(text)
        stack: list[str | None] = []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t == "{":
                stack.append(None)
            elif t == "}":
                if stack:
                    stack.pop()
            elif i + 2 < len(toks) and toks[i + 1] == "=" and toks[i + 2] == "{" and _TITLE.match(t):
                titles = [k for k in stack if k]
                parent.setdefault(t, titles[-1] if titles else None)
                stack.append(t)
                i += 3
                continue
            elif t == "province" and i + 2 < len(toks) and toks[i + 1] == "=" and toks[i + 2].isdigit():
                titles = [k for k in stack if k]
                if titles and titles[-1].startswith("b_"):
                    prov.setdefault(titles[-1], int(toks[i + 2]))
            i += 1
    return parent, prov


@dataclass
class Mapping:
    key: str                     # the save's title key
    save_id: int
    holder: int | None
    kind: str                    # "dead" (not defined by the target) or "moved" (a barony on another province)
    successors: list[str] = field(default_factory=list)
    cls: str = ""                # clean | unclean | wasteland | by_key | dropped
    reason: str = ""

    @property
    def outcome(self) -> str:
        """What happened to the title and its land, in the report's words."""
        held = self.holder is not None
        if self.cls == "clean":
            return f"kept by the campaign's holder as {self.successors[0]}" if held else \
                f"renamed to {self.successors[0]} (unheld)"
        if self.cls in ("unclean",):
            who = "lost by the campaign's holder" if held else "removed (unheld)"
            return f"{who}; the reference's holders take {', '.join(self.successors)}"
        if self.cls == "wasteland":
            return "lost by the campaign's holder: the land is wasteland in the target" if held else \
                "removed: wasteland in the target"
        if self.cls == "by_key":
            return f"removed (unheld); the target's {', '.join(self.successors)} takes its place"
        return "removed: no land and no successor in the target"

    def row(self) -> dict:
        return {"key": self.key, "kind": self.kind, "class": self.cls, "successors": self.successors,
                "holder": self.holder, "reason": self.reason, "outcome": self.outcome}


def classify(save: bytes, old_dir: Path, new_dir: Path, conversion: set[str] = frozenset()) -> list[Mapping]:
    """Every dead or moved title of the save, with successors and class. ``old_dir``/``new_dir`` are the two
    versions' ``common/landed_titles`` folders; ``conversion`` holds keys the target converts by itself."""
    old_parent, old_prov = title_tree(old_dir)
    new_parent, new_prov = title_tree(new_dir)
    on_prov = {p: b for b, p in new_prov.items()}
    new_children: dict[str, list[str]] = defaultdict(list)
    for k, par in new_parent.items():
        if par:
            new_children[par].append(k)
    old_children: dict[str, list[str]] = defaultdict(list)
    for k, par in old_parent.items():
        if par:
            old_children[par].append(k)

    def land_old(k: str) -> set[int]:
        if k.startswith("b_"):
            return {old_prov[k]} if k in old_prov else set()
        return set().union(*(land_old(c) for c in old_children.get(k, []))) if old_children.get(k) else set()

    def land_new(k: str) -> set[int]:
        if k.startswith("b_"):
            return {new_prov[k]} if k in new_prov else set()
        return set().union(*(land_new(c) for c in new_children.get(k, []))) if new_children.get(k) else set()

    def successors(k: str) -> Counter:
        if k.startswith("b_"):
            s = on_prov.get(old_prov.get(k))
            return Counter([s] if s else [])
        out = Counter()
        for c in old_children.get(k, []):
            for s, n in successors(c).items():
                up = new_parent.get(s)
                if up:
                    out[up] += n
        return out

    saved = {}
    for i, e in T.entries(save, "landed_titles/landed_titles"):
        k = T._depth0(save, e, T._KEY)
        if k is None:
            continue
        m = re.search(rb"\n\tholder=(\d+)", save[e.open:min(e.close, e.open + 4096)])
        saved[k.decode()] = (i, int(m.group(1)) if m else None)

    out: list[Mapping] = []
    for k, (i, h) in saved.items():
        if k.startswith("x_") or k in conversion:
            continue
        if k not in new_parent:                                     # dead
            mp = Mapping(k, i, h, "dead")
            same = [p + k[1:] for p in "hekdcb" if p + k[1:] in new_parent and p + k[1:] != k]
            sc = successors(k)
            mp.successors = [s for s, _ in sc.most_common()]
            if k.startswith("b_") and not mp.successors:
                mp.cls, mp.reason = "wasteland", f"province {old_prov.get(k)} has no barony in the target map"
            elif not mp.successors and same:
                mp.successors, mp.cls, mp.reason = same, "by_key", "same name under another tier"
            elif not mp.successors:
                mp.cls, mp.reason = "dropped", "no land and no same-named title in the target"
            out.append(mp)
        elif k.startswith("b_") and k in old_prov and k in new_prov and old_prov[k] != new_prov[k]:   # moved
            s = on_prov.get(old_prov[k])
            mp = Mapping(k, i, h, "moved", [s] if s else [])
            if not s:
                mp.cls, mp.reason = "wasteland", f"old province {old_prov[k]} has no barony in the target map"
            out.append(mp)

    # the clean rule, over all mappings at once (renames are simultaneous: b_ganjun leaves the key b_ganjun
    # free for b_linze in the same pass)
    renamed_away = {m.key for m in out if m.successors and m.cls == ""}
    kept_keys = set(saved) - renamed_away
    target_count = Counter(m.successors[0] for m in out if m.cls == "" and len(m.successors) == 1)
    for m in out:
        if m.cls:
            continue
        if len(m.successors) != 1:
            m.cls, m.reason = "unclean", f"split into {len(m.successors)}"
            continue
        s = m.successors[0]
        if target_count[s] > 1:
            m.cls, m.reason = "unclean", f"{target_count[s]} titles map to {s}"
        elif s in kept_keys:
            m.cls, m.reason = "unclean", f"{s} is a title the save keeps"
        elif land_old(m.key) != land_new(s):
            m.cls, m.reason = "unclean", (f"land differs: {len(land_old(m.key))} old provinces, "
                                          f"{len(land_new(s))} under {s}")
        else:
            m.cls = "clean"
    # a barony whose old county is not clean goes with its county: the reference's holders take the region
    # (the engine requires a barony's de facto liege to be its de jure county, so a campaign barony cannot sit
    # inside a reference county)
    by_key = {m.key: m for m in out}
    for m in out:
        par = by_key.get(old_parent.get(m.key) or "")
        if m.key.startswith("b_") and m.cls == "clean" and par is not None and par.cls != "clean":
            m.cls, m.reason = "unclean", f"its county {par.key} is {par.cls}"
    # the same for a barony the target still has under the same key: if its old county is removed, it goes too,
    # and the reference brings it back under its target county (b_wuluhai under c_langshan)
    for k, (i, h) in saved.items():
        par = by_key.get(old_parent.get(k) or "")
        if k.startswith("b_") and k not in by_key and par is not None and par.cls != "clean":
            mp = Mapping(k, i, h, "follows", [k], "unclean", f"its county {par.key} is {par.cls}")
            out.append(mp)
            by_key[k] = mp
    return out


def _title_fields() -> dict[str, tuple[set[bytes], set[bytes]]]:
    """Per kind (database section): the field names that hold title ids, as (scalars, lists), from the id schema
    (every path whose space is "title") plus the faith and holy-site fields the schema leaves to the religion
    rules. Per kind, because one name can mean two things: ``heir`` lists titles in a character and
    characters in a title."""
    from . import idschema as S
    out: dict[str, tuple[set[bytes], set[bytes]]] = {
        "faiths/database": ({b"religious_head"}, {b"active_clerical_electors", b"inactive_clerical_electors"}),
        "religion/holy_sites": ({b"barony"}, set()),
    }
    for kind, table in S.FIELDS.items():
        scalars, lists = out.setdefault(kind, (set(), set()))
        for path, space in table.items():
            if space != "title":
                continue
            segs = [s for s in path.split("/") if s not in ("[]", "<date>")]
            if segs[-1] == "*":
                lists.add(segs[-2].encode())
            elif segs[-1] != "#key":
                scalars.add(segs[-1].encode())
    return out


_TITLE_FIELDS = _title_fields()
_ALL_SCALARS = set().union(*(s for s, _ in _TITLE_FIELDS.values()))
_ALL_LISTS = set().union(*(lst for _, lst in _TITLE_FIELDS.values()))


def _kind_ranges(save: bytes) -> list[tuple[int, int, str]]:
    """(start, end, kind) of every section the title fields are known for, sorted by start."""
    from . import gamestate as gs
    out = []
    for kind in _TITLE_FIELDS:
        try:
            b = gs.locate(save, kind)
        except gs.GamestateError:
            continue
        out.append((b.open, b.close, kind))
    return sorted(out)


@dataclass
class Applied:
    renamed: dict[str, str] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    references_removed: Counter = field(default_factory=Counter)   # field name -> count
    county_records_renamed: int = 0
    county_records_removed: int = 0


def _county_records(save: bytes, res: Applied, ep) -> None:
    """The per-county record (county_manager/counties) is keyed by the county's title KEY, so it follows R15: a
    renamed county's record takes the new key; a removed county's record goes. (Census 2026-10-26: 11 renamed
    campaign counties kept their record under the dead key, and 16 stale records stayed.)"""
    from . import gamestate as gs
    try:
        b = gs.locate(save, "county_manager/counties")
    except gs.GamestateError:
        return
    gone = {k for k in res.removed if k.startswith("c_")}
    for e in gs.iter_entries(save, *b.body):
        k = e.key.decode() if e.key else ""
        if k in res.renamed and k.startswith("c_"):
            ep.add(gs.Edit(e.start, e.start + len(e.key), res.renamed[k].encode(), "R15", f"county record {k}"))
            res.county_records_renamed += 1
        elif k in gone:
            ep.delete_block(save, e, "R15", f"county record {k} (removed county)")
            res.county_records_removed += 1


def apply(save: bytes, mappings: list[Mapping], ep) -> Applied:
    """Add R15's edits to ``ep`` (a gamestate.EditPass over ``save``): clean -> rename the key; any other class
    -> delete the title and the references to its id from the title fields of every entry."""
    from . import gamestate as gs
    res = Applied()
    blocks = dict(T.entries(save, "landed_titles/landed_titles"))
    removed_ids = {}
    for m in mappings:
        e = blocks[m.save_id]
        if m.cls == "clean":
            kc = next(c for c in gs.iter_children(save, e.open + 1, min(e.close, e.open + 4096))
                      if c.key == b"key" and c.block is None)
            quote = save[kc.value_start:kc.value_start + 1] == b'"'
            new = f'"{m.successors[0]}"' if quote else m.successors[0]
            ep.add(gs.Edit(kc.value_start, kc.value_end, new.encode(), "R15", f"{m.key} -> {m.successors[0]}"))
            res.renamed[m.key] = m.successors[0]
        else:
            ep.delete_block(save, e, "R15", f"remove {m.key} ({m.cls})")
            removed_ids[m.save_id] = m.key
            res.removed.append(m.key)
    _county_records(save, res, ep)
    if not removed_ids:
        return res
    ids = b"|".join(str(i).encode() for i in removed_ids)
    spans = sorted((e.start, e.end) for i, e in blocks.items() if i in removed_ids)

    def inside_removed(pos: int) -> bool:
        return any(s <= pos < e for s, e in spans)

    ranges = _kind_ranges(save)

    def kind_at(pos: int) -> str | None:
        for s, e, kind in ranges:
            if s <= pos < e:
                return kind
        return None

    # scalars: key=<removed id>, the whole line goes (only where that key names a title in that kind)
    for m in re.finditer(rb"[\n\t ](" + b"|".join(_ALL_SCALARS) + rb")=(" + ids + rb")(?![\w.])", save):
        kind = kind_at(m.start(1))
        if inside_removed(m.start(1)) or kind is None or m.group(1) not in _TITLE_FIELDS[kind][0]:
            continue
        s, e = gs.removal_span(save, m.start(1), m.end(2))
        ep.add(gs.Edit(s, e, b"", "R15", "reference"))
        res.references_removed[m.group(1).decode()] += 1
    # lists: { ... <removed id> ... }, the item goes
    for m in re.finditer(rb"[\n\t ](" + b"|".join(_ALL_LISTS) + rb")=\{([^{}]*)\}", save):
        kind = kind_at(m.start(1))
        if kind is None or m.group(1) not in _TITLE_FIELDS[kind][1]:
            continue
        body_start = m.start(2)
        for t in re.finditer(rb"\S+", m.group(2)):
            if t.group().isdigit() and int(t.group()) in removed_ids:
                s, e = body_start + t.start(), body_start + t.end()
                if inside_removed(s):
                    continue
                while s > body_start and save[s - 1:s] == b" ":
                    s -= 1
                ep.add(gs.Edit(s, e, b"", "R15", "list reference"))
                res.references_removed[m.group(1).decode()] += 1
    return res
