"""Pre-launch checks for a 1.20-layout save: structure, cross-references, and key names the game cannot know.

Every check reads the gamestate only; nothing is changed. Severity:

- error: something the game reads by id or by structure is broken -- a brace imbalance, a rite or faith id
  that points nowhere, a character without a rite. The migration rules write these, so an error here is a
  failed post-condition of a rule.
- warn:  a reference the rules do not write (a spouse id, a culture id, a title holder) that points nowhere,
  or a layout detail (title_name_data placement). Real saves can carry some of these; compare against a
  fresh save from the same game version before treating one as a bug.
- info:  key names that neither the target-version reference, the game binary, the game's own script files
  nor the active mods contain.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import gamestate as gs
from .rules.to_1_20 import defined_title_keys

NONE = b"4294967295"
CHAR_SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
_ENTRY_COL0 = re.compile(rb"(?m)^(\d+)=\{")
# a character entry's own fields (one tab) and its family_data links (two tabs)
_CHAR_FIELDS = re.compile(rb"(?m)^\t(rite|culture|dynasty_house)=(\d+)"
                          rb"|^\t\t(spouse|primary_spouse|real_father|child|former_spouses)=(\d+|\{[^}]*\})")
_STRING_OR_BRACE = re.compile(rb'"(?:[^"\\]|\\.)*"|[{}]')
_KEY = re.compile(rb'"(?:[^"\\]|\\.)*"|([A-Za-z_][\w.:\-]*)[ \t]*=')
# words in the binary and in script files; a second, wider pattern keeps ids like c_yar-calli and menendez.0001
_WORD = re.compile(rb"[A-Za-z_][A-Za-z0-9_]{1,63}")
_WORD_WIDE = re.compile(rb"[A-Za-z_][A-Za-z0-9_]*[.\-][A-Za-z0-9_.\-]+")


def _words(data: bytes) -> set[bytes]:
    return set(_WORD.findall(data)) | set(_WORD_WIDE.findall(data))


@dataclass
class Finding:
    check: str
    severity: str           # error | warn | info
    count: int
    examples: list[str] = field(default_factory=list)
    note: str = ""
    gloss: str = ""         # what it means, in plain words (check keeps the game's own log wording)

    def as_dict(self) -> dict:
        return {"check": self.check, "severity": self.severity, "count": self.count,
                "gloss": self.gloss, "examples": self.examples, "note": self.note}


@dataclass
class LintReport:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def add(self, check: str, severity: str, bad: list, note: str = "", limit: int = 8, gloss: str = "") -> None:
        if bad:
            self.findings.append(Finding(check, severity, len(bad), [str(b) for b in bad[:limit]], note, gloss))

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def errors(self) -> int:
        return self.count("error")

    def as_dict(self) -> dict:
        return {"errors": self.errors, "warnings": self.count("warn"), "reject": self.count("reject"),
                "info": self.count("info"),
                "findings": [f.as_dict() for f in self.findings], "stats": self.stats, "skipped": self.skipped}


# --------------------------------------------------------------------------- helpers
class SectionIndex:
    """Top-level sections found in one walk (gs.locate rescans the whole gamestate on every call)."""

    def __init__(self, g: bytes):
        self.g, self.top, self._cache = g, {}, {}
        pos = 0
        while (m := gs._TOP_KEY.search(g, pos)) is not None:
            op = m.end() - 1
            try:
                close = gs.match_brace(g, op)
            except gs.GamestateError:       # an unclosed section: check_structure reports it; index the rest
                break
            self.top.setdefault(m.group(1).decode(), gs.Block(m.group(1), m.start(), op, close))
            pos = close + 1

    def block(self, path: str) -> gs.Block | None:
        if path not in self._cache:
            parts = path.split("/")
            b = self.top.get(parts[0])
            try:
                for p in parts[1:]:
                    b = gs.find_child(self.g, b, p) if b is not None else None
            except gs.GamestateError:
                b = None
            self._cache[path] = b
        return self._cache[path]


def _db(g: bytes, idx: SectionIndex, path: str) -> dict[bytes, bytes]:
    """id -> entry body for a small database (faiths, rites, religions, ...); {} when absent."""
    b = idx.block(path)
    return {} if b is None else {e.key: g[e.open + 1:e.close] for e in gs.iter_entries(g, *b.body)}


def _val(body: bytes, key: bytes) -> bytes | None:
    """The first ``key=value`` in an entry body. Keys may share a line ("faith_type=catholic\\t\\t\\treligion=8"),
    so the key is anchored on whitespace, not on a line start; every key read here comes before any nested
    block that could repeat it."""
    m = re.search(rb"[\n\t ]" + re.escape(key) + rb"=([^\s{}]+)", body)
    return m.group(1) if m else None


def _list(body: bytes, key: bytes) -> list[bytes]:
    m = re.search(rb"[\n\t ]" + re.escape(key) + rb"=\{([^}]*)\}", body)
    return m.group(1).split() if m else []


# --------------------------------------------------------------------------- checks
def check_structure(g: bytes, rep: LintReport) -> None:
    depth, low, first_negative = 0, 0, None
    for m in _STRING_OR_BRACE.finditer(g):
        c = g[m.start()]
        if c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
            if depth < low:
                low = depth
                if first_negative is None and depth < 0:
                    first_negative = m.start()
    bad = []
    if first_negative is not None:
        bad.append(f"a '}}' closes more than was opened at byte {first_negative:,}")
    if depth != 0:
        bad.append(f"{depth:+d} unclosed brace(s) at the end of the gamestate")
    rep.add("braces balance", "error", bad)


def check_ids(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """Every entry id is unique in its id space, and so is its 24-bit slot index.

    A CK3 id is a slot index (low 24 bits) plus a generation (top byte); two objects of one space may not share
    a slot, whatever their generations. The three character sections are one space. 1.20 itself writes every
    ``dead_unprunable`` entry twice, byte-identical; such a repeat is not a collision.
    """
    from .idschema import SPACES
    idx = idx or SectionIndex(g)
    dup_ids, dup_slots = [], []
    for space, sections in SPACES.items():
        seen: dict[int, tuple[str, int]] = {}
        slots: dict[int, int] = {}
        for sec in sections:
            b = idx.block(sec)
            if b is None:
                continue
            for m in _ENTRY_COL0.finditer(g, b.open, b.close):
                i = int(m.group(1))
                prev = seen.get(i)
                if prev is not None:
                    same = prev[0] == sec and _entry_text(g, prev[1]) == _entry_text(g, m.start())
                    if not same:
                        dup_ids.append(f"{space}: {i} in {prev[0]} and {sec}")
                    continue
                seen[i] = (sec, m.start())
                s = i & 0xFFFFFF
                if s in slots and slots[s] != i:
                    dup_slots.append(f"{space}: {slots[s]} and {i} share slot {s}")
                slots.setdefault(s, i)
    rep.add("entry ids are unique in each id space", "error", dup_ids,
            gloss="Two objects of the same kind carry the same number; the game keeps one and the other's links "
                  "point at the wrong object")
    rep.add("entry slots are unique in each id space", "error", dup_slots,
            "an id is a 24-bit slot index plus a generation in the top byte",
            gloss="Two objects of the same kind occupy the same slot under different generations; the game "
                  "cannot hold both")


_T_FIELD = {k: re.compile(rb"\n\t" + k + rb"=\"?([\w\-']+)\"?") for k in
            (b"key", b"de_jure_liege", b"de_facto_liege", b"capital_barony", b"holder")}


def check_titles(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """The title tree's own rules, as the 1.20 loader enforces them (each one seen in a load's error.log):
    keys unique ("Duplicate landed title name"); de jure and de facto lieges name titles that exist; a barony's
    de facto liege is its de jure county ("Dejure and defacto liege for barony differ"); a capital barony has
    both lieges ("Capital b_x doesn't have a De Jure / De Facto liege"). A barony without any county is a
    warning: the game logs only capital baronies, but every orphan is land no county holds."""
    idx = idx or SectionIndex(g)
    lt = idx.block("landed_titles/landed_titles")
    if lt is None:
        return
    titles = {}
    for m in _ENTRY_COL0.finditer(g, lt.open, lt.close):
        head = g[m.end():m.end() + 1500]
        head = head[:head.find(b"\n}") + 1] if b"\n}" in head else head
        f = {k: (x.group(1) if (x := rx.search(head)) else None) for k, rx in _T_FIELD.items()}
        titles[int(m.group(1))] = f
    keys = Counter(f[b"key"] for f in titles.values() if f[b"key"])
    dup = sorted(k.decode() for k, n in keys.items() if n > 1)
    bad_liege, barony_differs, capital_no_liege, orphan = [], [], [], []
    for i, f in titles.items():
        k = (f[b"key"] or b"?").decode()
        for field in (b"de_jure_liege", b"de_facto_liege"):
            v = f[field]
            if v is not None and v.isdigit() and int(v) not in titles:
                bad_liege.append(f"{k}: {field.decode()}={v.decode()}")
        if k.startswith("b_"):
            dj, df = f[b"de_jure_liege"], f[b"de_facto_liege"]
            if dj and df and dj != df:
                barony_differs.append(f"{k}: de jure {dj.decode()}, de facto {df.decode()}")
            if f[b"capital_barony"] == b"yes" and not (dj and df):
                capital_no_liege.append(f"{k}: {'no de jure liege' if not dj else ''}"
                                        f"{', ' if not dj and not df else ''}{'no de facto liege' if not df else ''}")
            elif not dj and f[b"holder"]:
                orphan.append(k)                     # held land that no county contains
    rep.add("title keys are unique", "error", [f"{k} x{keys[k.encode()]}" for k in dup],
            gloss="Two titles carry the same key; the game keeps one name and logs the other as a duplicate")
    rep.add("title lieges point at titles that exist", "error", bad_liege,
            gloss="A title's de jure or de facto liege is a number no title in the save has")
    rep.add("a barony's de facto liege is its de jure county", "error", barony_differs,
            gloss="The game requires a barony to sit in its own county; it logs this as an assertion")
    rep.add("capital baronies have a county", "error", capital_no_liege,
            gloss="A county's capital barony with no county above it (the game logs 'Capital ... doesn't have a "
                  "De Jure / De Facto liege')")
    rep.add("held baronies have a county", "warn", orphan,
            gloss="Held baronies with no county above them; the game does not log these unless they are a capital")
    # INV-1 (census 2026-10-26): every HELD county has its county_manager record (development, culture, rite).
    # Vanilla 1.20 at 987: 4,703 county titles, the 3,476 held ones each with a record, the unheld ones without.
    cm = idx.block("county_manager/counties")
    if cm is not None:
        # any indent (inserted records sit at column 0); keys have hyphens (c_al-arid)
        records = set(re.findall(rb"(?m)^[ \t]*(c_[^\s={}]+)=\{", g[cm.open:cm.close]))
        no_record = sorted(f[b"key"].decode() for f in titles.values()
                           if f[b"key"] and f[b"key"].startswith(b"c_") and f[b"holder"] and f[b"key"] not in records)
        rep.add("held counties have a county record", "error", no_record,
                gloss="A held county with no county_manager record has no culture, faith or development; the game "
                      "then fails every script that asks for them (seen as 'culture trigger [Failed context switch]')")


def check_contracts(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """A vassal contract binds two people: both its liege and its vassal are named and exist (a contract copied
    with only one party binds nobody)."""
    idx = idx or SectionIndex(g)
    chars: set[bytes] = set()
    for sec in CHAR_SECTIONS:
        b = idx.block(sec)
        if b is not None:
            chars.update(m.group(1) for m in _ENTRY_COL0.finditer(g, b.open, b.close))
    bad = []
    for sec in ("vassal_contracts/active", "vassal_contracts/database"):
        b = idx.block(sec)
        if b is None:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            body = g[e.open:e.close]
            for party in (b"liege", b"vassal"):
                m = re.search(rb"[\n\t ]" + party + rb"=(\d+)", body)
                if m is None or m.group(1) not in chars:
                    bad.append(f"{sec} {e.key.decode()}: {party.decode()} "
                               f"{'missing' if m is None else m.group(1).decode() + ' is not a character'}")
    rep.add("vassal contracts name both parties", "error", bad,
            gloss="A vassal contract without its liege or its vassal binds nobody")


def _entry_text(g: bytes, start: int) -> bytes:
    op = g.index(b"{", start)
    return g[start:gs.match_brace(g, op) + 1]


def check_references(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    idx = idx or SectionIndex(g)
    rites, faiths = _db(g, idx, "rites/database"), _db(g, idx, "faiths/database")
    if not rites or not faiths:
        rep.skipped.append("religion references: no rites/faiths databases (not a 1.20-layout save)")
    religions, holy = _db(g, idx, "religion/religions"), _db(g, idx, "religion/holy_sites")
    orgs, cultures = _db(g, idx, "organization_manager/database"), _db(g, idx, "culture_manager/cultures")

    # characters: ids, then one-tab fields of the column-0 entries in each section
    char_ids: set[bytes] = set()
    living: set[bytes] = set()
    spans = []
    for sec in CHAR_SECTIONS:
        b = idx.block(sec)
        if b is None:
            continue
        ids = [m for m in _ENTRY_COL0.finditer(g, b.open, b.close)]
        char_ids.update(m.group(1) for m in ids)
        if sec == "living":
            living.update(m.group(1) for m in ids)
        spans.append((sec, b, ids))
    titles_b = idx.block("landed_titles/landed_titles")
    title_ids = {m.group(1) for m in _ENTRY_COL0.finditer(g, titles_b.open, titles_b.close)} if titles_b else set()
    houses_b = idx.block("dynasties/dynasty_house")
    house_ids = {m.group(1) for m in _ENTRY_COL0.finditer(g, houses_b.open, houses_b.close)} if houses_b else set()
    rep.stats.update(characters=len(char_ids), living=len(living), titles=len(title_ids), houses=len(house_ids),
                     rites=len(rites), faiths=len(faiths), religions=len(religions), cultures=len(cultures))

    no_rite, bad_rite, bad_culture, bad_house, bad_family = [], [], [], [], []
    for sec, b, ids in spans:
        starts = [m.start() for m in ids]
        has_rite = bytearray(len(ids))
        # one pass per section, matched in place (pos/endpos, no slice copies of a 150 MB section)
        for m in _CHAR_FIELDS.finditer(g, b.open, b.close):
            key, val = m.group(1) or m.group(3), m.group(2) or m.group(4)
            if key == b"rite":
                i = bisect_right(starts, m.start()) - 1
                if i >= 0:
                    has_rite[i] = 1
                if rites and val not in rites:
                    bad_rite.append(f"{sec}/{ids[i].group(1).decode()}: rite={val.decode()}")
            elif key == b"culture":
                if cultures and val not in cultures:
                    bad_culture.append(f"{sec}: culture={val.decode()}")
            elif key == b"dynasty_house":
                if house_ids and val not in house_ids:
                    bad_house.append(f"{sec}: dynasty_house={val.decode()}")
            elif key in (b"child", b"former_spouses"):
                bad_family += [f"{sec}: {key.decode()} {x.decode()}" for x in val.strip(b"{}").split()
                               if x not in char_ids]
            elif val not in char_ids:                       # spouse / primary_spouse / real_father
                bad_family.append(f"{sec}: {key.decode()}={val.decode()}")
        if rites:
            no_rite += [f"{sec}/{ids[i].group(1).decode()}" for i in range(len(ids)) if not has_rite[i]]
    rep.add("every character has a rite", "error", no_rite, "1.20 writes rite= on every character")
    rep.add("character rite ids exist", "error", bad_rite)
    rep.add("character culture ids exist", "warn", bad_culture,
            gloss="Characters whose culture number matches no culture in the save")
    rep.add("character house ids exist", "warn", bad_house,
            gloss="Characters whose house number matches no house in the save")
    rep.add("family links point at characters in the save", "warn", bad_family,
            "spouses/children/real fathers absent from living, dead_unprunable and dead_prunable",
            gloss="Relatives (spouses, children, real fathers) recorded by a number no character in the save has; "
                  "usually people the game pruned long ago, common in old saves")

    # titles: holders alive, title_name_data in place
    bad_holder, tnd_dup, tnd_place = [], [], []
    if titles_b is not None:
        for t in gs.iter_entries(g, *titles_b.body):
            body = g[t.open:t.close]
            h = re.search(rb"\n\tholder=(\d+)", body)
            if h and h.group(1) not in char_ids:    # holy-order titles are held by dead founders: any section
                bad_holder.append(f"title {t.key.decode()}: holder={h.group(1).decode()}")
            i = body.find(b"\n\ttitle_name_data={")
            if i >= 0:
                if re.search(rb"\n\t(name|adj|pre|article)=", body):
                    tnd_dup.append(f"title {t.key.decode()}")
                prev = body[:i].rstrip(b"\n").rsplit(b"\n", 1)[-1]
                if not prev.startswith(b"\tcoat_of_arms_id="):
                    tnd_place.append(f"title {t.key.decode()}: after {prev.strip()[:40].decode(errors='replace')}")
    rep.add("title holders are characters in the save", "warn", bad_holder,
            gloss="Titles held by a number no character in the save has")
    rep.add("title names only inside title_name_data", "error", tnd_dup,
            "a title with title_name_data must not also carry inline name/adj/pre/article")
    rep.add("title_name_data follows coat_of_arms_id", "warn", tnd_place,
            gloss="Title names stored at a slightly different place in the title than the current game writes them "
                  "(the game logged nothing for this when the 987 save loaded)")

    # counties: culture on any layout, rite on a 1.20 layout
    bad_county, bad_county_culture = [], []
    counties = idx.block("county_manager/counties")
    for c in (gs.iter_entries(g, *counties.body) if counties is not None else []):
        body = g[c.open:c.close]
        r = _val(body, b"rite")
        if rites and (r is None or r not in rites):
            bad_county.append(f"county {c.key.decode()}: rite={r and r.decode()}")
        cu = _val(body, b"culture")
        if cultures and cu is not None and cu not in cultures:
            bad_county_culture.append(f"county {c.key.decode()}: culture={cu.decode()}")
    rep.add("every county has an existing rite", "error", bad_county)
    rep.add("county culture ids exist", "warn", bad_county_culture,
            gloss="Counties whose culture is not a culture in the save (4294967295 is the game's value for 'none')")

    if not rites or not faiths:
        return
    bad = []
    for rid, body in rites.items():
        f = _val(body, b"faith")
        if f is None or f not in faiths:
            bad.append(f"rite {rid.decode()}: faith={f and f.decode()}")
        for k in (b"founder", b"head_of_rite"):
            v = _val(body, k)
            if v is not None and v != NONE and v not in char_ids:
                bad.append(f"rite {rid.decode()}: {k.decode()}={v.decode()} (no such character)")
        o = _val(body, b"origin_rite")
        if o is not None and o != NONE and o not in rites:
            bad.append(f"rite {rid.decode()}: origin_rite={o.decode()}")
    rep.add("rites point at faiths, characters and rites that exist", "error", bad)

    bad = []
    for fid, body in faiths.items():
        r = _val(body, b"religion")
        if r is None or r not in religions:
            bad.append(f"faith {fid.decode()}: religion={r and r.decode()}")
        mr = _val(body, b"main_rite")
        if mr is None or mr not in rites:
            bad.append(f"faith {fid.decode()}: main_rite={mr and mr.decode()}")
        elif _val(rites[mr], b"faith") != fid:
            bad.append(f"faith {fid.decode()}: main_rite {mr.decode()} belongs to faith "
                       f"{(_val(rites[mr], b'faith') or b'?').decode()}")
        org = _val(body, b"organization")
        if org is not None and org not in orgs:
            bad.append(f"faith {fid.decode()}: organization={org.decode()}")
        bad += [f"faith {fid.decode()}: holy site {x.decode()}" for x in _list(body, b"holy_sites") if x not in holy]
        head = _val(body, b"religious_head")
        if head is not None and head != NONE and head not in title_ids:
            bad.append(f"faith {fid.decode()}: religious_head={head.decode()} (no such title)")
        o = _val(body, b"origin")
        if o is not None and o != NONE and o not in faiths:
            bad.append(f"faith {fid.decode()}: origin={o.decode()}")
    rep.add("faiths point at religions, rites, organizations, holy sites and titles that exist", "error", bad)

    bad = []
    for rid, body in religions.items():
        bad += [f"religion {rid.decode()}: faith {x.decode()}" for x in _list(body, b"faiths") if x not in faiths]
    for hid, body in holy.items():
        bad += [f"holy site {hid.decode()}: faith {x.decode()}" for x in _list(body, b"faiths") if x not in faiths]
        bar = _val(body, b"barony")
        if bar is not None and bar not in title_ids:
            bad.append(f"holy site {hid.decode()}: barony={bar.decode()} (no such title)")
    for oid, body in orgs.items():
        f = _val(body, b"faith")
        if f is not None and f not in faiths:
            bad.append(f"organization {oid.decode()}: faith={f.decode()}")
    for hid, body in _db(g, idx, "holy_orders/holy_orders").items():
        r = _val(body, b"rite")
        if r is not None and r not in rites:
            bad.append(f"holy order {hid.decode()}: rite={r.decode()}")
    rep.add("religions, holy sites, organizations and holy orders point at faiths/rites/titles that exist",
            "error", bad)

    bad = []
    for m in re.finditer(rb"type=(faith|religion)\s+identity=(\d+)", g):
        kind, ident = m.group(1), m.group(2)
        if (kind == b"faith" and ident not in faiths) or (kind == b"religion" and ident not in religions):
            bad.append(f"variable type={kind.decode()} identity={ident.decode()} at byte {m.start():,}")
    rep.add("script variables point at faiths/religions that exist", "error", bad)


_COMMENT = re.compile(rb"#[^\n]*")
_TOP_DEF = re.compile(rb"(?m)^([A-Za-z0-9_][\w.\-:@]*)[ \t]*=")
_RULE_OPTION = re.compile(rb"(?m)^\t([A-Za-z_]\w*)[ \t]*=[ \t]*\{")
_CULTURE_REF = re.compile(rb"culture:([A-Za-z_]\w*)")


@dataclass
class GameData:
    """What the target game (and the active mods) define, read once and shared by every gamestate linted.

    words: every name in the binary, the script files and the reference save (the key-name check).
    defined: top-level keys of every common/ file -- the database entries a save may reference by name.
    """
    words: set[bytes] = field(default_factory=set)
    sources: list[str] = field(default_factory=list)        # kinds, for messages
    source_paths: list[str] = field(default_factory=list)   # what was actually read, for the report
    mods_missing: list[str] = field(default_factory=list)   # mods the save lists that are not installed
    defined: set[bytes] = field(default_factory=set)
    rule_options: set[bytes] = field(default_factory=set)
    on_actions: set[bytes] = field(default_factory=set)
    cultures: set[bytes] = field(default_factory=set)
    dynasty_templates: set[bytes] = field(default_factory=set)
    culture_refs: set[bytes] = field(default_factory=set)
    dna_length: int | None = None
    reference_types: set[bytes] = field(default_factory=set)   # every type= value a target-version save carries
    title_keys: set[str] = field(default_factory=set)          # landed titles the game (and mods) define
    title_conversion: dict[str, str] = field(default_factory=dict)


def _read_common(root: Path, data: GameData) -> None:
    for f in (root / "common").rglob("*.txt"):
        # most game files start with a UTF-8 byte-order mark, which would hide each file's first definition
        text = _COMMENT.sub(b"", f.read_bytes().removeprefix(b"\xef\xbb\xbf"))
        keys = set(_TOP_DEF.findall(text))
        data.defined |= keys
        parts = {p.lower() for p in f.relative_to(root / "common").parts[:-1]}
        if "game_rules" in parts:
            data.rule_options |= set(_RULE_OPTION.findall(text))
        if "on_action" in parts:
            data.on_actions |= keys
        if "cultures" in parts and "culture" in parts:
            data.cultures |= keys
        if "dynasties" in parts:
            data.dynasty_templates |= keys
    for sub in ("common", "events", "history"):
        for f in (root / sub).rglob("*.txt"):
            data.culture_refs |= set(_CULTURE_REF.findall(f.read_bytes()))


def load_game_data(game_dir: Path | None, reference: bytes | None, mod_dirs: list[Path], *,
                   reference_name: str | None = None, mods_missing: list[str] | None = None) -> GameData:
    data = GameData(mods_missing=list(mods_missing or []))
    if reference is not None:
        data.words.update(m.group(1) for m in _KEY.finditer(reference) if m.group(1))
        lengths = Counter(len(m.group(1)) for m in re.finditer(rb'[\n\t]dna="([^"]*)"', reference))
        data.dna_length = lengths.most_common(1)[0][0] if lengths else None
        data.reference_types = {m.group(2) for m in _REF_SCALAR.finditer(reference) if m.group(1) == b"type"}
        data.sources.append("reference save")
        data.source_paths.append(f"reference save: {reference_name or '(given as bytes)'}")
    if game_dir is not None:
        exe = game_dir.parent / "binaries" / ("ck3.exe" if (game_dir.parent / "binaries" / "ck3.exe").exists() else "ck3")
        if exe.exists():
            data.words.update(_words(exe.read_bytes()))
            data.sources.append(f"game binary ({exe.name})")
            data.source_paths.append(f"game binary: {exe}")
        for sub in ("common", "events", "history", "gui", "map_data"):
            for f in (game_dir / sub).rglob("*.txt"):
                data.words.update(_words(f.read_bytes()))
        _read_common(game_dir, data)
        data.sources.append("game script files")
        data.source_paths.append(f"game folder: {game_dir}")
    for d in mod_dirs:
        for f in d.rglob("*.txt"):
            data.words.update(_words(f.read_bytes()))
        _read_common(d, data)
        data.sources.append(f"mod {d.name}")
        data.source_paths.append(f"mod: {d}")
    for root in ([game_dir] if game_dir is not None else []) + list(mod_dirs):
        if (root / "common" / "landed_titles").is_dir():
            keys, conv = defined_title_keys(root)
            data.title_keys |= keys
            data.title_conversion.update(conv)
    return data


def known_words(game_dir: Path | None, reference: bytes | None, mod_dirs: list[Path]) -> tuple[set[bytes], list[str]]:
    """Key names a 1.20 save may legitimately carry, and the sources read (see load_game_data)."""
    d = load_game_data(game_dir, reference, mod_dirs)
    return d.words, d.sources


# Keys the target version's reader rejects at a place, learned from its own error.log ("Unexpected token").
# A fresh reference save cannot show these: it has no schemes, so it never shows what a scheme may hold.
REJECTED_AT = {
    # (section, key): evidence
    (b"schemes", b"owner_influence"): "1.20.1.2 error.log: Unexpected token: owner_influence (1,334 on the 987 save)",
    (b"culture_manager", b"exposure_type"): "1.20.1.2 error.log: Unexpected token: exposure_type",
    (b"culture_manager", b"exposure_marker"): "1.20.1.2 error.log: Unexpected token: exposure_marker",
    (b"schemes", b"ready"): "1.20.1.2 error.log: Unexpected token: ready",
    (b"landed_titles", b"localization_key"): "1.20.1.2 error.log: Unexpected token: localization_key",
    (b"landed_titles", b"renamed"): "1.20.1.2 error.log: Unexpected token: renamed (player-renamed titles)",
}
# entries rejected only at one depth below the section's entries: 1.20 accepts localization_key inside a title's
# title_name_data (where it writes it itself) and rejects it directly in the title (where 1.8.1 put it):
# the 987 load logged 5, the 5 title-level ones, with 3 more inside title_name_data unlogged
REJECTED_DEPTH = {(b"landed_titles", b"localization_key"): 1}
# Fields whose value names a database entry the reader looks up ("Failed to read key reference").
_REF_SCALAR = re.compile(rb'[\n\t ](modifier|type|combat_effect|important_action_type|story_cycle|nickname)'
                         rb'[ \t]*=[ \t]*"?([A-Za-z0-9_][\w.\-]*)"?(?=[\s}])')
_NUMBER = re.compile(rb"[\d.\-]+")
_REF_LIST = re.compile(rb"[\n\t ](modifiers|perk|settings)[ \t]*=[ \t]*\{([^{}]*)\}")
_ON_ACTION = re.compile(rb'[\n\t ]on_action[ \t]*=[ \t]*"?([A-Za-z_][\w.\-]*)"?')


def unresolved_references(g: bytes, data: GameData) -> Counter:
    """name -> occurrences, for values in reference fields that nothing in the game data defines.

    `type=` is overloaded: its quoted values name database entries (innovations, artifact visuals), its bare
    values are engine enums no common/ file defines (type=boolean, type=conquest_claim, type=revoked). Only
    quoted types are checked. Known miss: the bare type=prisoner_of_war (an imprisonment type 1.20 rejects;
    66 log lines on the 987 save, about 2% of the family).

    The opinions section is skipped: the reader does not log an unknown opinion modifier as a failed key
    reference (421 such names on the 987 save, none in its error.log)."""
    om = re.search(rb"(?m)^opinions[ \t]*=[ \t]*\{", g)
    skip = (om.start(), gs.match_brace(g, om.end() - 1)) if om else (-1, -1)
    refs = Counter()
    for m in _REF_SCALAR.finditer(g):
        field_, val = m.group(1), m.group(2)
        if _NUMBER.fullmatch(val) or val in data.defined or skip[0] <= m.start() < skip[1]:
            continue
        if field_ == b"type" and (g[m.start(2) - 1] != 0x22 or val in data.reference_types):   # 0x22 = '"'
            continue
        refs[val] += 1
    for m in _REF_LIST.finditer(g):
        if skip[0] <= m.start() < skip[1]:
            continue
        known = data.rule_options if m.group(1) == b"settings" else data.defined
        for tok in m.group(2).split():
            tok = tok.strip(b'"')
            if tok and tok not in known:
                refs[tok] += 1
    return refs


def check_families(g: bytes, rep: LintReport, data: GameData, idx: SectionIndex) -> None:
    """What the target game will log when it reads this save, family by family (severity "reject").

    The count is the number of log lines predicted, so it can be compared with the game's error.log."""
    if data.dna_length is not None:
        bad = Counter(len(m.group(1)) for m in re.finditer(rb'[\n\t]dna="([^"]*)"', g)
                      if len(m.group(1)) != data.dna_length)
        rep.add("Unexpected DNA string length", "reject",
                [f"{n:,} portraits with {length}-character DNA" for length, n in bad.most_common()],
                f"the target version writes {data.dna_length}-character DNA",
                gloss="Characters whose face data (DNA) is in an older format the current game rejects "
                      "(how those faces then look has not been checked yet)")
        if bad:
            rep.findings[-1].count = sum(bad.values())
    else:
        rep.skipped.append("DNA length: no reference save to learn the target length from")

    for (section, key), evidence in REJECTED_AT.items():
        b = idx.block(section.decode())
        depth = REJECTED_DEPTH.get((section, key))
        pat = (rb"\n" + b"\t" * depth + key + rb"=") if depth else (rb"[\n\t]" + key + rb"=")
        n = len(re.findall(pat, g[b.open:b.close])) if b is not None else 0
        if n:
            rep.add(f"Unexpected token: {key.decode()} (in {section.decode()})", "reject", [evidence],
                    gloss=f"A field the current game no longer has ({key.decode()} in {section.decode()}); "
                          "the game skips it when loading")
            rep.findings[-1].count = n

    if not data.defined:
        rep.skipped.append("key references, on actions, title templates, duplicate titles, dynasty templates, "
                           "cultures: no game folder to compare against")
        return
    refs = unresolved_references(g, data)
    rep.add("Failed to read key reference", "reject",
            [f"{k.decode(errors='replace')} x{n:,}" for k, n in refs.most_common()], limit=25,
            gloss="Names of modifiers, perks, innovations, artifact looks and the like that the current game "
                  "(and the active mods) no longer define; the game cannot read them, so those values are lost")
    if refs:
        rep.findings[-1].count = sum(refs.values())

    onact = Counter(m.group(1) for m in _ON_ACTION.finditer(g) if m.group(1) not in data.on_actions)
    rep.add("Unknown on action", "reject", [f"{k.decode()} x{n:,}" for k, n in onact.most_common()], limit=20,
            gloss="Queued events waiting on trigger points (on actions) that the current game or the active mods "
                  "no longer have; mostly mods that are not loaded")
    if onact:
        rep.findings[-1].count = sum(onact.values())

    lt = idx.block("landed_titles/landed_titles")
    if lt is not None and data.title_keys:
        # a title whose key the game no longer defines loads nameless ("not a valid title template"), and every
        # nameless title after the first is then a "Duplicate landed title name" (96 and 95 on the 987 save)
        dead = [k.decode() for k in re.findall(rb'(?m)^\tkey="?([\w\-\']+)"?', g[lt.open:lt.close])
                if not k.startswith(b"x_") and k.decode() not in data.title_keys
                and k.decode() not in data.title_conversion]
        rep.add("is not a valid title template", "reject", dead, limit=12,
                gloss="Titles the current game no longer defines; they load without a name")
        if len(dead) > 1:
            rep.add("Duplicate landed title name", "reject", [f"{len(dead)} nameless titles -> {len(dead) - 1} duplicates"],
                    gloss="Follows from the nameless titles above: each one after the first is logged as a "
                          "duplicate name")
            rep.findings[-1].count = len(dead) - 1

    dyn = idx.block("dynasties/dynasties")
    if dyn is not None and data.dynasty_templates:
        missing = [m.group(1) for m in re.finditer(rb'\n\tkey="?([^"\n]+)"?', g[dyn.open:dyn.close])
                   if m.group(1) not in data.dynasty_templates]
        rep.add("Unknown dynasty template", "reject", [f"dynasty template {k.decode()}" for k in missing], limit=12,
                gloss="Dynasties whose template the current game no longer has; the game makes up a cultural "
                      "name for them instead")

    cm = idx.block("culture_manager/cultures")
    if cm is not None and data.cultures:
        have = set(re.findall(rb'[\n\t]culture_template="?([\w\-]+)', g[cm.open:cm.close]))
        wanted = sorted(c for c in (data.culture_refs & data.cultures) if c not in have)
        rep.add("Failed to fetch a valid culture", "reject", [c.decode() for c in wanted],
                "names only: how many log lines follow depends on how often the scripts that ask for them run",
                limit=30, gloss="Cultures the game's own scripts use that your save does not have (added to the "
                                "game since the save's version, or renamed)")


