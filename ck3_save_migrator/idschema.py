"""Which fields of a CK3 gamestate entry hold ids, and of which id space (the R13 schema).

Measured, not guessed: ``tests/one-offs/measure_unit1_field_spaces.py`` walked every entry of every numbered
database in a migrated 1.8.1 save and the 1.20 reference. In the save, ids carry a generation in the top byte,
so a value >= 2^24 found in exactly one space's id set names its space with no ambiguity (68 fields, 100% in one
space). The rest were settled by name plus a check (``measure_unit1_unclear_and_highwater.py``): for example
``allegiance`` holds titles (its values are e_hre, k_france, k_england, ...) and ``culture_marker`` is never
the culture's own id, so it is plain.

A field path is the chain of keys from the entry body down to the value, normalised: a numeric key is ``#``,
a date key is ``<date>``, an anonymous block is ``[]``, a bare list value is ``*``. A path segment ``?`` in this
table matches any one key (``alive_data/inventory/equipped/?`` covers every artifact slot). A path ending in
``#key`` names the numeric KEYS at that position (``acceptance/#key``: the keys of ``acceptance={ 12=50 }`` are
culture ids). Any path ending in ``identity`` is typed: its space comes from the sibling ``type=`` (TYPE_SPACE).
"""

from __future__ import annotations

import re

PLAIN = "plain"        # not an id: a quantity, a colour, a date part, a position in a design list
TYPED = "typed"        # an ``identity=`` whose space is named by the sibling ``type=``
TRAIT = "trait"        # a position in the save's ``traits_lookup`` table (joined by trait name)
REVIEW = "review"      # meaning not settled: left unchanged and reported (see the notes below)

# id space -> the database sections that hold its entries. The three character sections are one index space
# (measured: 83,376 indices, no index in two sections). vassal contracts live in ``active`` in a 1.8.1-shaped
# save and in ``database`` in 1.20; both are one space.
SPACES: dict[str, tuple[str, ...]] = {
    "character": ("living", "dead_unprunable", "characters/dead_prunable"),
    "title": ("landed_titles/landed_titles",),
    "dynasty": ("dynasties/dynasties",),
    "house": ("dynasties/dynasty_house",),
    "artifact": ("artifacts/artifacts",),
    "memory": ("character_memory_manager/database",),
    "council_task": ("council_task_manager/active",),
    "court_position": ("court_positions/database",),
    "coat_of_arms": ("coat_of_arms/coat_of_arms_manager_database",),
    "regiment": ("armies/regiments",),
    "army_regiment": ("armies/army_regiments",),
    "army": ("armies/armies",),
    "unit": ("units",),
    "mercenary": ("mercenary_company_manager/mercenary_companies",),
    "holy_order": ("holy_orders/holy_orders",),
    "vassal_contract": ("vassal_contracts/database", "vassal_contracts/active"),
    "domicile": ("domiciles/database",),
    "diarchy": ("diarchies/database",),
    "tax_slot": ("tax_slot_manager/database",),
    "clerical_region": ("clerical_region_manager/database",),
    "situation": ("situation_manager/database",),
    "situation_group": ("situation_participant_group_manager/database",),
    "situation_sub_region": ("situation_sub_region_manager/database",),
    "story": ("stories/active",),
    "important_action": ("important_action_manager/active",),
    "faction": ("faction_manager/factions",),
    "secret": ("secrets/secrets",),
    "scheme": ("schemes/active",),
    "war": ("wars/active_wars",),
    "activity": ("activities",),
    "inspiration": ("inspirations_manager/database",),
    "culture": ("culture_manager/cultures",),
    # identity spaces: the same ids in the save and the reference (the religion rules copied these databases
    # whole from the reference; provinces keep their numbers, 99.9% measured, new ones appended)
    "faith": ("faiths/database",),
    "rite": ("rites/database",),
    "religion": ("religion/religions",),
    "holy_site": ("religion/holy_sites",),
    "organization": ("organization_manager/database",),
    "province": ("provinces",),
}
IDENTITY = frozenset({"faith", "rite", "religion", "holy_site", "organization", "province"})

