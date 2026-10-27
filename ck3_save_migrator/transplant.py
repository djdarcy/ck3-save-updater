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
DYNAMIC_TEMPLATES = "landed_titles/dynamic_templates"           # the registry of runtime (x_) title keys
_TEMPLATE = re.compile(rb'\{\s*key="?([^"\s}]+)"?([^{}]*)\}')   # one entry: { key="x_mc_0" tier=duchy dyn=yes }
REPARENTED = frozenset({"unheld barony", "same holder", "baron only"})   # the 1c cases that are re-parented
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
    reparent_cases: Counter = field(default_factory=Counter)   # step 1c: moved campaign baronies by case
    reparent_left: list = field(default_factory=list)          # the cases not re-parented, named
    contracts_moved: int = 0                                   # baron-only vassals now bound to the 1.20 holder
    provinces_filled: int = 0                                  # ruling B: empty campaign provinces given a holding
    settled: list = field(default_factory=list)                # step 1c-bis: one row per settled barony
    settled_landless_rulers: list = field(default_factory=list)  # displaced copied rulers left with no title
    kept_by_holder: list = field(default_factory=list)         # R15 held titles: successors given to the holder
    kept_relinked: list = field(default_factory=list)          # lieges and contracts re-pointed so realms agree
    kept_skipped: list = field(default_factory=list)           # successors not given (not carried, settled, contested)
    orphans_reparented: list = field(default_factory=list)     # S3: "<title> -> <its 1.20 de jure parent>"
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
                "reparent_cases": dict(self.reparent_cases), "reparent_left": self.reparent_left,
                "contracts_moved": self.contracts_moved, "provinces_filled": self.provinces_filled,
                "settled": self.settled, "settled_landless_rulers": self.settled_landless_rulers,
                "kept_by_holder": self.kept_by_holder, "kept_skipped": self.kept_skipped,
                "kept_relinked": self.kept_relinked,
                "orphans_reparented": self.orphans_reparented,
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


def _landed_list(text: bytes, key: bytes) -> re.Match | None:
    """The ``landed_data/<key>={ ... }`` list of a character entry (never a same-named list elsewhere)."""
    ld = re.search(rb"\n\tlanded_data=\{", text)
    if not ld:
        return None
    return re.compile(rb"\n(\t\t)" + key + rb"=\{([^}]*)\}").search(text, ld.end())


def _edit_landed_list(text: bytes, key: bytes, add=(), drop=frozenset()) -> bytes:
    """A character entry with ids added to and removed from its ``landed_data/<key>`` list, the list made when
    absent (a liege lists his vassals' contracts there: ``landed_data/vassal_contracts``)."""
    m = _landed_list(text, key)
    if m:
        have = m.group(2).split()
        ids = [x for x in have if int(x) not in drop] + [str(a).encode() for a in add if str(a).encode() not in have]
        return text[:m.start()] + b"\n" + m.group(1) + key + b"={ " + b" ".join(ids) + b" }" + text[m.end():]
    ld = re.search(rb"\n\tlanded_data=\{\n", text)
    if not add:
        return text
    if not ld:                  # a character with no landed_data (a landless campaign holder regaining land, R15)
        close = text.rstrip().rfind(b"}")
        if close < 0:
            return text
        return text[:close] + b"\tlanded_data={\n\t\t" + key + b"={ " + b" ".join(str(a).encode() for a in add) + \
            b" }\n\t}\n" + text[close:]
    return text[:ld.end()] + b"\t\t" + key + b"={ " + b" ".join(str(a).encode() for a in add) + b" }\n" + \
        text[ld.end():]


TIER_RANK = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5}


def _primary_first(text: bytes, key_of) -> bytes:
    """A character entry whose ``landed_data/domain`` starts with its highest-tier title.

    The first domain entry is the ruler's primary title. 1.20, making a ruler independent, gives each other title
    the primary as liege when the primary outranks it, else the primary's own liege, and never moves a barony off
    its county; so a count whose primary title is his barony gets his county made its own liege, and the game's
    "which kingdom" routine then loops forever (the 987.11.8 freeze of 2026-10-27, decompiled in the vault). A
    domain whose first title has no tier letter (a runtime ``x_`` title) is left as it is: the campaign's own saves
    carry one, and the game keeps it."""
    m = _landed_list(text, b"domain")
    if not m:
        return text
    ids = m.group(2).split()
    ranks = [TIER_RANK.get(key_of(int(x))[:1], 0) for x in ids]
    if not ids or ranks[0] == 0 or ranks[0] >= max(ranks):
        return text
    top = ranks.index(max(ranks))
    ids = [ids[top]] + ids[:top] + ids[top + 1:]
    return text[:m.start()] + b"\n" + m.group(1) + b"domain={ " + b" ".join(ids) + b" }" + text[m.end():]


def _set_landed_scalar(text: bytes, key: bytes, value: int | None) -> bytes:
    """A character entry with ``landed_data/<key>`` set to ``value``, or the line removed when ``value`` is None."""
    ld = re.search(rb"\n\tlanded_data=\{\n", text)
    if not ld:
        return text
    m = re.compile(rb"\n\t\t" + key + rb"=\d+").search(text, ld.start())
    if m:
        return text[:m.start()] + (b"\n\t\t" + key + b"=" + str(value).encode() if value is not None else b"") + \
            text[m.end():]
    if value is None:
        return text
    return text[:ld.end()] + b"\t\t" + key + b"=" + str(value).encode() + b"\n" + text[ld.end():]


def _set_title_field(text: bytes, key: bytes, value: int | None) -> bytes:
    """A title entry with its depth-1 ``<key>=`` set to ``value`` (inserted after ``key=``), or removed (None)."""
    m = re.search(rb"\n\t" + key + rb"=\d+", text)
    if m:
        return text[:m.start()] + (b"\n\t" + key + b"=" + str(value).encode() if value is not None else b"") + \
            text[m.end():]
    if value is None:
        return text
    k = re.search(rb"\n\tkey=[^\n]*", text)
    at = k.end() if k else text.find(b"\n")
    return text[:at] + b"\n\t" + key + b"=" + str(value).encode() + text[at:]


