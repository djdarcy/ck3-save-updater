"""Builder contracts: for every rule that builds an entry field by field, what it writes for each field the game's own
entries of that kind carry.

The director's ruling (2026-11-16, after finding F25: R10 built the custom faith from a hand-written list and left out
faith_type, a field 1.20 added): which fields an entry has is the game's to say; what a field holds is never copied
from a neighbouring entry. So each field of the game's own entry of the kind is declared, once, as one of:

* ``carried``  -- taken from the old save's own entry;
* ``derived``  -- computed, and the reason says from what;
* ``absent``   -- left out on purpose, with the measurement that showed the game does the same;
* ``on_load``  -- left out because the game fills it in when it loads the save, with that measurement;
* ``unknown``  -- not written and not yet settled; lint names it to the player.

A test fails on any field of the game's own entries (the shipped baseline: field names only) that a contract for that
kind does not mention, so a new game version's new field fails here before a player sees a blank. Lint reads the same
declarations: ``absent`` and ``on_load`` are its allow-list, ``unknown`` stays a warning. One list, not two.

A contract whose kind the baseline does not hold (too few entries of it in a fresh game) says so in ``compare``; its
fields were measured against the game's re-save of an updated save when the rule was built.
"""
from __future__ import annotations

CARRIED, DERIVED, ABSENT, ON_LOAD, UNKNOWN = "carried", "derived", "absent", "on_load", "unknown"
STATUSES = (CARRIED, DERIVED, ABSENT, ON_LOAD, UNKNOWN)

_IDENTITY = "the old faith's own value"
_CONDITIONAL = "the game writes it only on some faiths ({}); a faith founded in the old save has none of it yet"

