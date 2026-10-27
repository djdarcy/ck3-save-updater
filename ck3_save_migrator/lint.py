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
from collections import Counter, defaultdict
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


def _cycles(parent: dict) -> list[list]:
    return gs.parent_cycles(parent)


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


_TIER_RANK = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5}
_DOMAIN = re.compile(rb"\n\t\tdomain=\{([^}]*)\}")


def check_primary_titles(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """A ruler's primary title (the first entry of landed_data/domain) is his highest-tier title. When 1.20 makes a
    ruler independent it gives his other titles the primary as liege if the primary outranks them, else the
    primary's own liege, and never moves a barony off its county: a count whose primary is his barony gets his
    county made its own liege, and the game's "which kingdom" routine then loops forever (measured 2026-10-27: the
    987.11.8 freeze, decompiled in the vault). A first entry with no tier letter (a runtime x_ title) is not judged:
    the campaign's own saves carry one."""
    idx = idx or SectionIndex(g)
    lt, living = idx.block("landed_titles/landed_titles"), idx.block("living")
    if lt is None or living is None:
        return
    key = {}
    for m in _ENTRY_COL0.finditer(g, lt.open, lt.close):
        k = _T_FIELD[b"key"].search(g, m.end(), min(lt.close, m.end() + 600))
        if k:
            key[m.group(1)] = k.group(1).decode()
    bad = []
    for m in _ENTRY_COL0.finditer(g, living.open, living.close):
        end = g.find(b"\n}", m.end(), living.close)
        d = _DOMAIN.search(g, m.end(), end if end > 0 else living.close)
        if not d:
            continue
        ids = d.group(1).split()
        ranks = [_TIER_RANK.get(key.get(i, "?")[:1], 0) for i in ids]
        if ids and ranks[0] and ranks[0] < max(ranks):
            top = ids[ranks.index(max(ranks))]
            bad.append(f"{m.group(1).decode()}: primary {key.get(ids[0], ids[0].decode())}, "
                       f"holds {key.get(top, top.decode())}")
    rep.add("a ruler's primary title is his highest title", "error", bad,
            gloss="The first title in a ruler's domain is his primary; when it is outranked by another title he "
                  "holds (a count whose primary is his barony), the game can make a title its own liege and freeze")


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
    looped = []
    for field in (b"de_jure_liege", b"de_facto_liege"):
        parent = {i: int(f[field]) for i, f in titles.items()
                  if f[field] is not None and f[field].isdigit() and int(f[field]) in titles}
        for c in _cycles(parent):
            looped.append(f"{field.decode()}: " + " -> ".join((titles[i][b"key"] or b"?").decode() for i in c + c[:1]))
    rep.add("title liege chains end", "error", looped,
            gloss="A title that is its own liege, or a chain of lieges that returns to itself; the game's walk up "
                  "the chain never ends (the 8 November 987 freeze was a county that had become its own liege)")
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


def check_registries(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """INV-6 (census 2026-10-26): every culture made from a game template is on ``template_cultures``, the list of
    the cultures the game made from its definitions (vanilla 1.20 at 987: 244 of 244). A warning: whether the
    game resolves ``culture:<key>`` through the list is not measured yet."""
    idx = idx or SectionIndex(g)
    tl, cu = idx.block("culture_manager/template_cultures"), idx.block("culture_manager/cultures")
    if tl is None or cu is None:
        return
    listed = {int(x) for x in g[tl.open + 1:tl.close].split() if x.isdigit()}
    missing = []
    for e in gs.iter_entries(g, cu.open + 1, cu.close):
        if e.key is None or not e.key.isdigit() or int(e.key) in listed:
            continue
        m = re.search(rb"\n\t*culture_template=\"?([\w\-']+)", g[e.open:min(e.close, e.open + 2000)])
        if m:
            missing.append(f"{m.group(1).decode()} ({e.key.decode()})")
    rep.add("template cultures are registered", "warn", sorted(missing),
            gloss="Cultures made from a game template but missing from the game's list of them; scripts that "
                  "name the culture may not find it")


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


def check_realms(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """A ruler's realm agrees with his contracts: a count or higher who holds his primary title, and whose primary
    has a de facto liege held by another living character, has a vassal contract with that character (in
    vassal_contracts/active or /database, where 1.20 writes them). Measured 2026-10-27: play5 crashed at 989.1.1 with
    two such counts (handed-back titles left their old ruler's counts under the new holder, uncontracted); the same
    save without them, and the 1.20 game's own fresh save, have none. A baron in that state, and a domain that lists
    a title someone else holds, are warnings: the campaign's own saves carry some and run."""
    idx = idx or SectionIndex(g)
    lt, living = idx.block("landed_titles/landed_titles"), idx.block("living")
    if lt is None or living is None:
        return
    titles: dict[bytes, dict] = {}
    for m in _ENTRY_COL0.finditer(g, lt.open, lt.close):
        end = g.find(b"\n}", m.end(), lt.close)             # the title's own body: a short title must not read the next
        b = g[m.end():min(end if end > 0 else lt.close, m.end() + 4096)]
        titles[m.group(1)] = {k: (x.group(1) if (x := _T_FIELD[k].search(b)) else None)
                              for k in (b"key", b"holder", b"de_facto_liege")}
    key = lambda t: (titles.get(t, {}).get(b"key") or t).decode()       # noqa: E731
    doms: dict[bytes, list[bytes]] = {}
    for m in _ENTRY_COL0.finditer(g, living.open, living.close):
        end = g.find(b"\n}", m.end(), living.close)
        d = _DOMAIN.search(g, m.end(), end if end > 0 else living.close)
        doms[m.group(1)] = d.group(1).split() if d else []
    lieges: dict[bytes, set[bytes]] = defaultdict(set)
    for sec in ("vassal_contracts/active", "vassal_contracts/database"):
        b = idx.block(sec)
        for e in gs.iter_entries(g, *b.body) if b is not None else []:
            body = g[e.open:e.close]
            v, lg = re.search(rb"[\n\t ]vassal=(\d+)", body), re.search(rb"[\n\t ]liege=(\d+)", body)
            if v and lg:
                lieges[v.group(1)].add(lg.group(1))
    bad, barons, foreign = [], [], []
    for c, ts in doms.items():
        foreign += [f"{c.decode()} lists {key(t)}" for t in ts if titles.get(t, {}).get(b"holder") != c]
        if not ts or titles.get(ts[0], {}).get(b"holder") != c:
            continue
        lg = titles[ts[0]][b"de_facto_liege"]
        lh = titles.get(lg, {}).get(b"holder") if lg else None
        if lh is None or lh == c or lh not in doms or lh in lieges.get(c, ()):
            continue
        row = f"{c.decode()} ({key(ts[0])}) under {key(lg)} of {lh.decode()}, contracts with " \
              f"{sorted(x.decode() for x in lieges.get(c, ())) or 'nobody'}"
        (barons if _TIER_RANK.get(key(ts[0])[:1], 0) == 1 else bad).append(row)
    rep.add("a vassal ruler has a contract with his liege", "error", bad,
            gloss="A count or higher is a vassal of his primary title's de facto liege; without a contract with "
                  "that liege the game's realm code works on a contract that is not there (play5 crashed at 989.1.1)")
    rep.add("a baron has a contract with his county's holder", "warn", barons,
            gloss="A barony's liege is its county; a baron bound to someone else is out of step with his realm")
    rep.add("a ruler's domain lists only titles he holds", "warn", foreign)


_SCOPE = re.compile(rb"type=(\w+)\s+identity=(\d+)")
_TOP_KEY = re.compile(rb"(?m)^([A-Za-z_]\w*)=")
_NONE_IDS = {b"4294967295", b"18446744073709551615"}   # the game's "none", 32- and 64-bit (1.20 writes 1,065)


def _top_sections(g: bytes) -> tuple[list[int], list[str]]:
    tops = [(m.start(), m.group(1).decode()) for m in _TOP_KEY.finditer(g)]
    return [s for s, _ in tops], [k for _, k in tops]


def _section_at(secs: tuple[list[int], list[str]], pos: int) -> str:
    import bisect
    i = bisect.bisect_right(secs[0], pos) - 1
    return secs[1][i] if i >= 0 else "?"


def check_scopes(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """Stored script scopes (``type=<kind> identity=<id>``: event targets, scheme and story scopes, council-task
    targets, variables, memories) point at a character, title, province, artifact or faith that exists. A warning:
    a 1.8.1 save carries hundreds the game tolerates (the founding campaign: 282 characters in ``living``, 164 in
    triggered events; its migration adds none), while 1.20's own fresh save has none. After the 989.1.1 crash (a
    council task aimed at a province with no title link; djdarcy: "another generic case of a linter check we should
    have to validate all events / actions?"). The game's "none" values are not dangling."""
    idx = idx or SectionIndex(g)

    def ids(*paths):
        out = set()
        for p in paths:
            b = idx.block(p)
            if b is not None:
                out.update(e.key for e in gs.iter_entries(g, *b.body) if e.key)
        return out

    known = {b"char": ids(*CHAR_SECTIONS), b"lt": ids("landed_titles/landed_titles"), b"prov": ids("provinces"),
             b"artifact": ids("artifacts/artifacts"), b"faith": ids("religion/faiths")}
    secs = _top_sections(g)
    groups: Counter = Counter()
    first: dict = {}
    for m in _SCOPE.finditer(g):
        kind, i = m.group(1), m.group(2)
        if i in _NONE_IDS or kind not in known or not known[kind] or i in known[kind]:
            continue
        k = (kind.decode(), _section_at(secs, m.start()))
        groups[k] += 1
        first.setdefault(k, i.decode())
    rep.add("stored script scopes point at things that exist", "warn",
            [f"{n:,} {k[0]} scope(s) in {k[1]} (e.g. {first[k]})" for k, n in groups.most_common()],
            gloss="Event, scheme, story or council-task scopes naming a character, title, province, artifact or "
                  "faith the save does not have; old saves carry some the game tolerates, but one the game acts on "
                  "can fail late")


def check_units_passable(g: bytes, rep: LintReport, game_dir: Path, idx: SectionIndex | None = None) -> None:
    """Nothing in the save lives on, or is aimed at, a province the target map makes impassable: a map unit, a
    holding with a type or soldier pools, a soldier pool raised there, a siege, a council task's target. 1.20 writes
    none (its fresh save at the founding date: 0). 2026-10-27: 1.8.1 land in the Ordos (9542, 9532) became
    impassable mountains; the founding save kept a castle there, its pools, a siege, an army, and two council tasks
    aimed at it, and crashed at 989.1.1 (ck3+0xb064e8) when a councillor was appointed to one of the tasks. R22
    clears them."""
    from .mapdata import impassable_provinces
    bad_map = impassable_provinces(Path(game_dir))
    if not bad_map:
        return
    idx = idx or SectionIndex(g)
    bad = []

    def entries(path):
        b = idx.block(path)
        return gs.iter_entries(g, *b.body) if b is not None else []

    for e in entries("units"):
        loc = re.search(rb"\n\t+location=(\d+)", g[e.open:e.close])
        if e.key and loc and int(loc.group(1)) in bad_map:
            bad.append(f"unit {e.key.decode()} on province {loc.group(1).decode()}")
    for e in entries("provinces"):
        if e.key and e.key.isdigit() and int(e.key) in bad_map:
            h = re.search(rb"\n\t\tholding=\{", g[e.open:e.close])
            if h:
                hb = g[e.open + h.end():g.find(b"\n\t\t}", e.open + h.end(), e.close)]
                if b"type=" in hb or re.search(rb"\n\t+(?:levy|garrison)=", hb):
                    bad.append(f"province {e.key.decode()} keeps an old holding")
    for e in entries("armies/regiments"):
        o = re.search(rb"\n\t+origin=(\d+)", g[e.open:e.close])
        if e.key and o and int(o.group(1)) in bad_map:
            bad.append(f"soldier pool {e.key.decode()} raised on province {o.group(1).decode()}")
    for e in entries("sieges/sieges"):
        pv = re.search(rb"\n\t+province=(\d+)", g[e.open:e.close])
        if e.key and pv and int(pv.group(1)) in bad_map:
            bad.append(f"siege {e.key.decode()} of province {pv.group(1).decode()}")
    for e in entries("council_task_manager/active"):
        t = re.search(rb"\n\t+target=\{\s*type=prov\s+identity=(\d+)", g[e.open:e.close])
        if e.key and t and int(t.group(1)) in bad_map:
            bad.append(f"council task {e.key.decode()} aimed at province {t.group(1).decode()}")
    # any other stored script scope aimed at such a province (an event, a scheme, a story, a variable) is the same
    # hazard; memories are history and are left alone
    secs = _top_sections(g)
    for m in _SCOPE.finditer(g):
        if m.group(1) == b"prov" and int(m.group(2)) in bad_map:
            sec = _section_at(secs, m.start())
            if sec not in ("council_task_manager", "character_memory_manager"):
                bad.append(f"a scope in {sec} aimed at province {m.group(2).decode()}")
    rep.add("nothing lives on a province the new map made impassable", "error", bad,
            gloss="Something on, or aimed at, a province the new map made impassable; the game crashes when it "
                  "files it under that province")


def check_meta(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """The metadata the launcher and loader read first is well formed: every entry of meta_data has a key.
    2026-10-27: a playset fit replaced `mods={...}` from the key instead of the brace and left a bare `{ ... }`; the
    game answered "Failed to load SaveGame" and lint said nothing."""
    idx = idx or SectionIndex(g)
    b = idx.block("meta_data")
    if b is None:
        return
    kids = list(gs.iter_children(g, *b.body))
    keyless = [g[c.start:min(c.end, c.start + 60)].decode("utf-8", "replace").split("\n")[0] for c in kids
               if c.key is None]
    rep.add("meta_data entries all have a key", "error", keyless,
            gloss="A bare value or block in the save's metadata; the game refuses to load it")


def _entry_text(g: bytes, start: int) -> bytes:
    op = g.index(b"{", start)
    return g[start:gs.match_brace(g, op) + 1]


_COMPANY_FIELD = {k: re.compile(rb"\n\t+" + k + rb"=(\d+)") for k in (b"title", b"county")}


def check_companies(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """Mercenary companies and their titles, as 1.20 keeps them (measured 2026-10-27).

    A company whose title no longer exists crashes the game's yearly company pass (an access violation writing into
    the shared "none" title); the game itself destroys a company title when its captain dies without a valid heir
    (destroy_if_invalid_heir) and can leave the company pointing at it, so run this on the game's own re-saves too.
    The title must name its company back (``mercenary=<company id>``) when it names one at all. Every runtime (x_)
    title must be registered in ``landed_titles/dynamic_templates``: the game rejects an unregistered key at load
    ("is not a valid title template") whatever its number, and destroys the title in play."""
    idx = idx or SectionIndex(g)
    comps, lt = idx.block("mercenary_company_manager/mercenary_companies"), idx.block("landed_titles/landed_titles")
    if comps is None or lt is None:
        return
    titles = {}
    for m in _ENTRY_COL0.finditer(g, lt.open, lt.close):
        end = g.find(b"\n}", m.end(), lt.close)
        head = g[m.end():end if end > 0 else min(lt.close, m.end() + 2000)]
        k = _T_FIELD[b"key"].search(head)
        mc = re.search(rb"\n\tmercenary=(\d+)", head)
        titles[m.group(1)] = (k.group(1).decode() if k else "?", mc.group(1) if mc else None)
    dangling, no_backlink = [], []
    for e in gs.iter_entries(g, *comps.body):
        if not (e.key and e.key.isdigit()):
            continue
        body = g[e.start:e.end]
        t = _COMPANY_FIELD[b"title"].search(body)
        if not t:
            continue
        tid = t.group(1)
        if tid not in titles:
            dangling.append(f"company {e.key.decode()}: title {tid.decode()} does not exist")
            continue
        key, back = titles[tid]
        if back is not None and back != e.key:          # 1.8-era titles carry no mercenary= (the game adds it)
            no_backlink.append(f"company {e.key.decode()}: its title {key} names mercenary={back.decode() if back else '-'}")
    # every runtime title must be registered: 1.20 rejects an x_ key missing from landed_titles/dynamic_templates
    # ("... is not a valid title template") and destroys the title in play (measured 2026-10-27: 167 carried company
    # titles unregistered, 134 destroyed within a year, their companies left dangling, then the crash)
    dt = idx.block("landed_titles/dynamic_templates")
    registered = set(re.findall(rb'key="?([^"\s}]+)', g[dt.open:dt.close])) if dt else set()
    unregistered = sorted(k for k, _ in titles.values() if k.startswith("x_") and k.encode() not in registered)
    rep.add("a runtime title is registered in dynamic_templates", "error", unregistered,
            gloss="An x_ title whose key is not in landed_titles/dynamic_templates; the game rejects it at load and "
                  "destroys it in play, leaving whatever points at it dangling")
    rep.add("a mercenary company's title exists", "error", dangling,
            gloss="A company whose title is gone; the game's yearly pass over companies crashes on it")
    rep.add("a mercenary company's title names the company back", "error", no_backlink,
            gloss="A company title's mercenary= must be the company's own id")


def check_armies(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """Armies, their map units and their regiments point at things that exist, and point back (measured
    2026-10-27, after the 20 March 989 stop in the AI's army planner, which splits army groups until the armies it
    moves carry no strength: an army whose links do not resolve is the data shape that would feed it).

    An army's ``unit`` is a unit whose ``army`` is that army; its ``regiments`` are army regiments whose ``army``
    is that army; a regiment's ``chunks`` draw on soldier pools in ``armies/regiments``; commanders, unit owners
    and knights are living characters. An army with no soldiers is a warning: the game makes one in passing (seen
    once in its own 988 autosave), but a migrated save should carry none."""
    idx = idx or SectionIndex(g)
    ab, rb_, pb, ub, lv = (idx.block(p) for p in ("armies/armies", "armies/army_regiments", "armies/regiments",
                                                   "units", "living"))
    if ab is None or ub is None or lv is None:
        return
    living = {e.key for e in gs.iter_entries(g, *lv.body) if e.key}
    armies, regs, units = (({e.key: g[e.open:e.close] for e in gs.iter_entries(g, *b.body) if e.key} if b else {})
                           for b in (ab, rb_, ub))
    pools = {e.key for e in gs.iter_entries(g, *pb.body) if e.key} if pb else set()
    bad, empty = [], []
    strength = Counter()
    for rid, t in regs.items():
        army = _val(t, b"army")
        if army is not None and army not in armies:
            bad.append(f"regiment {rid.decode()}: army {army.decode()} does not exist")
        knight = _val(t, b"knight")
        if knight is not None and knight not in living:
            bad.append(f"regiment {rid.decode()}: knight {knight.decode()} is not living")
        for p in re.findall(rb"regiment=(\d+)", t):
            if pools and p not in pools:
                bad.append(f"regiment {rid.decode()}: soldier pool {p.decode()} does not exist")
        cur, size = re.search(rb"current=([\d.]+)", t), re.search(rb"cached=\{\s*size=(\d+)", t)
        strength[army] += float(cur.group(1)) if cur else (int(size.group(1)) if size else 0)
    for aid, t in armies.items():
        a = aid.decode()
        u = _val(t, b"unit")
        if u is not None and u not in units:
            bad.append(f"army {a}: unit {u.decode()} does not exist")
        elif u is not None and _val(units[u], b"army") != aid:
            bad.append(f"army {a}: its unit {u.decode()} names another army")
        c = _val(t, b"commander")
        if c is not None and c not in living:
            bad.append(f"army {a}: commander {c.decode()} is not living")
        for r in _list(t, b"regiments"):
            if not r.isdigit():
                break                                  # a nested regiments={ { ... } } form, not an id list
            if r not in regs:
                bad.append(f"army {a}: regiment {r.decode()} does not exist")
            elif _val(regs[r], b"army") != aid:
                bad.append(f"army {a}: its regiment {r.decode()} names another army")
        if strength[aid] <= 0:
            empty.append(f"army {a} (commander {(c or b'-').decode()})")
    for uid, t in units.items():
        army, owner = _val(t, b"army"), _val(t, b"owner")
        if army is not None and army not in armies:
            bad.append(f"unit {uid.decode()}: army {army.decode()} does not exist")
        if owner is not None and owner not in living:
            bad.append(f"unit {uid.decode()}: owner {owner.decode()} is not living")
    rep.stats["armies"] = {"armies": len(armies), "units": len(units), "regiments": len(regs)}
    rep.add("army links resolve both ways", "error", bad,
            gloss="An army, map unit or regiment that names something missing, or something that does not name it "
                  "back; the game's army code reads these links without checking them")
    rep.add("armies have soldiers", "warn", empty,
            gloss="An army whose regiments hold no men; the AI's army planner splits groups by strength")


def check_ai(g: bytes, rep: LintReport, idx: SectionIndex | None = None) -> None:
    """The AI's saved war state (``ai/war_coordinator_db``, ``ai/war_plan_db``, ``ai/ai_strategies``), measured
    2026-10-27 after the 20 March 989 / 990 stops.

    A war coordinator with no ``war_stance`` or a ``supply_limit`` of 0 was created and never run; 1.20 writes none
    (0 of 204 and 214 in its own autosaves; lowest supply limit 1000), never computes them after loading, and its AI
    then splits an army stack to fit under a supply limit of 0 without end. Every war plan names a coordinator that
    exists, and every plan an AI strategy lists exists: a dangling plan id in a strategy crashed the load."""
    idx = idx or SectionIndex(g)
    wc, wp, st = (idx.block(p) for p in ("ai/war_coordinator_db", "ai/war_plan_db", "ai/ai_strategies"))
    if wc is None:
        return
    coords, unrun = set(), []
    for e in gs.iter_entries(g, *wc.body):
        if not e.key:
            continue
        coords.add(e.key)
        body = g[e.open:e.close]
        sl = _val(body, b"supply_limit")
        if _val(body, b"war_stance") is None or (sl is not None and float(sl) <= 0):
            unrun.append(f"coordinator {e.key.decode()} (war {(_val(body, b'war') or b'?').decode()}, "
                         f"supply_limit {(sl or b'-').decode()})")
    plans, dangling = set(), []
    if wp is not None:
        for e in gs.iter_entries(g, *wp.body):
            if not e.key:
                continue
            plans.add(e.key)
            c = _val(g[e.open:e.close], b"war_coordinator")
            if c is not None and c not in coords:
                dangling.append(f"war plan {e.key.decode()}: coordinator {c.decode()} does not exist")
    if st is not None:
        for m in re.finditer(rb"war_plans=\{([^{}]*)\}", g[st.open:st.close]):
            for pid in m.group(1).split():
                if pid not in plans:
                    dangling.append(f"an AI strategy lists war plan {pid.decode()}, which does not exist")
    rep.add("AI war coordinators have been run", "error", unrun,
            gloss="A war coordinator with no war stance or a supply limit of 0; the game never computes them after "
                  "loading, and its AI then splits an army stack without end (the 20 March 989 stop)")
    rep.add("AI war plans and strategies point at things that exist", "error", dangling,
            gloss="A war plan whose coordinator is gone, or a strategy listing a plan that is gone; the game "
                  "crashes loading it")


def check_reference_titles(g: bytes, rep: LintReport, reference: bytes, idx: SectionIndex | None = None) -> None:
    """Every title a fresh game of the target version has (the reference save) exists in the save, held or not
    (2026-10-27: the migrated founding save lacked 323, all unheld and titular in the fresh game, among them
    h_roman_empire; the game's scripts name 252 of them and fail on each). Runtime x_ titles are a game's own and
    are not compared; a title the engine is measured to create itself is listed as info, not an error."""
    from .rules.transplant_1_20 import ENGINE_CREATED     # here, not at the top: the rules import lint's helpers
    idx = idx or SectionIndex(g)
    lt = idx.block("landed_titles/landed_titles")
    try:
        rlt = gs.locate(reference, "landed_titles/landed_titles")
    except gs.GamestateError:
        return
    if lt is None:
        return
    key = re.compile(rb'\n\tkey="?([^"\s]+)"?')
    have = set(key.findall(g, lt.open, lt.close))
    want = {k for k in key.findall(reference, rlt.open, rlt.close) if not k.startswith(b"x_")}
    missing = sorted(k.decode() for k in want - have)
    rep.add("titles a fresh game has exist in the save", "error", [k for k in missing if k not in ENGINE_CREATED],
            limit=12, gloss="Titles the target version's fresh game has (most of them empty, waiting to be created or "
                            "earned) that the save lacks; the game's scripts that name them fail")
    rep.add("titles the game creates by itself", "info", [k for k in missing if k in ENGINE_CREATED],
            gloss="Titles the fresh game has that the engine is measured to create in a migrated save; left to it")


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
    rite_without_db = []                  # S1: rite ids in a save with no rites database (a half migration)
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
                elif not rites and i >= 0:
                    rite_without_db.append(f"{sec}/{ids[i].group(1).decode()}: rite={val.decode()}")
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
    rep.add("characters with a rite have a rites database", "error", rite_without_db,
            gloss="Characters carry 1.20 rite numbers but the save has no rites database: people were copied in "
                  "without the religion rules (R8), so their faith points at nothing")
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
    check_primary_titles(g, rep, idx)
    check_companies(g, rep, idx)
    check_armies(g, rep, idx)
    check_ai(g, rep, idx)
    if reference is not None:
        check_reference_titles(g, rep, reference, idx)
    check_contracts(g, rep, idx)
    check_realms(g, rep, idx)
    check_meta(g, rep, idx)
    check_scopes(g, rep, idx)
    if game_dir is not None:
        check_units_passable(g, rep, game_dir, idx)
    check_registries(g, rep, idx)
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
