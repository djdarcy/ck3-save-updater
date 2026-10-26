"""The transplant engine: copy objects from a reference gamestate into a save, through R13 (translate.py).

Rules R14 (new titles), R15 (dead titles) and R16 (people) PLAN into one ``Transplant``: they name the reference
titles, provinces and people to bring. ``close()`` then carries what those objects need (houses, dynasties,
cultures without a join, coats of arms, council tasks, court positions, vassal contracts, memories, artifacts,
regiments, ai strategies) to a fixpoint, and ``edits()`` writes everything in one pass. Planning before writing
is required by the edge policy: a reference is kept only when its target exists in the output, and that is
known only once every rule has planned (a title written alone would lose the holder R16 brings).

What the write does, proven by the Unit 2 proof-of-concept (a transplanted realm loads; the same without the
offset crashes the game):

* every copied entry is rewritten by ``translate.rewrite_entry`` with ``keep`` = the edge policy, and inserted at
  the start of the closing brace's line of its section, so entries start at column 0 as the game writes them;
* SEAMS: a new title whose de jure liege is a title the save already has is appended to that parent's
  ``de_jure_vassals`` (the parent's own entry is otherwise untouched). The other direction is not stitched: a new
  title's de facto liege, or a de jure child, that is an existing title is dropped and counted, because the
  campaign's own titles keep the campaign's structure (design G10);
* COUNTERS: ``coat_of_arms/next_id`` is raised above the copied coats (the engine allocates coats from it);
* LOOKUPS: trait names the save lacks are appended to ``traits_lookup``; copied history characters get their
  ``character_lookup`` entries.

The engine allocates new objects into the lowest free slots, including the gaps between copied slots (Unit 2
months run), so nothing may assume the copied indices are contiguous, and no reference may dangle.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import gamestate as gs
from . import idschema as S
from . import translate as T

CHARACTER_KINDS = ("living", "dead_unprunable")
# per-object kinds carried with a copied person or title: space -> the reference database kind
CARRIED: dict[str, str] = {
    "house": "dynasties/dynasty_house", "dynasty": "dynasties/dynasties", "culture": "culture_manager/cultures",
    "council_task": "council_task_manager/active", "court_position": "court_positions/database",
    "vassal_contract": "vassal_contracts/database", "memory": "character_memory_manager/database",
    "artifact": "artifacts/artifacts", "coat_of_arms": "coat_of_arms/coat_of_arms_manager_database",
    "regiment": "armies/regiments",
    "story": "stories/active", "mercenary": "mercenary_company_manager/mercenary_companies",
    # 1.20 systems the save does not have yet (their spaces are absent, so their ids carry over unchanged)
    "domicile": "domiciles/database", "clerical_region": "clerical_region_manager/database",
    "tax_slot": "tax_slot_manager/database", "diarchy": "diarchies/database",
    "holy_order": "holy_orders/holy_orders",
    # China's system state (Unit 5b): the situations, their sub-regions and participant groups
    "situation": "situation_manager/database", "situation_sub_region": "situation_sub_region_manager/database",
    "situation_group": "situation_participant_group_manager/database",
}
# anonymous pair lists carried when BOTH people are copied (a campaign person never gains a relation the
# reference's history invented)
# entries carried because they point at a carried owner (nothing points at them):
# space -> (kind, owner field, the owner's space)
OWNED: dict[str, tuple[str, bytes, str]] = {
    "regiment": ("armies/regiments", b"owner", "character"),       # a copied ruler's men-at-arms
    "story": ("stories/active", b"owner", "character"),            # a copied person's story (Tai migrations, ...)
    # djdarcy 2026-10-26: the new regions get the companies the 1.20 game has; a company sits in a county and
    # brings its runtime x_ title and its regiments (below)
    "mercenary": ("mercenary_company_manager/mercenary_companies", b"county", "title"),
}
PAIR_LISTS = {"relations/active_relations": (b"first", b"second"), "opinions/active_opinions": (b"owner", b"target")}
# carried from any copied object; the rest (council tasks, contracts, ...) only from a copied person
CARRIED_FROM_ANY = frozenset({"house", "dynasty", "culture", "coat_of_arms", "regiment", "domicile",
                              "clerical_region", "holy_order", "situation", "situation_sub_region",
                              "situation_group"})
# objects that bind characters: carried only when every named party is in the output
REQUIRED: dict[str, tuple[str, ...]] = {"vassal_contract": ("liege", "vassal"), "council_task": ("court_owner",)}
# the relatives a copied ruler or courtier brings (design: spouse, child, real father; one hop)
FAMILY = ("family_data/spouse", "family_data/primary_spouse", "family_data/child/*", "family_data/real_father",
          "family_data/former_spouses/*", "family_data/betrothed", "family_data/concubine",
          "family_data/concubinist")
TITLES = "landed_titles/landed_titles"
COUNTIES = "county_manager/counties"
# the lists of objects the game made from its own definitions at game start (ascending ids; measured 2026-10-26 in
# the reference and the campaign: neither is positional, the reference lists 0..n-1): a carried object the
# reference lists is listed in the output too (census defects 5-7)
REGISTRIES: dict[str, str] = {"culture_manager/template_cultures": "culture", "dynasties/static_dynasties": "dynasty",
                              "dynasties/static_dynasty_houses": "house"}
NAME_MAP = "coat_of_arms/coat_of_arms_manager_name_map"
_RUNTIME_KEY = re.compile(rb"^(x_(?:[a-z]+_)?)(\d+)$")      # x_mc_6 -> (x_mc_, 6); x_12 -> (x_, 12)
_PAIR = re.compile(rb"(?m)^[ \t]*([^\s={}]+)=(\d+)[ \t]*$")    # a whole-line key=number pair (name map)


@dataclass
class Report:
    planned: Counter = field(default_factory=Counter)          # what each rule asked for: (rule, kind) -> n
    inserted: Counter = field(default_factory=Counter)         # save section -> entries written
    seams: int = 0                                             # new children appended to an existing parent
    seam_parents: int = 0
    rewrite: T.RewriteReport = field(default_factory=T.RewriteReport)
    coa_next_id: tuple[int | None, int | None] = (None, None)
    traits_appended: int = 0
    character_lookup_added: int = 0
    sections_created: list[str] = field(default_factory=list)
    not_carried: Counter = field(default_factory=Counter)      # space -> objects left out for a missing party
    owner_carried: Counter = field(default_factory=Counter)    # space -> objects carried for their carried owner
    runtime_keys_renamed: dict = field(default_factory=dict)   # carried x_ title key -> the free key it took
    registered: Counter = field(default_factory=Counter)       # registry list -> carried ids appended
    name_map_added: Counter = field(default_factory=Counter)   # "title" / "other" -> coat name-map pairs appended
    expansion_orders: list[str] = field(default_factory=list)  # holy orders added onto campaign land
    collisions: Counter = field(default_factory=Counter)       # space -> copied slots already used by the save
    leases_added: list[str] = field(default_factory=list)      # "<campaign title key> -> <order title key>"

    def as_dict(self) -> dict:
        r = self.rewrite
        return {"planned": {f"{a} {b}": n for (a, b), n in self.planned.items()},
                "inserted": dict(self.inserted), "sections_created": self.sections_created,
                "not_carried": dict(self.not_carried), "owner_carried": dict(self.owner_carried),
                "runtime_keys_renamed": self.runtime_keys_renamed,
                "registered": dict(self.registered), "name_map_added": dict(self.name_map_added),
                "collisions": sum(self.collisions.values()), "collisions_by_space": dict(self.collisions),
                "expansion_content_added": {"holy_orders": self.expansion_orders, "leases": self.leases_added},
                "seams": self.seams, "seam_parents": self.seam_parents,
                "coa_next_id": list(self.coa_next_id), "traits_appended": self.traits_appended,
                "character_lookup_added": self.character_lookup_added,
                "translated": dict(r.translated), "dropped_total": sum(r.dropped.values()),
                "dropped": {f"{k} | {p}": n for (k, p), n in r.dropped.most_common()},
                "unlisted": {f"{k} | {p}": n for (k, p), n in r.unlisted.items()},
                "unknown_types": dict(r.unknown_types), "to_pruned": dict(r.to_pruned)}


def _set_employer(text: bytes, employer: int) -> bytes:
    """A rewritten character entry, placed in ``employer``'s court (an employer it had is replaced)."""
    emp = f"employer={employer}".encode()
    m = re.search(rb"\n(\t+)employer=\d+", text)
    if m:
        return text[:m.start()] + b"\n" + m.group(1) + emp + text[m.end():]
    m = re.search(rb"\n\tcourt_data=\{\n", text)
    if m:
        return text[:m.end()] + b"\t\t" + emp + b"\n" + text[m.end():]
    close = text.rstrip().rfind(b"}")
    return text[:close] + b"\tcourt_data={\n\t\t" + emp + b"\n\t}\n" + text[close:]


