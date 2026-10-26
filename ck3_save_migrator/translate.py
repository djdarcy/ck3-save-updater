"""R13: translate objects from a reference gamestate into a save's id spaces (a library, not a user rule).

How CK3 numbers objects (measured, ``tests/one-offs/measure_unit1_*.py``):

* an id is a 24-bit SLOT INDEX plus an 8-bit GENERATION in the top byte. The engine allocates from a free list:
  a new object takes a freed slot with the previous occupant's generation + 1, or a fresh slot above the highest
  index with generation 0 (two saves of one campaign: 122 of 122 reused character slots stepped by exactly +1,
  houses 29/29, titles 3/3). There is no allocator counter for these spaces; the engine rebuilds its free list
  from the slots in use.
* ``4294967295`` (0xFFFFFFFF) is the engine's "none".
* coats of arms carry no generation and are numbered by a counter, ``coat_of_arms/next_id`` (always the max id
  + 1); runtime-created titles take keys ``x_x_<n>`` from ``landed_titles/index``. Both must be raised when
  objects are added.

The translation of a reference id, per space:

1. a JOIN when the save already holds the same thing: titles by key (except runtime ``x_`` titles, whose keys
   are reused numbers, not identities), cultures by template, characters by history id (``character_lookup``),
   dynasties and houses by history key. A joined id maps to the save's id. A join only redirects the
   reference's REFERENCES; nothing from the reference is written into the campaign's entry (the people alive in
   1.20's history but dead in the campaign stay exactly as the campaign has them).
2. IDENTITY for the spaces whose ids are the same in both (faiths, rites, religions, holy sites, organizations,
   provinces), and for a space the save does not have at all.
3. otherwise an OFFSET on the slot index, keeping the generation: ``(id & 0xFF000000) | ((id & 0xFFFFFF) + base)``
   with ``base = 1 + the save's highest index in the space``. Every translated index lies above every save
   index, so collisions are impossible by construction and are still checked; the reference's own references
   to an object carry that object's generation, so a function on the index keeps every pair consistent.

Traits are not ids but positions in each save's ``traits_lookup`` table; they translate by trait name, and the
names the save lacks are appended (``Translator.new_traits``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from . import gamestate as gs
from . import idschema as S

LOW = 0xFFFFFF
GEN = 0xFF000000
NONE = 0xFFFFFFFF


class TranslationError(ValueError):
    """The reference cannot be translated into the save without a collision, an overflow or an ambiguity."""


def index(i: int) -> int:
    return i & LOW


def generation(i: int) -> int:
    return i >> 24


# --------------------------------------------------------------------------- #
# reading the two gamestates
# --------------------------------------------------------------------------- #
def entries(g: bytes, path: str):
    """The numbered entries of the database at ``path`` (empty when absent); a repeated id is yielded once
    (1.20 writes every ``dead_unprunable`` entry twice, byte-identical)."""
    try:
        blk = gs.locate(g, path)
    except gs.GamestateError:
        return
    seen = set()
    for e in gs.iter_entries(g, *blk.body):
        if e.key and e.key.isdigit():
            i = int(e.key)
            if i not in seen:
                seen.add(i)
                yield i, e


def space_ids(g: bytes, space: str) -> set[int]:
    out: set[int] = set()
    for sec in S.SPACES[space]:
        out.update(i for i, _ in entries(g, sec))
    return out


_KEY = re.compile(rb'\n\t+key="?([^"\s]+)"?')
_TEMPLATE = re.compile(rb'\n\t+culture_template="?([^"\s]+)"?')


def _depth0(g: bytes, e: gs.Block, rx: re.Pattern, head: int = 4096) -> bytes | None:
    """A scalar at depth 0 of an entry, found in its first ``head`` bytes and confirmed to be at depth 0."""
    body = g[e.open:min(e.close, e.open + head)]
    for m in rx.finditer(body):
        if body.count(b"{", 0, m.start()) - body.count(b"}", 0, m.start()) == 1:
            return m.group(1)
    return None


def keyed(g: bytes, path: str, rx: re.Pattern = _KEY) -> dict[bytes, int]:
    """key value -> id for a database whose entries carry a key at depth 0; an ambiguous key raises."""
    out: dict[bytes, int] = {}
    for i, e in entries(g, path):
        k = _depth0(g, e, rx)
        if k is None:
            continue
        if k in out:
            raise TranslationError(f"{path}: key {k.decode()!r} names both {out[k]} and {i}")
        out[k] = i
    return out


_DYNASTY = re.compile(rb"\n\t+dynasty=(\d+)")
_NAME = re.compile(rb'\n\t+name="?([^"\s]+)"?')


def founding_houses(g: bytes) -> dict[tuple[int, bytes], int]:
    """(dynasty id, house name) -> house id for houses without a key; a pair two houses share is left out."""
    out: dict[tuple[int, bytes], int] = {}
    bad = set()
    for i, e in entries(g, "dynasties/dynasty_house"):
        if _depth0(g, e, _KEY) is not None:
            continue
        d, n = _depth0(g, e, _DYNASTY), _depth0(g, e, _NAME)
        if d is None or n is None:
            continue
        k = (int(d), n)
        if k in out:
            bad.add(k)
        out[k] = i
    for k in bad:
        del out[k]
    return out


_LOOKUP_LINE = re.compile(rb"^[ \t]*([^\s={}]+)=(\d+)[ \t]*$", re.M)


def character_lookup(g: bytes) -> dict[str, int]:
    """history id -> character id, from the top-level ``character_lookup``.

    History ids are whole keys, numeric (``100=18301``) or named (``han_1176=5552``, ``abbasid_concubines_1=13000``),
    so each line is matched whole and the key kept as written. (An unanchored ``(\\d+)=(\\d+)`` read ``han_1176=5552``
    as ``1176``: 2,460 of the 1.20 reference's history ids were lost or overwritten, census 2026-10-26.)
    """
    try:
        b = gs.find_section(g, "character_lookup")
    except gs.GamestateError:
        return {}
    return {a.decode(): int(c) for a, c in _LOOKUP_LINE.findall(g[b.open + 1:b.close])}


def traits_lookup(g: bytes) -> list[str]:
    try:
        b = gs.find_section(g, "traits_lookup")
    except gs.GamestateError:
        return []
    return [t.strip(b'"').decode() for t in re.findall(rb'"[^"]*"|[^\s{}]+', g[b.open + 1:b.close])]


def counter(g: bytes, path: str, key: str) -> int | None:
    """A scalar at depth 0 of a section (``coat_of_arms`` / ``next_id``); None when absent."""
    try:
        blk = gs.locate(g, path)
    except gs.GamestateError:
        return None
    hits = _depth0_scalars(g, blk, key)
    return int(g[hits[-1].value_start:hits[-1].value_end]) if hits else None


def _depth0_scalars(g: bytes, blk: gs.Block, key: str):
    """Depth-0 scalars named ``key`` in a section of any size: the gaps between its blocks are tokenised, the
    blocks themselves (a 13 MB coat-of-arms database) are skipped."""
    out = []
    pos = blk.open + 1
    for e in gs.iter_entries(g, *blk.body):
        out += _gap_scalars(g, pos, e.start, key)
        pos = e.end
    out += _gap_scalars(g, pos, blk.close, key)
    return out


def _gap_scalars(g: bytes, start: int, end: int, key: str):
    if end <= start:
        return []
    return [c for c in gs.iter_children(g, start, end) if c.key == key.encode() and c.block is None]


# --------------------------------------------------------------------------- #
# the translation function
# --------------------------------------------------------------------------- #
@dataclass
class SpaceMap:
    """How ids of one space translate."""
    name: str
    base: int = 0
    identity: bool = False
    join: dict[int, int] = field(default_factory=dict)
    join_pruned: dict[int, int] = field(default_factory=dict)   # joins whose save object no longer exists
    save_n: int = 0
    save_max_index: int = -1
    ref_n: int = 0
    ref_max_index: int = -1

    def translate(self, i: int) -> int:
        if i == NONE:
            return i
        j = self.join.get(i)
        if j is not None:
            return j
        if self.identity or self.base == 0:
            return i
        return (i & GEN) | ((i & LOW) + self.base)

    @property
    def mode(self) -> str:
        if self.identity:
            return "identity"
        return "offset" if self.base else "identity (absent from the save)"


@dataclass
class Translator:
    spaces: dict[str, SpaceMap]
    trait_map: dict[int, int]
    new_traits: list[str]
    save_coa_next_id: int | None = None
    save_title_index: int | None = None
    used: Counter = field(default_factory=Counter)        # (space, how) -> count, from translate()

    @classmethod
    def build(cls, save: bytes, ref: bytes) -> Translator:
        """Compute every space's map from the two gamestates; TranslationError on overflow or ambiguity."""
        spaces: dict[str, SpaceMap] = {}
        save_ids_by = {}
        for sp in S.SPACES:
            s_ids, r_ids = space_ids(save, sp), space_ids(ref, sp)
            save_ids_by[sp] = s_ids
            m = SpaceMap(sp, identity=sp in S.IDENTITY, save_n=len(s_ids), ref_n=len(r_ids),
                         save_max_index=max((i & LOW for i in s_ids), default=-1),
                         ref_max_index=max((i & LOW for i in r_ids), default=-1))
            if not m.identity and s_ids:
                m.base = m.save_max_index + 1
                top = m.base + m.ref_max_index
                if top > LOW:
                    raise TranslationError(f"{sp}: base {m.base:,} + reference max index {m.ref_max_index:,} "
                                           f"exceeds the 24-bit slot index ({LOW:,})")
                if (max((i >> 24 for i in r_ids), default=0) == 0xFF) and top >= LOW:
                    raise TranslationError(f"{sp}: a translated id would be the 'none' sentinel")
            spaces[sp] = m

        def join(sp: str, pairs: dict[int, int], pruned_ok: bool = False) -> None:
            vals = list(pairs.values())
            if len(set(vals)) != len(vals):
                dup = [v for v, n in Counter(vals).items() if n > 1][:3]
                raise TranslationError(f"{sp}: two reference objects join the same save object {dup}")
            missing = {r: v for r, v in pairs.items() if v not in save_ids_by[sp]}
            if missing and not pruned_ok:
                raise TranslationError(f"{sp}: join targets missing from the save, e.g. {list(missing.values())[:3]}")
            spaces[sp].join = pairs
            spaces[sp].join_pruned = missing

        # titles by key; runtime x_ titles never join (their keys are reused counter values)
        st, rt = keyed(save, "landed_titles/landed_titles"), keyed(ref, "landed_titles/landed_titles")
        join("title", {rt[k]: st[k] for k in rt.keys() & st.keys() if not k.startswith(b"x_")})
        # cultures by template; campaign-made cultures have none and never join
        sc = keyed(save, "culture_manager/cultures", _TEMPLATE)
        rc = keyed(ref, "culture_manager/cultures", _TEMPLATE)
        join("culture", {rc[k]: sc[k] for k in rc.keys() & sc.keys()})
        # dynasties and houses by history key. A house without a key is its dynasty's founding house (the
        # reference has exactly one per dynasty): it joins through its dynasty's join and its name.
        sk, rk = keyed(save, "dynasties/dynasties"), keyed(ref, "dynasties/dynasties")
        join("dynasty", {rk[k]: sk[k] for k in rk.keys() & sk.keys()})
        sk, rk = keyed(save, "dynasties/dynasty_house"), keyed(ref, "dynasties/dynasty_house")
        houses = {rk[k]: sk[k] for k in rk.keys() & sk.keys()}
        s_found, r_found = founding_houses(save), founding_houses(ref)
        dyn = spaces["dynasty"].join
        for (d, name), r_id in r_found.items():
            s_id = s_found.get((dyn.get(d), name))
            if s_id is not None and r_id not in houses:
                houses[r_id] = s_id
        join("house", houses)
        # characters by history id. The save's lookup may point at a character the campaign has since pruned
        # (the game keeps such entries: 836 of 8,973 in the founding save); the reference's mentions of that
        # person still go to the campaign's id, never to a copy (recorded in ``join_pruned``).
        sl, rl = character_lookup(save), character_lookup(ref)
        join("character", {rl[h]: sl[h] for h in rl.keys() & sl.keys()}, pruned_ok=True)

        s_tr, r_tr = traits_lookup(save), traits_lookup(ref)
        pos = {n: i for i, n in enumerate(s_tr)}
        trait_map, new = {}, []
        for i, n in enumerate(r_tr):
            if n not in pos:
                pos[n] = len(s_tr) + len(new)
                new.append(n)
            trait_map[i] = pos[n]
        return cls(spaces, trait_map, new,
                   save_coa_next_id=counter(save, "coat_of_arms", "next_id"),
                   save_title_index=counter(save, "landed_titles", "index"))

    def id(self, space: str, value: int) -> int:
        m = self.spaces[space]
        out = m.translate(value)
        how = "none" if value == NONE else "joined" if value in m.join else \
            "identity" if out == value else "offset"
        self.used[(space, how)] += 1
        return out

    def trait(self, position: int) -> int:
        try:
            return self.trait_map[position]
        except KeyError:
            raise TranslationError(f"trait position {position} is outside the reference's traits_lookup")

    # -- what the transplant must also write --------------------------------
    def coa_next_id(self, translated_coa_ids) -> int | None:
        """The value ``coat_of_arms/next_id`` must hold after adding coats with these (translated) ids."""
        top = max(translated_coa_ids, default=None)
        if top is None:
            return self.save_coa_next_id
        return max(self.save_coa_next_id or 0, top + 1)


# --------------------------------------------------------------------------- #
# rewriting a reference entry into save text
# --------------------------------------------------------------------------- #
@dataclass
class RewriteReport:
    translated: Counter = field(default_factory=Counter)    # space -> values rewritten
    unchanged_ids: Counter = field(default_factory=Counter)  # space -> id values left as they are (identity)
    unlisted: Counter = field(default_factory=Counter)       # (kind, path) -> integer fields the schema lacks
    review: Counter = field(default_factory=Counter)         # (kind, path) -> REVIEW fields left unchanged
    unknown_types: Counter = field(default_factory=Counter)  # typed references with a type= the table lacks
    to_pruned: Counter = field(default_factory=Counter)      # space -> references joined to a pruned save object
    dropped: Counter = field(default_factory=Counter)        # (kind, path) -> references removed by ``keep``


def rewrite_entry(g: bytes, entry: gs.Block, kind: str, tr: Translator,
                  report: RewriteReport | None = None, keep=None) -> bytes:
    """The text of a reference ``entry`` (``id={...}``) of database ``kind`` with every id translated.

    The entry's own key is translated in the kind's space; every field the schema names is translated in its
    space; traits by name. Fields the schema does not know are left as they are and counted in ``report``.

    ``keep(space, reference_id, path) -> bool`` is the edge policy: a reference to an object that will not exist
    in the output (or, by ``path``, one that must not be linked, such as a new title's de facto liege in the
    campaign's realm) is removed instead of translated (a list item, a ``key=value`` line, or the list item / block
    that carries a typed reference), and counted in ``report.dropped``. A dangling translated id would point
    at a free slot that a later newborn can take. Without ``keep`` every reference is translated.
    """
    rep = report if report is not None else RewriteReport()
    st = _Walk(g, kind, tr, rep, keep)
    if entry.key and entry.key.isdigit():
        sp = S.KIND_SPACE.get(kind)
        if sp is None:
            raise TranslationError(f"no id space for entries of {kind!r}")
        st.put(sp, entry.start, entry.start + len(entry.key), int(entry.key), drop=None)   # always kept
    st.walk(entry.open + 1, entry.close, "", None, None)
    return st.render(entry)


def references(g: bytes, entry: gs.Block, kind: str):
    """Every id an entry refers to, as (path, space, id), by the schema (traits, plain and REVIEW fields
    excluded; numeric keys that are ids included). The entry's own id is not yielded."""
    def walk(start, end, prefix):
        children = list(gs.iter_children(g, start, end))
        typ = next((g[c.value_start:c.value_end].strip(b'"').decode() for c in children
                    if c.key == b"type" and c.block is None), None)
        for c in children:
            seg = S.norm_key(c.key, c.block is not None)
            path = f"{prefix}/{seg}" if prefix else seg
            if c.key and c.key.isdigit():
                ksp = S.classify(kind, f"{prefix}/#key" if prefix else "#key")
                if ksp not in (None, S.PLAIN, S.REVIEW, S.TYPED, S.TRAIT):
                    yield path + "#key", ksp, int(c.key)
            if c.block is not None:
                yield from walk(c.block.open + 1, c.block.close, path)
                continue
            tok = g[c.value_start:c.value_end]
            if not tok.isdigit() or int(tok) == NONE:
                continue
            cls = S.classify(kind, path)
            if cls == S.TYPED:
                cls = S.TYPE_SPACE.get(typ or "")
            if cls not in (None, S.PLAIN, S.REVIEW, S.TRAIT):
                yield path, cls, int(tok)
    yield from walk(entry.open + 1, entry.close, "")


class _Walk:
    """One entry's rewrite: id edits, plus the removals the ``keep`` predicate asks for."""

    def __init__(self, g, kind, tr, rep, keep):
        self.g, self.kind, self.tr, self.rep, self.keep = g, kind, tr, rep, keep
        self.edits: list[tuple[int, int, bytes]] = []
        self.drops: list[tuple[int, int]] = []

    def put(self, space, s, e, value, drop, path=""):
        """Translate one id token; when ``keep`` refuses the referenced object, remove ``drop`` instead."""
        if drop is not None and self.keep is not None and value != NONE and not self.keep(space, value, path):
            self.drops.append(gs.removal_span(self.g, *drop))
            self.rep.dropped[(self.kind, path)] += 1
            return
        if value in self.tr.spaces[space].join_pruned:
            self.rep.to_pruned[space] += 1
        new = self.tr.id(space, value)
        if new != value:
            self.edits.append((s, e, str(new).encode()))
            self.rep.translated[space] += 1
        else:
            self.rep.unchanged_ids[space] += 1

    def walk(self, start, end, prefix, anon, holder):
        """``anon``: span of the nearest anonymous block above (a list item); ``holder``: span of the child
        whose block this is. A typed reference that is refused removes the list item that carries it, or, when
        there is none, the block that holds it."""
        g = self.g
        children = list(gs.iter_children(g, start, end))
        typ = None
        for c in children:
            if c.key == b"type" and c.block is None:
                typ = g[c.value_start:c.value_end].strip(b'"').decode()
        for c in children:
            seg = S.norm_key(c.key, c.block is not None)
            path = f"{prefix}/{seg}" if prefix else seg
            if c.key and c.key.isdigit():
                ksp = S.classify(self.kind, f"{prefix}/#key" if prefix else "#key")
                if ksp not in (None, S.PLAIN, S.REVIEW, S.TYPED, S.TRAIT):
                    self.put(ksp, c.key_start, c.key_end, int(c.key), (c.start, c.end), path + "#key")
            if c.block is not None:
                span = (c.start, c.end)
                self.walk(c.block.open + 1, c.block.close, path, span if c.key is None else anon, span)
                continue
            tok = g[c.value_start:c.value_end]
            if not tok.isdigit():
                continue
            cls = S.classify(self.kind, path)
            whole = (c.start, c.end)
            if cls is None:
                self.rep.unlisted[(self.kind, path)] += 1
            elif cls == S.PLAIN:
                pass
            elif cls == S.REVIEW:
                self.rep.review[(self.kind, path)] += 1
            elif cls == S.TRAIT:
                new = self.tr.trait(int(tok))
                if new != int(tok):
                    self.edits.append((c.value_start, c.value_end, str(new).encode()))
                self.rep.translated["trait"] += 1
            elif cls == S.TYPED:
                sp = S.TYPE_SPACE.get(typ or "")
                if sp is None:
                    self.rep.unknown_types[typ] += 1
                elif sp != S.PLAIN:
                    self.put(sp, c.value_start, c.value_end, int(tok), anon or holder or whole, path)
            else:
                self.put(cls, c.value_start, c.value_end, int(tok), whole, path)

    def render(self, entry) -> bytes:
        drops = sorted(self.drops)
        merged: list[list[int]] = []
        for s, e in drops:
            if merged and s < merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        ops = [(s, e, b"") for s, e in merged]
        ops += [(s, e, b) for s, e, b in self.edits if not any(ms <= s < me for ms, me in merged)]
        base = entry.start
        text = self.g[entry.start:entry.end]
        out, pos = [], 0
        for s, e, b in sorted(ops):
            out.append(text[pos:s - base])
            out.append(b)
            pos = e - base
        out.append(text[pos:])
        return b"".join(out)