def check_keys(g: bytes, rep: LintReport, words: set[bytes], sources: list[str]) -> None:
    if not sources:
        rep.skipped.append("unknown keys: no reference save, game folder or mods to compare against")
        return
    seen = Counter(m.group(1) for m in _KEY.finditer(g) if m.group(1))
    unknown = sorted(((k, n) for k, n in seen.items() if k not in words), key=lambda kn: -kn[1])
    rep.stats["distinct_keys"] = len(seen)
    rep.add("key names the game and the mods do not know", "info",
            [f"{k.decode(errors='replace')} x{n:,}" for k, n in unknown],
            "compared against: " + ", ".join(sources), limit=40,
            gloss="Names in the save that neither the game nor the mods define; usually harmless leftovers of "
                  "mods or removed content")


def lint_gamestate(g: bytes, *, game_dir: Path | None = None, reference: bytes | None = None,
                   mod_dirs: list[Path] | None = None, keys: bool = True,
                   known: GameData | tuple[set[bytes], list[str]] | None = None) -> LintReport:
    """All checks on one gamestate. ``known`` reuses a load_game_data() result (a run with two outputs builds
    it once; a (words, sources) pair is accepted too); otherwise it is built from game_dir, reference and
    mod_dirs. ``keys=False`` skips the game-data checks (key names and the reject families)."""
    rep = LintReport()
    idx = SectionIndex(g)
    check_structure(g, rep)
    check_ids(g, rep, idx)
    check_titles(g, rep, idx)
    check_contracts(g, rep, idx)
    check_references(g, rep, idx)
    if keys:
        if isinstance(known, tuple):
            data = GameData(words=known[0], sources=list(known[1]))
        else:
            data = known if known is not None else load_game_data(game_dir, reference, list(mod_dirs or []))
        rep.stats["game_data"] = list(data.source_paths or data.sources)   # which load the families predict
        if data.mods_missing:
            rep.stats["mods_not_installed"] = list(data.mods_missing)
        check_keys(g, rep, data.words, data.sources)
        check_families(g, rep, data, idx)
    else:
        rep.skipped.append("unknown keys and reject families: not requested")
    return rep


def listed_workshop_mods(meta: bytes, game_dir: Path | None) -> tuple[list[Path], list[str]]:
    """(installed folders, ids not installed) for the Workshop mods a save's meta_data lists (ugc_<id>.mod)."""
    if game_dir is None:
        return [], []
    content = game_dir.parent.parent.parent / "workshop" / "content" / "1158310"
    found, missing = [], []
    for wid in re.findall(rb'"mod/ugc_(\d+)\.mod"', meta):
        d = content / wid.decode()
        (found if d.is_dir() else missing).append(d if d.is_dir() else wid.decode())
    return found, missing


def workshop_mod_dirs(meta: bytes, game_dir: Path | None) -> list[Path]:
    """The Steam Workshop folders of the mods a save's meta_data lists (ugc_<id>.mod), when installed."""
    return listed_workshop_mods(meta, game_dir)[0]