class Transplant:
    """A plan of reference objects to copy into a save, and the one write that carries it out."""

    def __init__(self, save: bytes, ref: bytes, tr: T.Translator | None = None):
        self.save, self.ref = save, ref
        self.tr = tr or T.Translator.build(save, ref)
        self.carry: dict[str, set[int]] = defaultdict(set)     # space -> reference ids to copy
        self.employer: dict[int, int] = {}       # reference character -> SAVE character whose court they join
        self.expansion_orders = False             # carry holy orders that lease campaign land (R14's flag)
        self.report = Report()
        self._ent: dict[str, dict[int, gs.Block]] = {}
        self._refs: dict[tuple[str, int], list] = {}
        self._closed = False

    # -- reference lookups --------------------------------------------------
    def entries(self, kind: str) -> dict[int, gs.Block]:
        if kind not in self._ent:
            self._ent[kind] = dict(T.entries(self.ref, kind))
        return self._ent[kind]

    def character(self, i: int) -> tuple[str, gs.Block] | None:
        for kind in ("living", "dead_unprunable"):
            e = self.entries(kind).get(i)
            if e is not None:
                return kind, e
        return None

    def references(self, kind: str, i: int, e: gs.Block):
        k = (kind, i)
        if k not in self._refs:
            self._refs[k] = list(T.references(self.ref, e, kind))
        return self._refs[k]

    def county_records(self) -> dict[str, gs.Block]:
        """The reference's county_manager records, by county title key."""
        if "_counties" not in self._ent:
            try:
                b = gs.locate(self.ref, COUNTIES)
                self._ent["_counties"] = {e.key.decode(): e for e in gs.iter_entries(self.ref, *b.body) if e.key}
            except gs.GamestateError:
                self._ent["_counties"] = {}
        return self._ent["_counties"]

    def title_keys(self) -> dict[int, str]:
        """reference title id -> key."""
        if "_tkeys" not in self._ent:
            self._ent["_tkeys"] = {i: (k.decode() if (k := T._depth0(self.ref, e, T._KEY)) else "?")
                                   for i, e in self.entries(TITLES).items()}
        return self._ent["_tkeys"]

    def save_title_key(self, save_id: int) -> str:
        if "_skeys" not in self._ent:
            self._ent["_skeys"] = {i: k.decode() for k, i in T.keyed(self.save, TITLES).items()}
        return self._ent["_skeys"].get(save_id, "")

    def holy_order_titles(self) -> dict[int, tuple[int | None, list[int]]]:
        """reference holy order id -> (its own title, the titles it leases)."""
        out = {}
        for i, e in self.entries("holy_orders/holy_orders").items():
            own, leased = None, []
            for path, sp, v in self.references("holy_orders/holy_orders", i, e):
                if path == "title":
                    own = v
                elif path == "titles/*":
                    leased.append(v)
            out[i] = (own, leased)
        return out

    def title_holders(self, titles) -> dict[int, int]:
        """reference title id -> its holder (a reference character id), for the given titles."""
        out = {}
        for t in titles:
            e = self.entries(TITLES).get(t)
            if e is None:
                continue
            m = re.search(rb"\n\tholder=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)])
            if m and int(m.group(1)) != T.NONE:
                out[t] = int(m.group(1))
        return out

    def people_closure(self, holders: set[int]) -> dict[str, set[int]]:
        """The people a set of rulers brings (design R16): the rulers, their courtiers (employer = a ruler), and
        the close family of both, one hop, living or dead (spouses, children, real father, and parents found
        through the parents' child lists). Joined (history) characters are left to the campaign by ``add``."""
        employer: dict[int, list[int]] = defaultdict(list)
        parents: dict[int, list[int]] = defaultdict(list)
        for kind in CHARACTER_KINDS:
            for i, e in self.entries(kind).items():
                for path, _, v in self.references(kind, i, e):
                    if path in ("court_data/employer", "court_data/host"):     # courtiers, and guests at court
                        employer[v].append(i)
                    elif path == "family_data/child/*":
                        parents[v].append(i)
        rulers = {h for h in holders if self.character(h) is not None}
        courtiers = {c for h in rulers for c in employer[h]} - rulers
        core = rulers | courtiers
        family = set()
        for x in core:
            kind, e = self.character(x)
            family |= {v for path, _, v in self.references(kind, x, e) if path in FAMILY}
            family |= set(parents[x])
        family = {f for f in family - core if self.character(f) is not None}
        return {"rulers": rulers, "courtiers": courtiers, "family": family}

    # -- planning -----------------------------------------------------------
    def add(self, space: str, ids, rule: str) -> None:
        ids = set(ids) - set(self.tr.spaces[space].join)        # a joined object is the campaign's already
        self.carry[space] |= ids
        self.report.planned[(rule, space)] += len(ids)
        self._closed = False

    def close(self) -> None:
        """Carry what the planned objects need, to a fixpoint."""
        frontier = [(sp, i) for sp in ("character", "title", "province") for i in self.carry[sp]]
        frontier += [(sp, i) for sp in CARRIED for i in self.carry[sp]]
        seen = set(frontier)

        def forward(frontier):
            while frontier:
                sp, i = frontier.pop()
                got = self._entry(sp, i)
                if got is None:
                    continue
                kind, e = got
                for _, rsp, v in self.references(kind, i, e):
                    if rsp not in CARRIED or v in self.tr.spaces[rsp].join or (rsp, v) in seen:
                        continue
                    if rsp not in CARRIED_FROM_ANY and sp != "character":
                        continue
                    if v in self.entries(CARRIED[rsp]):
                        self.carry[rsp].add(v)
                        seen.add((rsp, v))
                        frontier.append((rsp, v))

        forward(frontier)
        before = {sp: set(ids) for sp, ids in self.carry.items()}
        # owner back-references (R16's closure amended 2026-10-26): an entry that points at a carried owner while
        # nothing points at it comes too, e.g. a copied ruler's men-at-arms (regiment owner=<character>, measured:
        # 3,626 of the reference's 16,519 regiments, every value a living character)
        company_titles: list[int] = []
        for sp, (kind, fld, owner_sp) in OWNED.items():
            join = self.tr.spaces[sp].join
            for i, e in self.entries(kind).items():
                if i in self.carry[sp] or i in join:
                    continue
                text = self.ref[e.start:min(e.end, e.start + 2000)]
                m = re.search(rb"[\n\t]" + fld + rb"=(\d+)", text)
                if not (m and int(m.group(1)) in self.carry[owner_sp]):
                    continue
                self.carry[sp].add(i)
                self.report.owner_carried[sp] += 1
                if sp == "mercenary":           # the company's own x_ title and its regiments come with it
                    t = re.search(rb"[\n\t]title=(\d+)", text)
                    if t:
                        self.carry["title"].add(int(t.group(1)))
                        company_titles.append(int(t.group(1)))
                    r = re.search(rb"[\n\t]regiments=\{([^}]*)\}", text)
                    for rid in (r.group(1).split() if r else []):
                        self.carry["regiment"].add(int(rid))
        # a company's captain holds its x_ title and leads it: carried as R16 carries a ruler (the captain, the
        # court, close family). Without them the title is unheld and every trigger on the company's leader fails
        # (soak 2026-10-26 03:42: "mercenary_company_leader [Failed context switch]" 2,543 in five minutes)
        if company_titles:
            cj = set(self.tr.spaces["character"].join)
            people = self.people_closure(set(self.title_holders(company_titles).values()))
            for group, label in (("rulers", "captain"), ("courtiers", "company court"), ("family", "company family")):
                new = people[group] - cj - self.carry["character"]
                self.carry["character"] |= new
                if new:
                    self.report.owner_carried[label] += len(new)
        # what the owner pass added has forward references of its own (an x_ title's holder, ...): follow them
        added = [(sp, i) for sp, ids in self.carry.items() for i in ids - before.get(sp, set())
                 if sp in ("character", "title", "province") or sp in CARRIED]
        seen.update(added)
        forward(added)
        self.carry["ai"] = {p for p in self.carry["character"] if p in self.entries("ai/ai_strategies")}
        # an object that binds two parties is carried only when both are in the output (a vassal contract
        # carried with its liege but without its vassal binds nobody); the references to it are then dropped
        for sp, fields in REQUIRED.items():
            kind = CARRIED[sp]
            for i in list(self.carry[sp]):
                refs = {p: v for p, rsp, v in self.references(kind, i, self.entries(kind)[i]) if rsp == "character"}
                if not all(f in refs and self.keep("character", refs[f]) for f in fields):
                    self.carry[sp].discard(i)
                    self.report.not_carried[sp] += 1
        # a holy order comes only with its own title and every title it leases: one that leases campaign land
        # would plant the reference's institution in the campaign's world
        join = self.tr.spaces["title"].join
        for i, (own, leased) in self.holy_order_titles().items():
            if i not in self.carry["holy_order"]:
                continue
            ok = own in self.carry["title"] and all(t in self.carry["title"] or (self.expansion_orders and t in join)
                                                    for t in leased)
            if not ok:
                self.carry["holy_order"].discard(i)
                self.report.not_carried["holy_order"] += 1
            elif any(t in join for t in leased):
                self.report.expansion_orders.append(self.title_keys().get(own, str(own)))
        self._closed = True

    def _entry(self, sp: str, i: int):
        if sp == "character":
            return self.character(i)
        kind = {"title": TITLES, "province": "provinces"}.get(sp) or CARRIED.get(sp)
        e = self.entries(kind).get(i) if kind else None
        return (kind, e) if e is not None else None

    # -- the edge policy ----------------------------------------------------
    def keep(self, space: str, v: int, path: str = "") -> bool:
        m = self.tr.spaces[space]
        if space in S.IDENTITY:
            return True
        if v in m.join:
            if space == "title" and path == "de_facto_liege" and self.save_title_key(m.join[v]).startswith("c_"):
                return True             # a new barony in an existing county: the engine requires de facto = de jure
            if space == "title" and (path == "de_facto_liege" or path.startswith("de_jure_vassals")):
                return False            # campaign titles keep the campaign's structure (only the seam joins)
            if space == "title" and path in ("landed_data/domain/*", "landed_data/realm_capital",
                                             "dead_data/domain/*"):
                return False            # a copied ruler never holds a campaign title: the campaign's holder does
            return v not in m.join_pruned
        return v in self.carry[space]

    # -- the write ----------------------------------------------------------
    def edits(self) -> gs.EditPass:
        """Every edit of the transplant, against the save's gamestate, as one EditPass (rule "transplant")."""
        if not self._closed:
            self.close()
        ep = gs.EditPass()
        rep = self.report
        payload: dict[str, list[bytes]] = defaultdict(list)

        def rewrite(kind, e):
            return T.rewrite_entry(self.ref, e, kind, self.tr, rep.rewrite, self.keep)

        for p in sorted(self.carry["character"]):
            kind, e = self.character(p)
            text = rewrite(kind, e)
            if p in self.employer:
                text = _set_employer(text, self.employer[p])
            payload[kind].append(text)
        for p in sorted(self.carry["ai"]):
            payload["ai/ai_strategies"].append(rewrite("ai/ai_strategies", self.entries("ai/ai_strategies")[p]))
        # runtime titles (x_mc_6, x_x_12) are numbered per save, so a carried one may reuse a key the campaign has:
        # it takes the next free number of its prefix (e2e 2026-10-26: x_mc_6 named both 12116 and 30389)
        used = set(T.keyed(self.save, TITLES))
        nxt: dict[bytes, int] = {}
        for k in used:
            m = _RUNTIME_KEY.match(k)
            if m:
                nxt[m.group(1)] = max(nxt.get(m.group(1), 0), int(m.group(2)) + 1)
        for t in sorted(self.carry["title"]):
            text = rewrite(TITLES, self.entries(TITLES)[t])
            k = self.title_keys().get(t, "").encode()
            m = _RUNTIME_KEY.match(k)
            if m and k in used:
                new = m.group(1) + str(nxt.get(m.group(1), 1)).encode()
                nxt[m.group(1)] = nxt.get(m.group(1), 1) + 1
                text = re.sub(rb'([\n\t]key=)"?' + re.escape(k) + rb'"?(?=\s)', lambda x: x.group(1) + new, text, count=1)
                rep.runtime_keys_renamed[k.decode()] = new.decode()
                k = new
            used.add(k)
            payload[TITLES].append(text)
        # a database keyed BY a copied record: every carried county brings its county_manager record (R16's
        # closure amended 2026-10-26: forward references, databases keyed by a copied record, owner back-references)
        records = self.county_records()
        for t in sorted(self.carry["title"]):
            e = records.get(self.title_keys().get(t, ""))
            if e is not None:
                payload[COUNTIES].append(rewrite(COUNTIES, e))
        for pv in sorted(self.carry["province"]):
            payload["provinces"].append(rewrite("provinces", self.entries("provinces")[pv]))
        for sp, kind in CARRIED.items():
            for i in sorted(self.carry[sp]):
                payload[kind].append(rewrite(kind, self.entries(kind)[i]))
        created = []
        for kind, items in payload.items():
            body = b"".join(x + b"\n" for x in items)
            try:
                sec = self._target(kind)
            except T.TranslationError:
                created.append((kind, body))       # a 1.20 system the save has never had: the section is new
                rep.inserted[kind] += len(items)
                continue
            at = self.save.rfind(b"\n", 0, sec.close) + 1
            ep.add(gs.Edit(at, at, body, "transplant", kind))
            rep.inserted[self._target_name(kind)] += len(items)
        for kind, body in created:
            parts = kind.split("/")
            text = body
            for depth, name in reversed(list(enumerate(parts))):
                text = b"\t" * depth + name.encode() + b"={\n" + text + b"\t" * depth + b"}\n"
            end = len(self.save)
            ep.add(gs.Edit(end, end, text, "transplant", f"new section {kind}"))
            rep.sections_created.append(kind)

        self._seams(ep)
        self._leases(ep)
        self._pairs(ep)
        self._events(ep)
        self._counters_and_lookups(ep)
        self._registries(ep)
        self._collisions()
        return ep

    def _registries(self, ep: gs.EditPass) -> None:
        """The game-start lists (REGISTRIES) and the coat name map gain the carried objects the reference lists.
        A save without the list is left alone; a name-map key the campaign has keeps the campaign's coat."""
        for path, sp in REGISTRIES.items():
            try:
                rb_, sb = gs.locate(self.ref, path), gs.locate(self.save, path)
            except gs.GamestateError:
                continue
            m = self.tr.spaces[sp]
            listed = {int(x) for x in self.ref[rb_.open + 1:rb_.close].split()}
            have = {int(x) for x in self.save[sb.open + 1:sb.close].split()}
            adds = sorted(m.translate(i) for i in self.carry[sp] & listed if i not in m.join)
            adds = [i for i in adds if i not in have]
            if adds:
                ep.add(gs.Edit(sb.close, sb.close, (" ".join(map(str, adds)) + " ").encode(), "transplant", path))
                self.report.registered[path] = len(adds)
        try:
            rn, sn = gs.locate(self.ref, NAME_MAP), gs.locate(self.save, NAME_MAP)
        except gs.GamestateError:
            return
        coa = self.tr.spaces["coat_of_arms"]
        have = {k for k, _ in _PAIR.findall(self.save[sn.open + 1:sn.close])}
        titles = {k.encode() for k in self.title_keys().values()}
        lines = []
        for k, v in _PAIR.findall(self.ref[rn.open + 1:rn.close]):
            c = int(v)
            if c not in self.carry["coat_of_arms"] or c in coa.join:
                continue
            k = self.report.runtime_keys_renamed.get(k.decode(), k.decode()).encode()
            if k in have:
                continue
            lines.append(b"\t\t" + k + b"=" + str(coa.translate(c)).encode() + b"\n")
            self.report.name_map_added["title" if k in titles else "other"] += 1
        if lines:
            at = self.save.rfind(b"\n", 0, sn.close) + 1
            ep.add(gs.Edit(at, at, b"".join(lines), "transplant", NAME_MAP))

    def _collisions(self) -> None:
        """A11.4, measured rather than assumed: per space, copied (not joined) objects whose translated slot index
        is already a slot of the save's own objects. Must be 0."""
        for sp, ids in self.carry.items():
            if sp in ("ai",) or sp in S.IDENTITY or sp not in self.tr.spaces:
                continue
            m = self.tr.spaces[sp]
            own = {i & T.LOW for i in T.space_ids(self.save, sp)}
            hit = sum(1 for i in ids if i not in m.join and (m.translate(i) & T.LOW) in own)
            self.report.collisions[sp] = hit

    def _pairs(self, ep: gs.EditPass) -> None:
        """Relations and opinions between two copied people, appended to the save's lists."""
        copied = self.carry["character"]
        for kind, (a, b) in PAIR_LISTS.items():
            try:
                rblk, sblk = gs.locate(self.ref, kind), gs.locate(self.save, kind)
            except gs.GamestateError:
                continue
            items = []
            for e in gs.iter_entries(self.ref, *rblk.body):
                if e.key is not None:
                    continue
                body = self.ref[e.open:min(e.close, e.open + 600)]
                ma = re.search(rb"\n\t+" + a + rb"=(\d+)", body)
                mb = re.search(rb"\n\t+" + b + rb"=(\d+)", body)
                if ma and mb and int(ma.group(1)) in copied and int(mb.group(1)) in copied:
                    items.append(T.rewrite_entry(self.ref, e, kind, self.tr, self.report.rewrite, self.keep))
            if items:
                ep.add(gs.Edit(sblk.close, sblk.close, b"".join(b" " + x + b"\n" for x in items), "transplant", kind))
                self.report.inserted[kind] += len(items)

    def _events(self, ep: gs.EditPass) -> None:
        """Queued events (``triggered_event``) of copied people whose every reference is in the output."""
        copied = self.carry["character"]
        out = []
        for sec in gs.find_sections(self.ref, "triggered_event"):
            refs = list(T.references(self.ref, sec, "triggered_event"))
            if not any(sp == "character" and v in copied for _, sp, v in refs):
                continue
            if all(self.keep(sp, v, p) for p, sp, v in refs):
                out.append(T.rewrite_entry(self.ref, sec, "triggered_event", self.tr, self.report.rewrite,
                                           self.keep))
            else:
                self.report.not_carried["triggered_event"] += 1
        if out:
            end = len(self.save)
            ep.add(gs.Edit(end, end, b"".join(x + b"\n" for x in out), "transplant", "triggered_event"))
            self.report.inserted["triggered_event"] += len(out)

    def _leases(self, ep: gs.EditPass) -> None:
        """A carried holy order that leases a campaign title: the campaign title gets ``lessee=<the order's
        title>``, the link 1.20 writes on a leased title, unless it is already leased."""
        join = self.tr.spaces["title"].join
        tm = self.tr.spaces["title"]
        wanted: dict[int, int] = {}                                 # save title id -> translated order title id
        for i, (own, leased) in self.holy_order_titles().items():
            if i in self.carry["holy_order"] and own is not None:
                for t in leased:
                    if t in join:
                        wanted.setdefault(join[t], tm.translate(own))
        if not wanted:
            return
        for sid, e in T.entries(self.save, TITLES):
            if sid not in wanted:
                continue
            if re.search(rb"\n\tlessee=", self.save[e.open:min(e.close, e.open + 8192)]):
                continue                                            # the campaign's own lease stands
            at = self.save.rfind(b"\n", 0, e.close) + 1
            ep.add(gs.Edit(at, at, f"\tlessee={wanted[sid]}\n".encode(), "transplant", "lease"))
            order_key = next((k for i, k in self.title_keys().items() if tm.translate(i) == wanted[sid]), "?")
            self.report.leases_added.append(f"{self.save_title_key(sid)} -> {order_key}")

    def _target_name(self, kind: str) -> str:
        if kind in self._ent.get("_targets", {}):
            return self._ent["_targets"][kind][0]
        space = S.KIND_SPACE.get(kind)
        names = [kind] + [s for s in S.SPACES.get(space, ()) if s != kind]
        for name in names:
            try:
                blk = gs.locate(self.save, name)
            except gs.GamestateError:
                continue
            self._ent.setdefault("_targets", {})[kind] = (name, blk)
            return name
        raise T.TranslationError(f"the save has no section for {kind!r}")

    def _target(self, kind: str) -> gs.Block:
        self._target_name(kind)
        return self._ent["_targets"][kind][1]

    def _seams(self, ep: gs.EditPass) -> None:
        """Append each copied title whose de jure liege is an existing title to that parent's list."""
        tm = self.tr.spaces["title"]
        children: dict[int, list[int]] = defaultdict(list)       # save parent id -> translated new children
        for t in sorted(self.carry["title"]):
            e = self.entries(TITLES)[t]
            m = re.search(rb"\n\tde_jure_liege=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)])
            if m and int(m.group(1)) in tm.join:
                children[tm.join[int(m.group(1))]].append(tm.translate(t))
        if not children:
            return
        blocks = {i: e for i, e in T.entries(self.save, TITLES) if i in children}
        for parent, kids in children.items():
            e = blocks.get(parent)
            if e is None:
                continue
            ids = " ".join(str(k) for k in kids).encode()
            lst = next((c for c in gs.iter_children(self.save, *e.body)
                        if c.key == b"de_jure_vassals" and c.block is not None), None)
            if lst is not None:
                ep.add(gs.Edit(lst.block.close, lst.block.close, ids + b" ", "transplant", "seam"))
            else:
                at = self.save.rfind(b"\n", 0, e.close) + 1
                ep.add(gs.Edit(at, at, b"\tde_jure_vassals={ " + ids + b" }\n", "transplant", "seam"))
            self.report.seams += len(kids)
            self.report.seam_parents += 1

    def _counters_and_lookups(self, ep: gs.EditPass) -> None:
        rep = self.report
        coa = self.tr.spaces["coat_of_arms"]
        if self.carry["coat_of_arms"]:
            blk = gs.locate(self.save, "coat_of_arms")
            hits = T._depth0_scalars(self.save, blk, "next_id")
            new = self.tr.coa_next_id([coa.translate(i) for i in self.carry["coat_of_arms"]])
            if hits:
                c = hits[-1]
                ep.add(gs.Edit(c.value_start, c.value_end, str(new).encode(), "transplant", "coat next_id"))
            else:
                at = self.save.rfind(b"\n", 0, blk.close) + 1
                ep.add(gs.Edit(at, at, f"\tnext_id={new}\n".encode(), "transplant", "coat next_id"))
            rep.coa_next_id = (self.tr.save_coa_next_id, new)
        if self.tr.new_traits and self.carry["character"]:
            tl = gs.find_section(self.save, "traits_lookup")
            ep.add(gs.Edit(tl.close, tl.close, (" ".join(self.tr.new_traits) + " ").encode(), "transplant",
                           "traits"))
            rep.traits_appended = len(self.tr.new_traits)
        rl = T.character_lookup(self.ref)
        cm = self.tr.spaces["character"]
        adds = [f"\t{h}={cm.translate(c)}\n" for h, c in sorted(rl.items()) if c in self.carry["character"]]
        if adds:
            cl = gs.find_section(self.save, "character_lookup")
            at = self.save.rfind(b"\n", 0, cl.close) + 1
            ep.add(gs.Edit(at, at, "".join(adds).encode(), "transplant", "character_lookup"))
            rep.character_lookup_added = len(adds)