CONTRACTS: dict[str, dict] = {
    "R10 custom faith": {
        "kind": "faiths/database",
        "builder": "ck3_save_migrator/rules/religion_1_20.py r10_custom_faith (faith_lines)",
        "fields": {
            "faith_type": (DERIVED, "the faith it was created from (its origin faith's faith_type): 1.20 keeps the "
                                    "god's names on the type (F25)"),
            "religion": (DERIVED, "the 1.20 religion of the old faith's religion"),
            "main_rite": (DERIVED, "the rite R10 makes for it"),
            "organization": (DERIVED, "the organization R10 makes for it"),
            "holy_sites": (CARRIED, "the old faith's holy sites, by template, as 1.20 holy-site ids"),
            "eminent_holy_sites": (DERIVED, "its own holy sites that its origin faith counts as eminent, else its "
                                            "first holy site; 1 to 3 (game/common/defines FAITH_EMINENT_HOLY_SITES_*)"),
            "changes": (CARRIED, "the old faith's dated history (empty when it has none, as in the game's own)"),
            "origin": (DERIVED, "the faith of the 1.20 rite matching the old faith's template"),
            "historical": (DERIVED, "no: a faith founded in play"),
            "tag": (DERIVED, "dynamic_faith_<id>, as the game names a faith founded in play"),
            "name": (CARRIED, _IDENTITY), "adjective": (CARRIED, _IDENTITY), "adherent": (CARRIED, _IDENTITY),
            "adherent_plural": (CARRIED, _IDENTITY), "desc": (CARRIED, _IDENTITY), "color": (CARRIED, _IDENTITY),
            "icon": (CARRIED, _IDENTITY), "texticon": (CARRIED, _IDENTITY),
            "graphical_faith": (CARRIED, _IDENTITY), "piety_icon_group": (CARRIED, _IDENTITY),
            "tenet_background_icon": (DERIVED, '"", as the game writes it on every faith'),
            "tenet_heretical_background_icon": (DERIVED, '"", as the game writes it on every faith'),
            "tenet_neutral_background_icon": (DERIVED, '"", as the game writes it on every faith'),
            "tenet_unknown_background_icon": (DERIVED, '"", as the game writes it on every faith'),
            "fervor": (CARRIED, "the old faith's fervor (50 when it has none)"),
            "religious_head": (DERIVED, "the head title R9 carries, else none"),
            "tenet": (CARRIED, "the old faith's tenets that 1.20 still defines"),
            "doctrine": (CARRIED, "the old faith's doctrines that 1.20 still defines"),
            "tenets": (ON_LOAD, "the game fills it in on load: faith 103 and its rite gain it in the game's re-save "
                                "of an updated save (refactor advisor, 2026-11-16)"),
            "saints": (ABSENT, _CONDITIONAL.format("19% of the 1.20.1.2 reference: saints canonised in play")),
            "variables": (ABSENT, _CONDITIONAL.format("9% of the reference: script variables set in play")),
            "tenet_popularity": (ABSENT, _CONDITIONAL.format("6% of the reference")),
            "active_clerical_electors": (ABSENT, _CONDITIONAL.format("1% of the reference: clerical elections")),
            "inactive_clerical_electors": (ABSENT, _CONDITIONAL.format("1% of the reference: clerical elections")),
        },
    },
    "R10 custom faith's main rite": {
        "kind": "rites/database",
        "builder": "ck3_save_migrator/rules/religion_1_20.py _rite_text",
        "fields": {
            "faith": (DERIVED, "the custom faith's id"),
            "founder": (CARRIED, "the old faith's founder"),
            "head_of_rite": (DERIVED, "none, as on a rite made in play"),
            "origin_rite": (DERIVED, "none (4294967295), as the game writes on a rite made in play"),
            "data": (DERIVED, "the faith's identity, tenets and doctrines, as R10 writes the faith"),
            "convert": (DERIVED, "yes"), "enabled": (DERIVED, "yes"), "override_name": (DERIVED, "no"),
            "source": (DERIVED, "fallback, as on a rite made in play"),
            "rite_type": (ABSENT, "a rite made in play has none: the game's own 1.20.1.2 save writes its rites 150 "
                                  "and 151 (Catholicism and Orthodoxy, made at the 987 start) without one, as the "
                                  "update writes the rites it makes"),
            "cultures": (ABSENT, "the game writes it on 3% of rites (5 of 152 in the reference): cultures a rite was "
                                 "adopted by in play"),
        },
    },
    "R10 custom faith's organization": {
        "kind": "organization_manager/database",
        "builder": "ck3_save_migrator/rules/religion_1_20.py r10_custom_faith (org)",
        "fields": {
            "faith": (DERIVED, "the custom faith's id"),
            "coat_of_arms_id": (ABSENT, "the game gives 69% of organizations one; R8 drops it on purpose for "
                                        "carried ones (religion_1_20.py), and a new one needs a coat the game makes"),
        },
    },
    "vassal contract (transplant, title lock-step)": {
        "kind": "vassal_contracts/database",
        "builder": "ck3_save_migrator/transplant.py contract_entry",
        "fields": {
            "vassal": (DERIVED, "the vassal the contract is for"),
            "liege": (DERIVED, "the liege holding the vassal's de jure liege title"),
            "date": (DERIVED, "the save's date"),
            "levels": (DERIVED, "{ 1 }, the default obligation levels"),
            "contract_group": (DERIVED, "the government's contract group, when known; left out otherwise"),
            "liege_dynasty_date": (ON_LOAD, "the game fills it in on load: 3,602 of 3,602 contracts carry it in the "
                                            "game's re-save of an updated save (refactor advisor, 2026-11-16)"),
            "allegiance": (ABSENT, "the game writes it on 2% of contracts (special subject types)"),
            "subject_standing": (ABSENT, "the game writes it on under 0.1% of contracts"),
        },
    },
    "R27 house feud": {
        "kind": "house_relations/database",
        "compare": "the 1.20.1.2 reference holds no house relations; the fields were measured on the game's re-save",
        "builder": "ck3_save_migrator/rules/to_1_20.py R27",
        "fields": {
            "houses": (DERIVED, "the two feuding houses"),
            "type": (DERIVED, "default_house_relation"),
            "level": (DERIVED, "default_house_relation_level_feud"),
            "fraction": (DERIVED, "the feud's progress, as the rule sets it"),
        },
    },
    "R28 no-fertility relation": {
        "kind": "opinions/active_opinions",
        "builder": "ck3_save_migrator/rules/to_1_20.py R28",
        "fields": {
            "owner": (DERIVED, "the first of the pair"),
            "target": (DERIVED, "the second of the pair"),
            "scripted_relations": (DERIVED, "the no-fertility relation"),
            "temporary_opinion": (ABSENT, "an opinion entry that holds only relations has none: the game's own "
                                          "re-save of an updated save writes 41,606 of its 115,410 opinion entries "
                                          "without one (the 1.20.1.2 reference's 52 opinions are all temporary "
                                          "ones, from a fresh game)"),
        },
    },
    "R29 scheme thaw": {
        "kind": "schemes/active",
        "compare": "the 1.20.1.2 reference has too few schemes to compare; the fields were measured on the game's "
                   "day-one re-save of 1,334 carried plots and 1,062 it started itself (2026-11-05)",
        "builder": "ck3_save_migrator/rules/to_1_20.py R29 (_SCHEME_START, agent_slots)",
        "fields": {
            "status": (DERIVED, "the scheme's state"), "opportunities": (DERIVED, "0"),
            "semiyearly_update_days": (DERIVED, "0"), "last_update": (DERIVED, "1.1.1"),
            "ramping_success_chance": (DERIVED, "0"), "breach": (DERIVED, "0"), "phases": (DERIVED, "0"),
            "next_id": (DERIVED, "the number of agent slots"),
            "agent_slots": (DERIVED, "one per agent the scheme type defines, seated from the old agents"),
        },
    },
    "R3 title_name_data": {
        "kind": "landed_titles/landed_titles title_name_data",
        "compare": "a block inside a title, not a database: the baseline records depth-1 fields of entries only",
        "builder": "ck3_save_migrator/rules/to_1_20.py R3",
        "fields": {
            "name": (CARRIED, "the title's inline name"), "article": (CARRIED, "the title's inline article"),
            "adj": (CARRIED, "the title's inline adjective"), "pre": (CARRIED, "the title's inline prefix"),
            "title_history_names": (ABSENT, "the 1.20 reference writes it on 27% of titles; not in a 1.8 save "
                                            "(R3's docstring)"),
        },
    },
    "editor: queued event": {
        "kind": "triggered_event",
        "compare": "a block in the event queue, not a database; the layout was measured on the game's own queue "
                   "(finding F20, a hand-scheduled event fired in the game)",
        "builder": "ck3_save_migrator/events.py event_block",
        "fields": {
            "event": (DERIVED, "the event named"), "scope": (DERIVED, "the character as root, and a seed"),
            "date": (DERIVED, "the date asked for"),
        },
    },
}


def allowed() -> dict[tuple[str, str], str]:
    """(kind, field) -> reason, for every ``absent`` or ``on_load`` declaration: lint's allow-list."""
    out: dict[tuple[str, str], str] = {}
    for c in CONTRACTS.values():
        for f, (status, why) in c["fields"].items():
            if status in (ABSENT, ON_LOAD):
                out.setdefault((c["kind"], f), why)
    return out


def undeclared(kind: str, baseline_fields) -> list[str]:
    """The fields of the game's own entries of ``kind`` that a contract for that kind does not mention."""
    declared = set()
    for c in CONTRACTS.values():
        if c["kind"] == kind:
            declared |= set(c["fields"])
    return sorted(set(baseline_fields) - declared)