# kind (a database section path) -> the space its entry keys belong to. ``ai/ai_strategies`` is keyed by
# character id (its keys are character ids; measured 100%).
KIND_SPACE: dict[str, str] = {sec: sp for sp, secs in SPACES.items() for sec in secs}
KIND_SPACE["ai/ai_strategies"] = "character"

# ``type=`` value of a typed reference -> space. ``value``/``boolean`` carry a number, not an id.
TYPE_SPACE: dict[str, str] = {
    "char": "character", "lt": "title", "faith": "faith", "rite": "rite", "council_task": "council_task",
    "prov": "province", "religion": "religion", "dyn_house": "house", "dyn": "dynasty", "culture": "culture",
    "ho": "holy_order", "situation": "situation", "artifact": "artifact", "army": "army", "mc": "mercenary",
    "fac": "faction", "story": "story", "war": "war", "act": "activity", "char_mem": "memory",
    "scheme": "scheme", "sec": "secret", "insp": "inspiration",
    "value": PLAIN, "boolean": PLAIN, "flag": PLAIN,
}

_C, _T = "character", "title"

# kind -> path -> space (or TRAIT / REVIEW). Paths not listed here and not in PLAIN_FIELDS are "unlisted": left
# unchanged and counted, so a field the schema has never seen cannot pass silently.
FIELDS: dict[str, dict[str, str]] = {
    "character": {
        "alive_data/activity": "activity",
        "alive_data/activity_invitations/*": "activity",
        "alive_data/artifact_claims/*": "artifact",
        "alive_data/claim/[]/title": _T,
        "alive_data/heir/*": _T,
        "alive_data/inspiration": "inspiration",
        "alive_data/inventory/artifacts/*": "artifact",
        "alive_data/inventory/equipped/?": "artifact",
        "alive_data/inventory/owner": _C,
        "alive_data/kills/*": _C,
        "alive_data/location/location": "province",
        "alive_data/memories/*": "memory",
        "alive_data/obedience_target": _C,
        "alive_data/owned_activities/*": "activity",
        "alive_data/pretender/*": _T,
        "alive_data/prison_data/imprisoner": _C,
        "alive_data/schemes/*": "scheme",
        "alive_data/secrets/*": "secret",
        "alive_data/stories/*": "story",
        "alive_data/targeting_schemes/*": "scheme",
        "alive_data/targeting_secrets/*": "secret",
        "court_data/army": "army",
        "court_data/council_task": "council_task",
        "court_data/court_positions/*": "court_position",
        "court_data/employer": _C,
        "court_data/host": _C,
        "court_data/regiment": "army_regiment",
        "court_data/tax_slot": "tax_slot",
        "culture": "culture",
        "dead_data/domain/*": _T,
        "dead_data/killer": _C,
        "dead_data/kills/*": _C,
        "dead_data/know_of_killer/*": _C,
        "dead_data/liege": _C,
        "dead_data/liege_title": _T,
        "dead_data/named_title": _T,
        "dynasty_house": "house",
        "family_data/betrothed": _C,
        "family_data/child/*": _C,
        "family_data/concubine": _C,
        "family_data/concubinist": _C,
        "family_data/former_concubines/*": _C,
        "family_data/former_concubinists/*": _C,
        "family_data/former_spouses/*": _C,
        "family_data/primary_spouse": _C,
        "family_data/real_father": _C,
        "family_data/spouse": _C,
        "inactive_traits/*": TRAIT,
        "landed_data/council/*": "council_task",
        "landed_data/court_positions/*": "court_position",
        # engine-internal (no script mentions it); neither as titles nor as provinces do its values lie in the
        # character's realm (22 and 5 of 4,804). Unit 2's load decides.
        "landed_data/diplo_centers/*": REVIEW,
        "landed_data/domain/*": _T,
        "landed_data/election_titles/*": _T,
        "landed_data/event_troops/[]/regiments/*": "regiment",
        "landed_data/known_schemes/*": "scheme",
        "landed_data/realm_capital": _T,
        "landed_data/sponsored_inspirations/*": "inspiration",
        "landed_data/succession/*": _C,
        "landed_data/tax_slot/*": "tax_slot",
        "landed_data/tributary_contracts/*": "vassal_contract",
        "landed_data/units/*": "unit",
        "landed_data/vassal_contracts/*": "vassal_contract",
        "landed_data/wars/*": "war",
        "organization": "organization",
        "playable_data/diarchy": "diarchy",
        "playable_data/diarchy_successor": _C,
        "playable_data/knights/*": _C,
        "recessive_traits/*": TRAIT,
        "rite": "rite",
        "traits/*": TRAIT,
    },
    "landed_titles/landed_titles": {
        "capital": _T,                        # a title id (the capital county), not a province
        "claim/*": _C,
        # a small number shared by many titles (12 on every elector of one region); its space is not settled.
        # Every candidate space (faith, rite, religion, clerical region) is identity or absent from the save.
        "clerical_elector": REVIEW,
        "clerical_region/clerical_region": "clerical_region",
        "clerical_region/domicile": "domicile",
        "coat_of_arms_id": "coat_of_arms",
        "controlled_maa/*": "regiment",
        "owned_maa/*": "regiment",
        "de_facto_liege": _T,
        "de_jure_liege": _T,
        "de_jure_vassals/*": _T,
        "domicile": "domicile",
        "heir/*": _C,
        "history/<date>": _C,
        "history/<date>/holder": _C,
        "holder": _C,
        "holy_order": "holy_order",
        "lessee": _T,
        "mercenary": "mercenary",
        "succession_election/candidate_sources/[]/character": _C,
        "succession_election/candidates/*": _C,
        "succession_election/electors/*": _C,
        "succession_election/nominations/[]/candidate": _C,
        "succession_election/nominations/[]/elector": _C,
    },
    "dynasties/dynasties": {
        "coat_of_arms_id": "coat_of_arms",
        "dynasty_head": _C,
    },
    "dynasties/dynasty_house": {
        "artifact_claims/*": "artifact",
        "artifacts_for_claim/[]/artifact": "artifact",
        "coat_of_arms_id": "coat_of_arms",
        "dynasty": "dynasty",
        "head_of_house": _C,
        "historical/*": _C,
        "house_title": _T,
        "house_unity/dynasty_house": "house",
    },
    "artifacts/artifacts": {
        "characters/*": _C,
        "history/entries/[]/actor": _C,
        "history/entries/[]/recipient": _C,
        "history/entries/[]/location": "province",
        "holy_site_owner": "holy_site",
        "owner": _C,
        "title": _T,
    },
    "character_memory_manager/database": {
        "participants/?": _C,
    },
    "council_task_manager/active": {
        "court_owner": _C,
        "last_appointed_councillor": _C,
        "owner": _C,
    },
    "court_positions/database": {
        "employee": _C,
        "employer": _C,
    },
    "culture_manager/cultures": {
        "acceptance/#key": "culture",
        "head": _C,
        "parents/*": "culture",
    },
    "diarchies/database": {
        "diarch": _C,
        "liege": _C,
    },
    "domiciles/database": {
        "culture": "culture",
        "owner_title": _T,
        "province": "province",
        "rite": "rite",
    },
    "faction_manager/factions": {
        "target": _C,
        "title_members/[]/county": _T,
    },
    "holy_orders/holy_orders": {
        "founder": _C,
        "rite": "rite",
        "title": _T,
        "titles/*": _T,
    },
    "important_action_manager/active": {
        "character": _C,
    },
    "mercenary_company_manager/mercenary_companies": {
        "county": _T,
        "culture": "culture",
        "regiments/*": "regiment",
        "title": _T,
    },
    "armies/regiments": {
        "controlling_title": _T,
        "origin": "province",
        "owner": _C,
        "owning_title": _T,
    },
    "ai/ai_strategies": {
        "advanced_ai_data/cb_target/*": _C,
        "advanced_ai_data/de_jure_overlap/id": _C,
        "advanced_ai_data/friend/id": _C,
        "advanced_ai_data/threat/id": _C,
    },
    "clerical_region_manager/database": {
        "counties/*": _T,
        "title": _T,
    },
    "situation_manager/database": {
        "history/[]/catalyst/character": _C,
        "manual_participant_candidates/*": _C,
        "sub_region_refs/*": "situation_sub_region",
    },
    "situation_participant_group_manager/database": {
        "characters/*": _C,
        "situation": "situation",
        "sub_region": "situation_sub_region",
    },
    "situation_sub_region_manager/database": {
        "data/center_province": "province",
        "participant_groups/*": "situation_group",
        "phase/future_phases/[]/history/[]/character": _C,
        "phase/sub_region": "situation_sub_region",
        "situation": "situation",
        "titles/*": _T,
    },
    "stories/active": {
        "owner": _C,
    },
    "tax_slot_manager/database": {
        "liege": _C,
        "tax_collector": _C,
        "vassals/*": _C,
    },
    "vassal_contracts/database": {
        "allegiance": _T,
        "liege": _C,
        "vassal": _C,
    },
    "provinces": {
        "holding/garrison": "regiment",
        "holding/levy": "regiment",
    },
}
for _sec in SPACES["character"]:
    FIELDS[_sec] = FIELDS["character"]