class Transplant:
    """A plan of reference objects to copy into a save, and the one write that carries it out."""

    def __init__(self, save: bytes, ref: bytes, tr: T.Translator | None = None):
        self.save, self.ref = save, ref
        self.tr = tr or T.Translator.build(save, ref)
        self.carry: dict[str, set[int]] = defaultdict(set)     # space -> reference ids to copy
        self.employer: dict[int, int] = {}       # reference character -> SAVE character whose court they join
        self.expansion_orders = False             # carry holy orders that lease campaign land (R14's flag)
        # step 1c ruling B (R14's plan): campaign provinces with no holding whose 1.20 barony is carried; their
        # entry is replaced by the reference's (holding, buildings, levy, garrison)
        self.fill_provinces: set[int] = set()
        # held titles R15 removed because 1.20 split or redrew their land (R15 records them, R14 hands them over):
        # rows {key, holder, successors, old_liege_key}; their successors go to the holder (holdings_plan)
        self.r15_kept: list[dict] = []
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

    def output_title_key(self, out_id: int) -> str:
        """The key of a title by its id in the output: a campaign title's own key, else the key of the reference
        title that translates to that id (a copied title)."""
        k = self.save_title_key(out_id)
        if k:
            return k
        if "_okeys" not in self._ent:
            m = self.tr.spaces["title"]
            self._ent["_okeys"] = {m.translate(r): key for r, key in self.title_keys().items()}
        return self._ent["_okeys"].get(out_id, "")

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
        frontier += [("province", p) for p in sorted(self.fill_provinces)]     # their regiments come too
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

    # -- step 1c: campaign baronies 1.20 put in another county -------------
    def reparent_plan(self) -> dict[int, tuple[int | None, tuple[str, int] | None, str]]:
        """Campaign baronies whose 1.20 county (the reference's de jure liege) is not their county in the save:
        save barony id -> (save county now, the 1.20 county as ("save", id) or ("ref", id), case). Cases:
        ``unheld barony``, ``same holder`` and ``baron only`` are re-parented (director 2026-10-26 04:45: the
        baron keeps the barony as a vassal of the 1.20 county's holder); ``mixed`` (the holder also holds titles
        outside that county, so two lieges would be needed) and ``county not in output`` are left and named.
        Measured on the engine's re-save: without this, the engine re-seats every such barony under its 1.20
        county and gives it to that county's holder or to no one (145 baronies on the old output)."""
        if "_reparent" in self._ent:
            return self._ent["_reparent"]
        tm = self.tr.spaces["title"]
        to_save = tm.join                                            # reference title id -> save title id
        from_save = {s: r for r, s in to_save.items()}
        head = {}
        for i, e in T.entries(self.save, TITLES):
            b = self.save[e.open:min(e.close, e.open + 4096)]
            k = re.search(rb"\n\tkey=\"?([\w\-']+)", b)
            h = re.search(rb"\n\tholder=(\d+)", b)
            dj = re.search(rb"\n\tde_jure_liege=(\d+)", b)
            head[i] = (k.group(1).decode() if k else "", int(h.group(1)) if h else None,
                       int(dj.group(1)) if dj else None)
        ref_dj = {}
        for r, e in self.entries(TITLES).items():
            m = re.search(rb"\n\tde_jure_liege=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)])
            if m:
                ref_dj[r] = int(m.group(1))

        def county_1_20(s: int) -> tuple[str, int] | None:
            """The 1.20 county of a save barony, in output terms; None when 1.20 does not know the barony."""
            r = from_save.get(s)
            c = ref_dj.get(r) if r is not None else None
            if c is None:
                return None
            return ("save", to_save[c]) if c in to_save else ("ref", c)

        moved = {}
        for s, (k, h, dj) in head.items():
            if not k.startswith("b_"):
                continue
            want = county_1_20(s)
            if want is None or want == ("save", dj):
                continue
            moved[s] = want
        held: dict[int, list[int]] = defaultdict(list)
        for s, (_, h, _) in head.items():
            if h is not None:
                held[h].append(s)
        out = {}
        for s, want in moved.items():
            _, h, dj = head[s]
            if want[0] == "ref" and want[1] not in self.carry["title"]:
                case = "county not in output"
            elif h is None:
                case = "unheld barony"
            elif self.county_holder(want, head) == h:
                case = "same holder"
            elif all(head[t][0].startswith("b_") and (moved.get(t) or ("save", head[t][2])) == want
                     for t in held[h]):
                case = "baron only"
            else:
                case = "mixed"
            # ruling A (director 2026-10-26 13:3x): the game gives a county's capital barony to the county's holder
            # (re-save of e2e_1c4: 11 of 18 such baronies lost, 18 of 18 non-capitals kept), so a lone baron cannot
            # keep a capital; named, like the mixed cases
            if case == "baron only":
                r = from_save.get(s)
                re_ = self.entries(TITLES).get(r) if r is not None else None
                if re_ is not None and re.search(rb"\n\tcapital_barony=yes", self.ref[re_.open:min(re_.close,
                                                                                                    re_.open + 2048)]):
                    case = "capital"
            out[s] = (dj, want, case)
        self._ent["_reparent"] = out
        self._ent["_reparent_head"] = head
        return out

    def county_holder(self, want: tuple[str, int], head: dict | None = None) -> int | None:
        """The output holder of a 1.20 county given as ("save", id) or ("ref", id), as an output character id."""
        head = head if head is not None else self._ent.get("_reparent_head", {})
        if want[0] == "save":
            return head.get(want[1], (None, None, None))[1]
        e = self.entries(TITLES).get(want[1])
        m = re.search(rb"\n\tholder=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)]) if e else None
        if not m or not self.keep("character", int(m.group(1)), "holder"):
            return None
        return self.tr.spaces["character"].translate(int(m.group(1)))

    def contract_moves(self) -> list[tuple[int, int, int, int]]:
        """Step 1c, baron-only cases: (contract id, contract's save entry start, old liege, new liege) for each
        baron whose contract moves to the 1.20 county's holder (output ids). Measured on the engine's re-save of
        e2e_1c3: moving the contract's ``liege=`` alone is not enough; a liege lists his vassals' contracts in
        ``landed_data/vassal_contracts``, and a contract the new liege does not list is deleted on load."""
        if "_moves" in self._ent:
            return self._ent["_moves"]
        plan = self.reparent_plan()
        head = self._ent["_reparent_head"]
        settled = self.settled_baronies()
        settle = self.settle_plan()
        new_liege = {}
        for b, (_, want, case) in plan.items():
            if b in settled:                        # 1c-bis: the county came to the campaign
                c, fate = settled[b]
                d = settle[c]
                if fate == "vassal":
                    new_liege[head[b][1]] = d["new"]
                elif fate == "count" and d["branch"].startswith("family"):
                    lt = d["liege_title"]
                    lh = head.get(lt, ("", None, None))[1] if lt is not None else None
                    if lh is not None and lh != head[b][1]:
                        new_liege[head[b][1]] = lh
                continue                            # "landless": the contract is removed, not moved
            if case == "baron only":
                x = self.county_holder(want, head)
                if x is not None and x != head[b][1]:
                    new_liege[head[b][1]] = x
        out = []
        for path in ("vassal_contracts/database", "vassal_contracts/active"):
            try:
                ents = T.entries(self.save, path)
            except T.TranslationError:
                continue
            for i, e in ents:
                body = self.save[e.open:e.close]
                v = re.search(rb"\n\t+vassal=(\d+)", body)
                lg = re.search(rb"\n\t+liege=(\d+)", body)
                if v and lg and int(v.group(1)) in new_liege and int(lg.group(1)) != new_liege[int(v.group(1))]:
                    out.append((i, e.open, int(lg.group(1)), new_liege[int(v.group(1))]))
        self._ent["_moves"] = out
        return out

    # -- step 1c-bis: a moved campaign barony under a copied county ---------
    def _save_chars(self) -> dict[int, gs.Block]:
        if "_save_chars" not in self._ent:
            out = {}
            for sec in CHARACTER_KINDS:
                try:
                    blk = gs.locate(self.save, sec)
                except gs.GamestateError:
                    continue
                for e in gs.iter_entries(self.save, blk.open + 1, blk.close):
                    if e.key is not None and e.key.isdigit():
                        out.setdefault(int(e.key), e)
            self._ent["_save_chars"] = out
        return self._ent["_save_chars"]

    def _family(self) -> callable:
        """The family test (djdarcy 2026-10-26): a character whose house or dynasty is the player's, or whose
        spouse's (current or former) is. ``family_test.py`` also follows descent from the dynasty's founder; the
        save names no founder generically, so that branch is not tested here (both family barons on the founding
        save match by their own house)."""
        chars = self._save_chars()
        hd = {}
        for i, e in T.entries(self.save, "dynasties/dynasty_house"):
            m = re.search(rb"\n\t*dynasty=(\d+)", self.save[e.start:min(e.end, e.start + 2000)])
            hd[i] = int(m.group(1)) if m else None

        def body(c):
            e = chars.get(c)
            return self.save[e.start:e.end] if e is not None else b""

        def kin(c):
            m = re.search(rb"\n\tdynasty_house=(\d+)", body(c))
            h = int(m.group(1)) if m else None
            return h, hd.get(h)

        pm = re.search(rb"currently_played_characters=\{\s*(\d+)", self.save)
        player = int(pm.group(1)) if pm else None
        ph, pd = kin(player) if player is not None else (None, None)

        def spouses(c):
            out = []
            for f in (b"spouse", b"primary_spouse", b"former_spouses"):
                for m in re.finditer(rb"\n\t+" + f + rb"=(?:\{([^}]*)\}|(\d+))", body(c)):
                    out += [int(x) for x in (m.group(1) or m.group(2)).split() if x.isdigit()]
            return out

        def family(c):
            if player is None or (ph is None and pd is None):
                return ""
            for who in [c] + spouses(c):
                h, d = kin(who)
                if (h is not None and h == ph) or (d is not None and d == pd):
                    return "own house or dynasty" if who == c else "spouse's house or dynasty"
            return ""
        return family

    def settle_plan(self) -> dict[int, dict]:
        """Step 1c-bis (transplant DWP 16:45 addendum; director rulings 2026-10-26 17:3x). For each COPIED county
        a moved campaign barony belongs to in 1.20: the county goes to the campaign. A baron of the player's
        family is promoted to its count; otherwise the holder of the barony's old county takes it and the baron
        stays his vassal (a baron who IS the old count simply gains the county). A capital barony goes with the
        county: a carried capital held by the displaced ruler, or a campaign capital whose baron is not the new
        count (that baron becomes landless at the new count's court: no built barony is free in these counties).
        The displaced copied ruler loses the county; landless if he holds nothing else, at the new holder's
        court. Copied barons in the county stay barons, vassals of the new holder.
        ref county id -> {"new", "branch", "liege_title", "x", "baronies": {save barony: fate}, "capital",
        "carried_vassals"}."""
        if "_settle" in self._ent:
            return self._ent["_settle"]
        plan = self.reparent_plan()
        head = self._ent["_reparent_head"]
        tm, cm = self.tr.spaces["title"], self.tr.spaces["character"]
        family = self._family()
        sdf = {}
        for i, e in T.entries(self.save, TITLES):
            m = re.search(rb"\n\tde_facto_liege=(\d+)", self.save[e.open:min(e.close, e.open + 4096)])
            if m:
                sdf[i] = int(m.group(1))
        chars = self._save_chars()

        def primary(c):
            e = chars.get(c)
            m = re.search(rb"\n\t\tdomain=\{\s*(\d+)", self.save[e.start:e.end]) if e is not None else None
            return int(m.group(1)) if m else None

        ref_field = {}
        for r, e in self.entries(TITLES).items():
            b = self.ref[e.open:min(e.close, e.open + 4096)]
            ref_field[r] = (int(m.group(1)) if (m := re.search(rb"\n\tde_jure_liege=(\d+)", b)) else None,
                            int(m.group(1)) if (m := re.search(rb"\n\tholder=(\d+)", b)) else None,
                            b"\n\tcapital_barony=yes" in b)
        by_county: dict[int, list[int]] = defaultdict(list)
        for s, (old, want, case) in plan.items():
            if want[0] != "ref" or want[1] not in self.carry["title"] or case not in ("baron only", "capital",
                                                                                      "mixed"):
                continue
            if self.county_holder(want, head) is None:
                continue
            by_county[want[1]].append(s)
        out = {}
        for c, baronies in sorted(by_county.items()):
            x = ref_field[c][1]
            barons = {s: head[s][1] for s in baronies}
            olds = {plan[s][0] for s in baronies}
            old_counts = {head[o][1] for o in olds if o is not None}
            fam = [h for s, h in sorted(barons.items()) if family(h)]
            capital_save = next((s for s in baronies if ref_field.get(self._ref_of(s), (0, 0, False))[2]), None)
            if fam:
                # the family baron holding the capital first, else the first by barony
                new = barons[capital_save] if capital_save is not None and barons[capital_save] in fam else fam[0]
                branch = f"family baron promoted ({family(new)})"
                h = next(iter(old_counts)) if len(old_counts) == 1 else None
                p = primary(h) if h is not None else None
                liege = p if p is not None and head.get(p, ("",))[0][:1] in ("d", "k", "e") else \
                    sdf.get(next(iter(olds)) if len(olds) == 1 else None)
            elif len(old_counts) == 1:
                new = next(iter(old_counts))
                branch = "the old count takes it" + (" (a moved barony of his own came too)"
                                                     if new in barons.values() else "")
                liege = sdf.get(next(iter(olds)))
            else:
                continue                                # no single old count: left as 1c names it
            fates = {}
            for s, h in barons.items():
                if h == new:
                    fates[s] = "count"
                elif s == capital_save:
                    fates[s] = "landless"
                else:
                    fates[s] = "vassal"
            cap_ref = next((r for r, (dj, hh, cap) in ref_field.items() if dj == c and cap), None)
            carried_cap = cap_ref if cap_ref is not None and cap_ref not in tm.join and \
                ref_field[cap_ref][1] == x else None
            # copied barons of the county other than the displaced ruler: their contracts go to the new holder
            vassals = {ref_field[r][1] for r, (dj, hh, cap) in ref_field.items()
                       if dj == c and hh is not None and hh != x and r not in tm.join}
            contracts = []
            for i in self.carry["vassal_contract"]:
                b = self.ref[self.entries(CARRIED["vassal_contract"])[i].start:
                             self.entries(CARRIED["vassal_contract"])[i].end]
                v = re.search(rb"\n\t+vassal=(\d+)", b)
                lg = re.search(rb"\n\t+liege=(\d+)", b)
                if v and lg and int(v.group(1)) in vassals and int(lg.group(1)) == x:
                    contracts.append(i)
            # the displaced ruler's own other baronies in the county stay his (director 2026-10-26 18:0x: the game
            # leaves them with him on load; "we keep the new players"); named
            x_kept = sorted(r for r, (dj, hh, cap) in ref_field.items()
                            if dj == c and hh == x and r != carried_cap and r not in tm.join)
            out[c] = {"new": new, "branch": branch, "liege_title": liege, "x": x, "baronies": fates,
                      "capital": carried_cap, "carried_contracts": sorted(contracts), "x_kept": x_kept,
                      "old_county": next(iter(olds)) if len(olds) == 1 else None}
        self._ent["_settle"] = out
        return out

    def holdings_plan(self) -> dict:
        """djdarcy 2026-10-27 (~06:30): "any titles that were in play that are still existent in the game that were
        present in our original game should be upgraded if possible so the correct holder still has their title."
        For each held title R15 removed because 1.20 split or redrew its land (``self.r15_kept``), its successors
        -- carried from the reference -- go to the campaign holder instead of the reference's holder, with the
        county's capital barony when the displaced ruler held it. Lieges follow the game's convention (see
        ``_primary_first``): the holder's primary is his highest title; a title below it takes the primary as de
        facto liege, a title at or above it takes the primary's own liege; a barony keeps its county. The displaced
        ruler's vassal contracts for land under a regained title move to the holder; a displaced ruler left with
        nothing joins the holder's court. The holder's own titles whose liege R15 stripped point at his primary.
        Returns {"titles": {ref id: (holder, liege out id | None, set_liege)}, "x_drop": {ref char: {out ids}},
        "x_new": {ref char: holder}, "contracts": {ref contract: (holder, ref char)}, "holders": {holder:
        {"dom_add": [out ids], "liege_fix": {save title: out liege | None}}}}."""
        if "_holdings" in self._ent:
            return self._ent["_holdings"]
        out = {"titles": {}, "x_drop": defaultdict(set), "x_new": {}, "contracts": {}, "holders": {},
               "repoint": {}, "contract_moves": {}, "relinked": []}
        self._ent["_holdings"] = out
        if not self.r15_kept:
            return out
        tm = self.tr.spaces["title"]
        keys = self.title_keys()
        by_key = {k: i for i, k in keys.items()}
        settled = set(self.settle_plan())
        ref = {}                                   # ref title -> (de jure, holder, capital barony?, de facto)
        for r, e in self.entries(TITLES).items():
            b = self.ref[e.open:min(e.close, e.open + 4096)]
            ref[r] = (int(m.group(1)) if (m := re.search(rb"\n\tde_jure_liege=(\d+)", b)) else None,
                      int(m.group(1)) if (m := re.search(rb"\n\tholder=(\d+)", b)) else None,
                      b"\n\tcapital_barony=yes" in b,
                      int(m.group(1)) if (m := re.search(rb"\n\tde_facto_liege=(\d+)", b)) else None)
        claims, src = defaultdict(set), {}
        for row in self.r15_kept:
            for s in row["successors"]:
                r = by_key.get(s)
                why = ("not in the reference" if r is None else "not carried" if r not in self.carry["title"]
                       else "settled by the redrawn-county rule" if r in settled else None)
                if why:
                    self.report.kept_skipped.append({"title": s, "from": row["key"], "why": why})
                    continue
                claims[r].add(row["holder"])
                src.setdefault(r, row)
        regained: dict[int, int] = {}
        for r, hs in claims.items():
            if len(hs) > 1:
                self.report.kept_skipped.append({"title": keys[r], "from": src[r]["key"],
                                                 "why": f"claimed by {len(hs)} campaign holders"})
                continue
            regained[r] = next(iter(hs))
        for r, h in list(regained.items()):         # a count holds his county's capital barony
            if keys[r].startswith("c_"):
                cap = next((c for c, f in ref.items() if f[0] == r and f[2]), None)
                if cap is not None and cap not in regained and cap in self.carry["title"] and cap not in settled \
                        and ref[cap][1] == ref[r][1]:
                    regained[cap], src[cap] = h, src[r]
        chars = self._save_chars()
        sdf: dict[int, int | None] = {}
        sdh: dict[int, int | None] = {}                          # save title -> its holder
        for i, e in T.entries(self.save, TITLES):
            b = self.save[e.open:min(e.close, e.open + 4096)]
            m = re.search(rb"\n\tde_facto_liege=(\d+)", b)
            sdf[i] = int(m.group(1)) if m else None
            m = re.search(rb"\n\tholder=(\d+)", b)
            sdh[i] = int(m.group(1)) if m else None
        save_id_of = {self.save_title_key(i): i for i in sdf}
        svc: dict[int, tuple[int, int, str]] = {}                # vassal (save char) -> (contract, liege, section)
        for path in ("vassal_contracts/active", "vassal_contracts/database"):
            try:
                for i, e in T.entries(self.save, path):
                    b = self.save[e.open:e.close]
                    v, lg = re.search(rb"\n\t+vassal=(\d+)", b), re.search(rb"\n\t+liege=(\d+)", b)
                    if v and lg:
                        svc.setdefault(int(v.group(1)), (i, int(lg.group(1)), path))
            except T.TranslationError:
                continue
        settle = self.settle_plan()
        rank = lambda k: TIER_RANK.get(k[:1], 0)                 # noqa: E731
        by_holder: dict[int, list[int]] = defaultdict(list)
        for r, h in regained.items():
            by_holder[h].append(r)
        info: dict[int, dict] = {}                               # holder -> his realm after the hand-back
        for h, rs in sorted(by_holder.items()):
            e = chars.get(h)
            dom = re.search(rb"\n\t\tdomain=\{([^}]*)\}", self.save[e.start:e.end]) if e is not None else None
            existing = [int(x) for x in dom.group(1).split()] if dom else []
            order = {r: (src[r]["successors"].index(keys[r]) if keys[r] in src[r]["successors"] else 99) for r in rs}
            rs = sorted(rs, key=lambda r: (-rank(keys[r]), order[r], r))
            items = [("save", s, self.save_title_key(s)) for s in existing] + [("ref", r, keys[r]) for r in rs]
            top = max(rank(k) for _, _, k in items)
            prim = next(it for it in items if rank(it[2]) == top)
            info[h] = {"rs": rs, "existing": existing, "top": top, "prim": prim, "prim_key": prim[2],
                       "prim_out": prim[1] if prim[0] == "save" else tm.translate(prim[1])}

        def primary_of(c: int) -> tuple[int | None, str]:
            """A campaign character's primary title after the hand-back: (output id, key)."""
            if c in info:
                return info[c]["prim_out"], info[c]["prim_key"]
            ce = chars.get(c)
            d = re.search(rb"\n\t\tdomain=\{([^}]*)\}", self.save[ce.start:ce.end]) if ce is not None else None
            first = int(d.group(1).split()[0]) if d and d.group(1).split() else None
            return (first, self.save_title_key(first)) if first is not None else (None, "")

        def final_holder(r: int) -> int | None:
            """Who holds a reference title after the plans, when that is a campaign character (else None)."""
            if r in regained:
                return regained[r]
            if r in settle:
                return settle[r]["new"]
            j = tm.join.get(r)
            return sdh.get(j) if j is not None else None

        for h, d in info.items():
            rs, existing, top, prim, prim_out = d["rs"], d["existing"], d["top"], d["prim"], d["prim_out"]
            rows = sorted({row["key"]: row for row in (src[r] for r in rs)}.values(), key=lambda row: -rank(row["key"]))
            fallback = next((save_id_of[row["old_liege_key"]] for row in rows
                             if row["old_liege_key"] in save_id_of), None)
            if prim[0] == "save":
                plg = sdf.get(prim[1]) if sdf.get(prim[1]) is not None else fallback
            else:
                old = existing[0] if existing else None
                plg = sdf[old] if old is not None and sdf.get(old) is not None else fallback
            # the realm must agree with the contract (play5 2026-10-27: a count handed his county back with no liege
            # while his contract still bound him, and a baron under a county now held by another, crashed 989.1.1):
            # a ruler bound by a contract takes a title of that liege as his primary's liege; a baron's contract
            # follows his county's holder, since a barony's liege is always its county
            ct = svc.get(h)
            if ct is not None and top > TIER_RANK["b"] and (plg is None or sdh.get(plg) != ct[1]):
                lp, lk = primary_of(ct[1])
                if lp is not None and rank(lk) > top:
                    out["relinked"].append({"holder": h, "title": prim[2], "liege": lk, "why": "his contract's liege"})
                    plg = lp
                else:
                    self.report.kept_skipped.append({"title": prim[2], "from": src[rs[0]]["key"],
                                                     "why": f"contract liege {ct[1]} holds nothing above it"})
            if ct is not None and top == TIER_RANK["b"] and prim[0] == "ref" and ref[prim[1]][0] is not None:
                ch = final_holder(ref[prim[1]][0])
                if ch is not None and ch not in (ct[1], h):
                    out["contract_moves"][ct[0]] = (ct[1], ch, ct[2])
                    out["relinked"].append({"holder": h, "title": prim[2], "liege": keys.get(ref[prim[1]][0]),
                                            "why": f"contract moved from {ct[1]} to the county's holder {ch}"})
                elif ch is None:
                    self.report.kept_skipped.append({"title": prim[2], "from": src[rs[0]]["key"],
                                                     "why": "its county's holder is not a campaign character"})
            liege_for = lambda k: prim_out if rank(k) < top else plg      # noqa: E731
            for r in rs:
                if keys[r].startswith("b_"):
                    out["titles"][r] = (h, None, False)
                else:
                    out["titles"][r] = (h, plg if (prim[0] == "ref" and r == prim[1]) else liege_for(keys[r]), True)
                x = ref[r][1]
                if x is not None and x in self.carry["character"]:
                    out["x_drop"][x].add(tm.translate(r))
                    out["x_new"].setdefault(x, h)
                self.report.kept_by_holder.append({
                    "title": keys[r], "from": src[r]["key"], "holder": h,
                    "displaced": self.tr.spaces["character"].translate(x) if x is not None else None,
                    "liege": None if out["titles"][r][1] is None else self.output_title_key(out["titles"][r][1])})
            fix = {}
            for s in existing:
                k = self.save_title_key(s)
                if k.startswith("b_"):
                    continue
                if prim[0] == "save" and s == prim[1]:
                    if sdf.get(s) is None and plg is not None:
                        fix[s] = plg                    # his primary lost its liege to R15
                    continue
                want = liege_for(k)
                if want is not None and (sdf.get(s) is None or (prim[0] == "ref" and s == (existing[0] if existing
                                                                                         else None))):
                    fix[s] = want                       # stripped by R15, or his old primary under the new one
            out["holders"][h] = {"dom_add": [tm.translate(r) for r in rs], "liege_fix": fix}
        # the displaced ruler's vassals under a regained title: their contracts move to the holder
        regained_from: dict[int, dict[int, int]] = defaultdict(dict)      # ref char -> {ref title: holder}
        for r, h in regained.items():
            if ref[r][1] is not None:
                regained_from[ref[r][1]][r] = h
        titles_of: dict[int, list[int]] = defaultdict(list)
        for t, f in ref.items():
            if f[1] is not None:
                titles_of[f[1]].append(t)
        vc = self.entries(CARRIED["vassal_contract"]) if self.carry["vassal_contract"] else {}
        for i in sorted(self.carry["vassal_contract"]):
            b = self.ref[vc[i].start:vc[i].end]
            v, lg = re.search(rb"\n\t+vassal=(\d+)", b), re.search(rb"\n\t+liege=(\d+)", b)
            if not (v and lg) or int(lg.group(1)) not in regained_from:
                continue
            got = regained_from[int(lg.group(1))]
            h = next((got[ref[t][3]] for t in titles_of.get(int(v.group(1)), []) if ref[t][3] in got), None)
            if h is not None:
                out["contracts"][i] = (h, int(lg.group(1)))
        # the displaced ruler keeps the titles he still has, but one whose de facto liege was a title of his now
        # handed back would make him a vassal of its new holder with no contract (play5: c_tiande under d_langshan):
        # it takes the liege above, past every handed-back title, so his own contract still describes him
        for x in sorted(out["x_drop"]):
            for t in titles_of.get(x, []):
                lg = ref[t][3]
                if t in regained or t in settle or lg not in regained or t not in self.carry["title"] \
                        or keys.get(t, "").startswith("b_"):
                    continue
                while lg is not None and lg in regained:
                    lg = ref[lg][3]
                if lg is not None and not (lg in self.carry["title"] or lg in tm.join):
                    lg = None
                out["repoint"][t] = tm.translate(lg) if lg is not None else None
                out["relinked"].append({"holder": self.tr.spaces["character"].translate(x), "title": keys.get(t),
                                        "liege": keys.get(lg) if lg is not None else None,
                                        "why": "its liege title was handed back"})
        self.report.kept_relinked = out["relinked"]
        return out

    def _ref_of(self, save_title: int) -> int | None:
        if "_from_save" not in self._ent:
            self._ent["_from_save"] = {s: r for r, s in self.tr.spaces["title"].join.items()}
        return self._ent["_from_save"].get(save_title)

    def orphan_plan(self) -> dict[tuple[str, int], int]:
        """S3 (director 2026-10-26 00:45): a title with no de jure parent in the output whose 1.20 counterpart has
        one gets it, from the reference's own tree (the map's data, a carry). ("save", id) or ("ref", id) -> the
        reference id of the parent; only parents present in the output (campaign or copied) are used."""
        if "_orphans" in self._ent:
            return self._ent["_orphans"]
        tm = self.tr.spaces["title"]
        ref_dj = {}
        for r, e in self.entries(TITLES).items():
            m = re.search(rb"\n\tde_jure_liege=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)])
            if m:
                ref_dj[r] = int(m.group(1))
        present = lambda p: p in tm.join or p in self.carry["title"]  # noqa: E731
        out = {}
        for s, e in T.entries(self.save, TITLES):
            r = self._ref_of(s)
            if r is None or r not in ref_dj or not present(ref_dj[r]):
                continue
            if self.reparent_plan().get(s) is not None:
                continue                                # a moved barony: 1c's
            if not re.search(rb"\n\tde_jure_liege=\d+", self.save[e.open:min(e.close, e.open + 4096)]):
                out[("save", s)] = ref_dj[r]
        # measured 2026-10-26 on e2e_1c8: all 22 orphans are campaign titles whose 1.8.1 parent R15 removed (two of
        # them renamed by R15, d_orkhon and k_bale); a copied title keeps the reference's parent through rewrite
        self._ent["_orphans"] = out
        return out

    def reparented(self, s: int) -> bool:
        """Is campaign barony ``s`` moved to its 1.20 county: a 1c case, or one step 1c-bis settles."""
        case = self.reparent_plan().get(s, (None, None, ""))[2]
        return case in REPARENTED or s in self.settled_baronies()

    def settled_baronies(self) -> dict[int, tuple[int, str]]:
        """save barony id -> (ref county id, fate) for every barony step 1c-bis settles."""
        return {s: (c, fate) for c, d in self.settle_plan().items() for s, fate in d["baronies"].items()}

    def _out_title(self, want: tuple[str, int]) -> int:
        return want[1] if want[0] == "save" else self.tr.spaces["title"].translate(want[1])

    # -- the edge policy ----------------------------------------------------
    def keep(self, space: str, v: int, path: str = "") -> bool:
        m = self.tr.spaces[space]
        if space in S.IDENTITY:
            return True
        if v in m.join:
            if space == "title" and path.startswith("de_jure_vassals") and self.reparented(m.join[v]):
                return True             # a campaign barony 1.20 put in this new county comes with it (step 1c)
            if space == "title" and path.startswith("de_jure_vassals") and ("save", m.join[v]) in self.orphan_plan():
                return True             # a campaign title whose old parent died joins its 1.20 parent (S3)
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

        cm = self.tr.spaces["character"]
        tmap, kmap = self.tr.spaces["title"], self.tr.spaces["vassal_contract"]
        gains: dict[int, list[int]] = defaultdict(list)          # copied liege (output id) -> contracts it gains
        for cid, _, _, x in self.contract_moves():
            gains[x].append(cid)
        # step 1c-bis, the copied side: the displaced ruler loses the county (and its carried capital) and those
        # barons' contracts; with nothing left he goes to the new holder's court (R16's employer path)
        settle = self.settle_plan()
        x_drop: dict[int, set[int]] = defaultdict(set)           # copied ruler (ref) -> titles (output ids) lost
        x_vc: dict[int, set[int]] = defaultdict(set)             # copied ruler (ref) -> contracts (output ids) lost
        x_new: dict[int, int] = {}
        title_set: dict[int, tuple[int, int | None, bool]] = {}  # ref title -> (new holder, de facto liege, county?)
        contract_liege: dict[int, int] = {}                      # ref contract -> new liege (save id)
        for c, d in settle.items():
            x = d["x"]
            x_drop[x].add(tmap.translate(c))
            title_set[c] = (d["new"], d["liege_title"], True)
            if d["capital"] is not None:
                x_drop[x].add(tmap.translate(d["capital"]))
                title_set[d["capital"]] = (d["new"], None, False)
            x_vc[x] |= {kmap.translate(i) for i in d["carried_contracts"]}
            for i in d["carried_contracts"]:
                contract_liege[i] = d["new"]
            x_new.setdefault(x, d["new"])
        # R15's held titles (djdarcy 2026-10-27): the successors go to the campaign holder, through the same path
        hp = self.holdings_plan()
        for r, (holder, liege, set_liege) in hp["titles"].items():
            title_set[r] = (holder, liege, set_liege)
        for x, lost in hp["x_drop"].items():
            x_drop[x] |= lost
            x_new.setdefault(x, hp["x_new"][x])
        for i, (holder, x) in hp["contracts"].items():
            contract_liege[i] = holder
            x_vc[x].add(kmap.translate(i))
        for x, lost in x_drop.items():
            ch = self.character(x)
            m = re.search(rb"\n\t\tdomain=\{([^}]*)\}", self.ref[ch[1].start:ch[1].end]) if ch else None
            held = {tmap.translate(int(t)) for t in (m.group(1).split() if m else [])}
            if held <= lost and x not in self.employer:
                self.employer[x] = x_new[x]
                self.report.settled_landless_rulers.append(cm.translate(x))
        for p in sorted(self.carry["character"]):
            kind, e = self.character(p)
            text = rewrite(kind, e)
            if p in self.employer:
                text = _set_employer(text, self.employer[p])
            if cm.translate(p) in gains:            # step 1c: a campaign baron's contract, now this ruler's
                text = _edit_landed_list(text, b"vassal_contracts", add=gains.pop(cm.translate(p)))
            if p in x_drop:
                text = _edit_landed_list(text, b"domain", drop=x_drop[p])
                text = _edit_landed_list(text, b"vassal_contracts", drop=x_vc[p])
                rc = re.search(rb"\n\t\trealm_capital=(\d+)", text)
                if rc and int(rc.group(1)) in x_drop[p]:
                    left = re.search(rb"\n\t\tdomain=\{([^}]*)\}", text)
                    ids = left.group(1).split() if left else []
                    text = _set_landed_scalar(text, b"realm_capital", int(ids[0]) if ids else None)
            payload[kind].append(text)
        self._ent["_gains_left"] = gains            # lieges that are campaign people: edited in place (_reparent)
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
            if t in title_set:                      # 1c-bis and R15's held titles: the title comes to the campaign
                holder, liege, set_liege = title_set[t]
                text = _set_title_field(text, b"holder", holder)
                if set_liege:                       # never on a barony: its de facto liege is its county
                    text = _set_title_field(text, b"de_facto_liege", liege)
            elif t in hp["repoint"]:                # a displaced ruler's title whose liege was handed back
                text = _set_title_field(text, b"de_facto_liege", hp["repoint"][t])
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
        if self.fill_provinces:                     # ruling B: the campaign's empty entry becomes the reference's
            for pv, e in T.entries(self.save, "provinces"):
                if pv in self.fill_provinces:
                    ep.add(gs.Edit(e.start, e.end, rewrite("provinces", self.entries("provinces")[pv]),
                                   "transplant", "1c province holding"))
                    rep.provinces_filled += 1
        for sp, kind in CARRIED.items():
            for i in sorted(self.carry[sp]):
                text = rewrite(kind, self.entries(kind)[i])
                if sp == "vassal_contract" and i in contract_liege:     # 1c-bis: a copied baron's new liege
                    text = re.sub(rb"(\n\t+liege=)\d+", lambda m: m.group(1) + str(contract_liege[i]).encode(),
                                  text, count=1)
                payload[kind].append(text)
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
        self._reparent(ep)
        self._leases(ep)
        self._pairs(ep)
        self._events(ep)
        self._counters_and_lookups(ep)
        self._registries(ep)
        self._register_runtime_titles(ep)
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

    def _register_runtime_titles(self, ep: gs.EditPass) -> None:
        """Every carried runtime (x_) title is registered in landed_titles/dynamic_templates, with the reference's own
        entry for it (tier and the rest) under the key the title has in the output. 1.20 rejects an unregistered x_
        key at load ("... is not a valid title template") and destroys the title in play; a mercenary company left
        pointing at it then crashes the yearly company pass (2026-10-27: 167 carried company titles, 134 destroyed
        within a year). A key the save already registers is left alone."""
        try:
            rdt, sdt = gs.locate(self.ref, DYNAMIC_TEMPLATES), gs.locate(self.save, DYNAMIC_TEMPLATES)
        except gs.GamestateError:
            return
        ref_entry = {m.group(1): m.group(2).strip() for m in _TEMPLATE.finditer(self.ref, rdt.open, rdt.close)}
        have = {m.group(1) for m in _TEMPLATE.finditer(self.save, sdt.open, sdt.close)}
        keys = self.title_keys()
        adds = []
        for i in sorted(self.carry["title"] - set(self.tr.spaces["title"].join)):
            rkey = keys.get(i, "")
            if not rkey.startswith("x_"):
                continue
            okey = self.report.runtime_keys_renamed.get(rkey, rkey).encode()
            rest = ref_entry.get(rkey.encode())
            if okey in have or rest is None:
                continue
            adds.append(b'{ key="' + okey + b'" ' + rest + b" } ")
            have.add(okey)
        if adds:
            ep.add(gs.Edit(sdt.close, sdt.close, b" ".join(adds), "transplant", DYNAMIC_TEMPLATES))
            self.report.registered[DYNAMIC_TEMPLATES] = len(adds)

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
        """Append each copied title whose de jure liege is an existing title to that parent's list; and (step 1c)
        move each re-parented campaign barony from its old county's list to its 1.20 county's, when that county
        is a campaign title (a copied county lists it already: ``keep``). One rewrite per parent list."""
        tm = self.tr.spaces["title"]
        children: dict[int, list[int]] = defaultdict(list)       # save parent id -> ids appended
        removed: dict[int, set[int]] = defaultdict(set)          # save parent id -> ids taken out
        for t in sorted(self.carry["title"]):
            e = self.entries(TITLES)[t]
            m = re.search(rb"\n\tde_jure_liege=(\d+)", self.ref[e.open:min(e.close, e.open + 4096)])
            if m and int(m.group(1)) in tm.join:
                children[tm.join[int(m.group(1))]].append(tm.translate(t))
                self.report.seams += 1
        for (side, s), p in sorted(self.orphan_plan().items()):
            if side == "save" and p in tm.join:         # S3: a campaign parent lists its re-parented orphan
                children[tm.join[p]].append(s)
        for b, (old, want, case) in sorted(self.reparent_plan().items()):
            if not self.reparented(b):
                continue
            if old is not None:
                removed[old].add(b)
            if want[0] == "save":
                children[want[1]].append(b)
        parents = set(children) | set(removed)
        if not parents:
            return
        blocks = {i: e for i, e in T.entries(self.save, TITLES) if i in parents}
        for parent in sorted(parents):
            e = blocks.get(parent)
            if e is None:
                continue
            kids, gone = children.get(parent, []), removed.get(parent, set())
            lst = next((c for c in gs.iter_children(self.save, *e.body)
                        if c.key == b"de_jure_vassals" and c.block is not None), None)
            if lst is not None:
                have = [int(x) for x in self.save[lst.block.open + 1:lst.block.close].split() if x.isdigit()]
                ids = [x for x in have if x not in gone] + [k for k in kids if k not in have]
                if not gone:            # only appends: insert at the close, the campaign's text untouched
                    add = " ".join(str(k) for k in kids if k not in have).encode()
                    if add:
                        ep.add(gs.Edit(lst.block.close, lst.block.close, add + b" ", "transplant", "seam"))
                else:
                    ep.add(gs.Edit(lst.block.open + 1, lst.block.close,
                                   (" " + " ".join(map(str, ids)) + " ").encode(), "transplant", "seam"))
            elif kids:
                at = self.save.rfind(b"\n", 0, e.close) + 1
                ep.add(gs.Edit(at, at, b"\tde_jure_vassals={ " + " ".join(map(str, kids)).encode() + b" }\n",
                               "transplant", "seam"))
            if children.get(parent):
                self.report.seam_parents += 1

    def _name_mirror_cases(self, head: dict) -> None:
        """The mirror of the mixed case (director 2026-10-26 15:5x): a copied barony inside a CAMPAIGN county,
        held by a copied ruler who also holds land outside that county, goes with its county to the campaign
        holder on load (re-save of e2e_1c5: 4, the Chinese emperor's baronies in campaign counties). Named."""
        tm = self.tr.spaces["title"]
        ref_dj, ref_holder = {}, {}
        for r, e in self.entries(TITLES).items():
            b = self.ref[e.open:min(e.close, e.open + 4096)]
            m = re.search(rb"\n\tde_jure_liege=(\d+)", b)
            h = re.search(rb"\n\tholder=(\d+)", b)
            if m:
                ref_dj[r] = int(m.group(1))
            if h:
                ref_holder[r] = int(h.group(1))
        held: dict[int, list[int]] = defaultdict(list)
        for r, h in ref_holder.items():
            held[h].append(r)
        keys = self.title_keys()
        for r in sorted(self.carry["title"]):
            k = keys.get(r, "")
            c, h = ref_dj.get(r), ref_holder.get(r)
            if not k.startswith("b_") or c not in tm.join or h is None or not self.keep("character", h, "holder"):
                continue
            x = head.get(tm.join[c], (None, None, None))[1]           # the campaign county's holder
            if x is None or x == self.tr.spaces["character"].translate(h):
                continue
            if all(keys.get(t, "").startswith("b_") and ref_dj.get(t) == c for t in held[h]):
                continue                                              # a lone baron: not this case
            self.report.reparent_cases["goes with its county"] += 1
            self.report.reparent_left.append({
                "barony": k, "county now": self.save_title_key(tm.join[c]), "county in 1.20": self.save_title_key(
                    tm.join[c]), "holder": self.tr.spaces["character"].translate(h), "case": "goes with its county",
                "reason": f"goes with its 1.20 county to the campaign holder {x}", "goes to": x})

    def _reparent(self, ep: gs.EditPass) -> None:
        """Step 1c: each re-parented barony points at its 1.20 county (de jure and de facto, as the engine
        requires of a barony); a baron-only holder's contract binds them to that county's holder."""
        plan = self.reparent_plan()
        head = self._ent["_reparent_head"]
        rep = self.report
        stitles = dict(T.entries(self.save, TITLES)) if plan else {}
        settled = self.settled_baronies()
        for b, (old, want, case) in sorted(plan.items()):
            rep.reparent_cases["settled (1c-bis)" if b in settled else case] += 1
            if not self.reparented(b):
                rep.reparent_left.append({"barony": head[b][0], "county now": self.save_title_key(old) if old
                                          else None, "county in 1.20": self.title_keys().get(want[1], "")
                                          if want[0] == "ref" else self.save_title_key(want[1]),
                                          "holder": head[b][1], "case": case,
                                          "reason": {"capital": "capital of its 1.20 county (the county's "
                                                                "holder always holds it)",
                                                     "mixed": "the holder also holds land outside the 1.20 "
                                                              "county; one person cannot have two lieges"
                                                     }.get(case, case),
                                          "goes to": self.county_holder(want, head)})
                continue
            new = str(self._out_title(want)).encode()
            e = stitles[b]
            for fld in (b"de_jure_liege", b"de_facto_liege"):
                m = re.search(rb"\n\t" + fld + rb"=(\d+)", self.save[e.open:e.close])
                if m:
                    ep.add(gs.Edit(e.open + m.start(1), e.open + m.end(1), new, "transplant", "1c " + fld.decode()))
                else:
                    at = self.save.rfind(b"\n", 0, e.close) + 1
                    ep.add(gs.Edit(at, at, b"\t" + fld + b"=" + new + b"\n", "transplant", "1c " + fld.decode()))
        # S3: an orphan campaign title gets its 1.20 de jure parent
        tmo = self.tr.spaces["title"]
        for (side, s), p in sorted(self.orphan_plan().items()):
            if side != "save":
                continue
            e = stitles.get(s) if stitles else dict(T.entries(self.save, TITLES)).get(s)
            if e is None:
                continue
            at = self.save.rfind(b"\n", 0, e.close) + 1
            new_p = tmo.join[p] if p in tmo.join else tmo.translate(p)
            ep.add(gs.Edit(at, at, f"\tde_jure_liege={new_p}\n".encode(), "transplant", "S3 de jure parent"))
            rep.orphans_reparented.append(f"{self.save_title_key(s)} -> {self.title_keys().get(p, '')}")
        self._name_mirror_cases(head)
        # campaign characters' entries, each edited once: contract lists, domains, court (1c and 1c-bis)
        ops: dict[int, dict] = defaultdict(lambda: {"vc_drop": set(), "vc_add": [], "dom_drop": set(),
                                                    "dom_add": [], "employer": None})
        for cid, start, old, new in self.contract_moves():
            close = gs.match_brace(self.save, start)
            lg = re.search(rb"\n\t+liege=(\d+)", self.save[start:close])
            ep.add(gs.Edit(start + lg.start(1), start + lg.end(1), str(new).encode(), "transplant", "1c contract"))
            ops[old]["vc_drop"].add(cid)
            rep.contracts_moved += 1
        for x, cids in self._ent.get("_gains_left", {}).items():
            ops[x]["vc_add"].extend(cids)
        self._settle_save_side(ep, stitles, head, ops)
        self._kept_save_side(ep, ops)
        chars = self._save_chars()
        for c, op in ops.items():
            ent = chars.get(c)
            if ent is None:
                continue
            text = self.save[ent.start:ent.end]
            new = _edit_landed_list(text, b"vassal_contracts", add=op["vc_add"], drop=op["vc_drop"])
            if op["dom_add"] or op["dom_drop"]:
                new = _edit_landed_list(new, b"domain", add=op["dom_add"], drop=op["dom_drop"])
                new = _primary_first(new, self.output_title_key)      # a promoted baron's county is his primary
                rc = re.search(rb"\n\t\trealm_capital=(\d+)", new)
                left = re.search(rb"\n\t\tdomain=\{([^}]*)\}", new)
                ids = left.group(1).split() if left else []
                if rc and int(rc.group(1)) in op["dom_drop"]:
                    new = _set_landed_scalar(new, b"realm_capital", int(ids[0]) if ids else None)
            if op["employer"] is not None:
                new = _set_employer(new, op["employer"])
            if new != text:
                ep.add(gs.Edit(ent.start, ent.end, new, "transplant", "1c character"))

    def _kept_save_side(self, ep: gs.EditPass, ops: dict) -> None:
        """R15's held titles, the campaign side: the holder gains the regained titles in his domain (primary first,
        by the ops pass) and the moved contracts in his list; his own titles whose de facto liege R15 stripped, or
        his old primary under a new one, point where holdings_plan says."""
        hp = self.holdings_plan()
        if not hp["holders"]:
            return
        km = self.tr.spaces["vassal_contract"]
        for h, d in hp["holders"].items():
            ops[h]["dom_add"].extend(d["dom_add"])
        for i, (h, _x) in hp["contracts"].items():
            ops[h]["vc_add"].append(km.translate(i))
        for i, (old, new, path) in sorted(hp["contract_moves"].items()):   # a baron's contract follows his county
            e = dict(T.entries(self.save, path)).get(i)
            m = re.search(rb"(\n\t+liege=)(\d+)", self.save[e.open:e.close]) if e is not None else None
            if m is None:
                continue
            ep.add(gs.Edit(e.open + m.start(2), e.open + m.end(2), str(new).encode(), "transplant",
                           "R15 kept: contract liege"))
            ops[old]["vc_drop"].add(i)
            ops[new]["vc_add"].append(i)
        stitles = dict(T.entries(self.save, TITLES))
        for h, d in hp["holders"].items():
            for s, liege in sorted(d["liege_fix"].items()):
                e = stitles.get(s)
                if e is None:
                    continue
                m = re.search(rb"\n\tde_facto_liege=(\d+)", self.save[e.open:e.close])
                if m and liege is not None:
                    ep.add(gs.Edit(e.open + m.start(1), e.open + m.end(1), str(liege).encode(), "transplant",
                                   "R15 kept: de facto liege"))
                elif m is None and liege is not None:
                    at = self.save.rfind(b"\n", 0, e.close) + 1
                    ep.add(gs.Edit(at, at, f"\tde_facto_liege={liege}\n".encode(), "transplant",
                                   "R15 kept: de facto liege"))
        for op in ops.values():
            op["dom_add"] = list(dict.fromkeys(op["dom_add"]))

    def _settle_save_side(self, ep: gs.EditPass, stitles: dict, head: dict, ops: dict) -> None:
        """Step 1c-bis, the campaign side: the new holder gains the county (and a carried capital, and a capital a
        landless baron gives up) in his domain and the copied barons' contracts in his list; a capital baron who
        is not the new count gives his barony to him, loses his contract and goes to his court. Report rows."""
        settle = self.settle_plan()
        if not settle:
            return
        rep = self.report
        tm, km = self.tr.spaces["title"], self.tr.spaces["vassal_contract"]
        contracts = {}
        for path in ("vassal_contracts/database", "vassal_contracts/active"):
            try:
                for i, e in T.entries(self.save, path):
                    v = re.search(rb"\n\t+vassal=(\d+)", self.save[e.open:e.close])
                    lg = re.search(rb"\n\t+liege=(\d+)", self.save[e.open:e.close])
                    if v:
                        contracts[int(v.group(1))] = (i, e, int(lg.group(1)) if lg else None)
            except T.TranslationError:
                continue
        for c, d in settle.items():
            new, c_out = d["new"], tm.translate(c)
            ops[new]["dom_add"].append(c_out)
            if d["capital"] is not None:
                ops[new]["dom_add"].append(tm.translate(d["capital"]))
            ops[new]["vc_add"].extend(km.translate(i) for i in d["carried_contracts"])
            for s, fate in sorted(d["baronies"].items()):
                baron = head[s][1]
                if fate == "landless":
                    e = stitles[s]
                    m = re.search(rb"\n\tholder=(\d+)", self.save[e.open:e.close])
                    if m:
                        ep.add(gs.Edit(e.open + m.start(1), e.open + m.end(1), str(new).encode(), "transplant",
                                       "1c-bis capital holder"))
                    ops[baron]["dom_drop"].add(s)
                    ops[new]["dom_add"].append(s)
                    ops[baron]["employer"] = new
                    ct = contracts.get(baron)
                    if ct is not None:
                        i, ce, lg = ct
                        a, b = gs.removal_span(self.save, ce.start, ce.end)
                        ep.add(gs.Edit(a, b, b"", "transplant", "1c-bis contract removed"))
                        if lg is not None:
                            ops[lg]["vc_drop"].add(i)
                elif fate == "count" and baron != (head.get(d["old_county"], ("", None, None))[1]):
                    ops[baron]["dom_add"].append(c_out)          # a promoted family baron (already added if new)
                rep.settled.append({
                    "barony": head[s][0], "old county": self.save_title_key(d["old_county"]) if d["old_county"]
                    else None, "old count": head.get(d["old_county"], ("", None, None))[1],
                    "new county": self.title_keys().get(c, ""), "old holder": self.tr.spaces["character"]
                    .translate(d["x"]), "new holder": new, "branch": d["branch"], "baron": baron,
                    "baron's fate": {"count": "holds the county", "vassal": f"keeps the barony, vassal of {new}",
                                     "landless": f"landless at {new}'s court: capital of the county; no built "
                                                 "barony free in it"}[fate]})
            for r in d["x_kept"]:
                rep.settled.append({
                    "barony": self.title_keys().get(r, ""), "old county": None, "old count": None,
                    "new county": self.title_keys().get(c, ""), "old holder": self.tr.spaces["character"]
                    .translate(d["x"]), "new holder": self.tr.spaces["character"].translate(d["x"]),
                    "branch": d["branch"], "baron": self.tr.spaces["character"].translate(d["x"]),
                    "baron's fate": "held by the displaced ruler, left with him"})
        # de-duplicate: a promoted baron is also "new"
        for op in ops.values():
            op["dom_add"] = list(dict.fromkeys(op["dom_add"]))

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