FIELDS["vassal_contracts/active"] = FIELDS["vassal_contracts/database"]

_DATE = re.compile(rb"^-?\d+\.\d+\.\d+$")


def norm_key(key: bytes | None, is_block: bool) -> str:
    """One path segment for a child's key: '#', '<date>', '[]', '*', '=' or the key itself."""
    if key is None:
        return "[]" if is_block else "*"
    if key == b"":
        return "="
    if key.isdigit():
        return "#"
    if _DATE.match(key):
        return "<date>"
    return key.decode("utf-8", "replace")


def classify(kind: str, path: str) -> str | None:
    """The space (or PLAIN/TYPED/TRAIT/REVIEW) of ``path`` in an entry of ``kind``; None when unlisted."""
    table = FIELDS.get(kind, {})
    hit = table.get(path)
    if hit is not None:
        return hit
    segs = path.split("/")
    for pat, sp in table.items():
        if "?" in pat:
            ps = pat.split("/")
            if len(ps) == len(segs) and all(p == "?" or p == s for p, s in zip(ps, segs)):
                return sp
    if segs[-1] == "identity":
        return TYPED
    if path in PLAIN_FIELDS.get(kind, ()) or path in PLAIN_FIELDS.get(_family(kind), ()):
        return PLAIN
    return None


def _family(kind: str) -> str:
    return "character" if kind in SPACES["character"] else kind


# Fields measured in the reference's entries that are not ids (quantities, colours, ticks, positions in design
# lists), generated from the field probe's output and reviewed by hand. Listing them is what lets the rewriter
# report a field it has never seen instead of passing it silently.
def _plain(*paths: str) -> frozenset[str]:
    return frozenset(paths)


PLAIN_FIELDS: dict[str, frozenset[str]] = {
    "ai/ai_strategies": _plain(
        "advanced_ai_data/budget_long_term", "advanced_ai_data/budget_reserved",
        "advanced_ai_data/budget_short_term", "advanced_ai_data/budget_war_chest",
        "advanced_ai_data/de_jure_overlap/value", "advanced_ai_data/desired_war_chest",
        "advanced_ai_data/desired_war_chest_treasury", "advanced_ai_data/execpted_legitimacy",
        "advanced_ai_data/friend/value", "advanced_ai_data/min_reserved_gold",
        "advanced_ai_data/min_reserved_treasury", "advanced_ai_data/threat/value", "advanced_ai_data/ticks/*",
        "advanced_ai_data/treasury_budget_long_term", "advanced_ai_data/treasury_budget_reserved",
        "advanced_ai_data/treasury_budget_short_term", "advanced_ai_data/treasury_budget_war_chest"),
    "armies/regiments": _plain("chunks/[]/current", "chunks/[]/max", "max", "size"),
    "artifacts/artifacts": _plain("durability", "max_durability", "quality", "wealth"),
    "character": _plain(
        "alive_data/focus/changes", "alive_data/focus/progress", "alive_data/gold/value", "alive_data/health",
        "alive_data/income", "alive_data/influence/currency", "alive_data/merit/accumulated",
        "alive_data/merit/currency", "alive_data/modifier/multiplier", "alive_data/piety/currency",
        "alive_data/prestige/accumulated", "alive_data/prestige/currency", "alive_data/stress",
        "alive_data/variables/data/[]/tick", "alive_data/variables/list/[]/duration/*", "landed_data/balance",
        "landed_data/barter_goods/value", "landed_data/current_strength", "landed_data/domain_limit",
        "landed_data/levy", "landed_data/max_power", "landed_data/power",
        "landed_data/royal_court/court_grandeur/base", "landed_data/royal_court/court_grandeur/current",
        "landed_data/royal_court/court_grandeur/expected", "landed_data/strength",
        "landed_data/strength_for_liege", "landed_data/strength_without_hires", "landed_data/vassal_limit",
        "landed_data/vassal_power_value", "landed_data/vassals_towards_limit", "mass",
        "playable_data/current_spiritual_fulfillment", "playable_data/legitimacy", "skill/*",
        "trait_xp_amounts/*", "weight/base", "weight/current", "weight/target"),
    "character_memory_manager/database": _plain("variables/list/[]/duration/*"),
    "coat_of_arms/coat_of_arms_manager_database": _plain(
        "color1/*", "color2/*", "color3/*", "colored_emblem/color1/*", "colored_emblem/color2/*",
        "colored_emblem/color3/*", "colored_emblem/instance/rotation", "colored_emblem/mask/*"),
    "culture_manager/cultures": _plain(
        "acceptance/#", "color/*", "culture_era_data/[]/join", "culture_era_data/[]/left",
        "culture_era_data/[]/progress", "culture_innovation/[]/progress", "culture_marker",
        "culture_reformation/progress", "variables/list/[]/duration/*"),
    "diarchies/database": _plain("swing"),
    "domiciles/database": _plain(
        "domicile_building_slots/[]/internal_slots/[]/slot_index", "domicile_building_slots/[]/slot_index",
        "herd", "provisions"),
    # ``key`` on dynasties and houses is the history key the join uses; the rewriter leaves it as it is
    "dynasties/dynasties": _plain("key", "prestige/accumulated", "prestige/currency"),
    "dynasties/dynasty_house": _plain("house_unity/value", "key"),
    "faction_manager/factions": _plain("power", "update_day"),
    "holy_orders/holy_orders": _plain("worldliness"),
    "important_action_manager/active": _plain("player", "scope/list/[]/duration/*", "scope/seed"),
    "landed_titles/landed_titles": _plain(
        "color/*", "succession_election/nominations/[]/strength", "treasury/value", "treasury_budgets/income",
        *(f"treasury_budgets/categories/{c}/{f}" for c in ("cardinal", "military", "ministry", "salary")
          for f in ("allocation", "base", "count", "receiver"))),
    "mercenary_company_manager/mercenary_companies": _plain("culture_name", "size"),
    "provinces": _plain("fort_level", "holding/barter_goods", "holding/income"),
    "situation_manager/database": _plain("history/[]/catalyst/value"),
    "situation_sub_region_manager/database": _plain("data/map_color/*"),
    "stories/active": _plain("seed"),    # a random seed (up to 744,748,921), not an id
    "vassal_contracts/database": _plain("levels/#", "levels/*", "subject_standing"),
}
PLAIN_FIELDS["vassal_contracts/active"] = PLAIN_FIELDS["vassal_contracts/database"]
