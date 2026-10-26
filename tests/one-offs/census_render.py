"""Census step 7: render output 1 of the census -- one row per section/database from shape_diff.json, with the
verdict and its evidence (measured by census_coverage.py, census_followup*.py, census_lookup.py and the shape
survey of the game's re-save of our output). Rows sorted: defect, left to the engine, carried, not applicable.

Usage: python -I tests/one-offs/census_render.py <shape_diff.json> <out.md> [<template.md with a {{TABLE}} line>]
"""
import json
import sys
from pathlib import Path

D, E, C, N = "**defect**", "left to the engine", "carried", "n/a"
RES = "the game's re-save of ours"
V = {
    # ---- defects
    "county_manager/counties": (D, "title key", "n", "910 new-map counties have no record (the reference and the chain have all 910); on load the engine writes them with `culture=4294967295` (none) in 910, development 0 in 740, a different rite in 498 (" + RES + "). Also 11 campaign counties renamed by R15 lost their record and 16 stale records remain under the dead keys"),
    "character_lookup": (D, "history id -> character id", "y", "R17 and R13 parse it with an unanchored `(\\d+)=(\\d+)`: 2,460 new-map history ids missing (2,413 non-numeric such as `ainu_sum_4`, 47 numeric overwritten by `han_1176`-style keys); 1,102 of the 1,351 written keys are not reference history ids; R13's character join: 140 spurious, 583 missed"),
    "armies/regiments": (D, "own id (owner -> character)", "y", "433 men-at-arms regiments owned by 303 copied rulers (`owner=` points at the person, nothing points at the regiment, so the closure never reaches them); ours 0, " + RES + " 0"),
    "stories/active": (D, "own id (owner -> character)", "n", "all 17 reference stories belong to copied people (`story_tai_migrations` 15, `story_mandala` 2); ours 0; R17 dropped the 17 `alive_data/stories` references; " + RES + " 0"),
    "culture_manager/template_cultures": (D, "positional list of culture ids (index = template)", "n", "the 55 copied cultures are not registered (reference: list = 0..243); " + RES + " unchanged at 228"),
    "dynasties/static_dynasties": (D, "positional list of dynasty ids", "n", "554 copied history dynasties are not in the static list; " + RES + " unchanged at 4,671"),
    "dynasties/static_dynasty_houses": (D, "positional list of house ids", "n", "40 copied history houses are not in the list; " + RES + " unchanged at 228"),
    "coat_of_arms/coat_of_arms_manager_name_map": (D, "name -> coat id (title keys, dynasty/house keys, history ids)", "n", "dynasty/house keys: 107 of the copied dynasties' and houses' keys missing, the engine does not add them on load (" + RES + "): defect. Title keys: 299 new-map missing, but the chain lacks all 299 too: left to the engine"),
    # ---- left to the engine
    "county_manager/monthly_change": (E, "positional (parallel to counties)", "n", "ours still has the 1.8.1 name `monthly_increase` (2,571); the engine writes `monthly_change` with 3,476 on load (" + RES + "); a schema rename, not the transplant"),
    "county_manager/monthly_increase": (E, "positional (parallel to counties)", "n", "the 1.8.1 name; the engine drops it on load (" + RES + ")"),
    "mercenary_company_manager/mercenary_companies": (E, "own id (county -> title)", "n", "167 reference companies sit in new-map counties; ours 0, but the chain lacks them too (473 = 473) and each needs its `x_` runtime title, which R14 leaves out by design. Flag: the new regions have no mercenaries"),
    "faction_manager/factions": (E, "own id (target -> character; county members)", "n", "6 reference factions target copied rulers (4 with new-map counties); factions are AI state the engine forms monthly; not filled on load (" + RES + " 162 = 162)"),
    "important_action_manager/active": (E, "own id (character)", "n", "the reference's 21 all belong to the player (0 new-map); the engine recomputes them (" + RES + ": 295)"),
    "council_task_manager/queue": (E, "list of character ids", "n", "a transient queue (13, 3 new-map); absent in the chain and in " + RES),
    "council_task_manager/active": (C, "own id (court_owner -> character)", "y", "1,888 of 1,888 new-map tasks carried; the engine removes 59 of them on load (" + RES + ")"),
    "vassal_contracts/database": (E, "own id (vassal, liege -> character)", "y", "ours writes 1.8.1-shaped `active`; the engine renames it to `database` on load (" + RES + "); 504 of 539 new-map contracts carried (35 left out: a party not copied, by design); the engine drops 61 of the carried on load"),
    "vassal_contracts/active": (E, "own id (vassal, liege -> character)", "y", "see `vassal_contracts/database`"),
    "accolades": (E, "container", "n", "an empty 1.20 manager; the engine creates it on load (" + RES + ")"),
    "activity_manager": (E, "container", "n", "an empty 1.20 manager; created on load (" + RES + ")"),
    "barter_missions": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "confederation_manager": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "epidemics": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "great_projects": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "house_relations": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "legends": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "migration_manager": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "task_contracts": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "travel_plans": (E, "container", "n", "an empty 1.20 manager; created on load"),
    "theocracy_lease_manager": (E, "container", "n", "empty; created on load"),
    "title_and_vassal_change_manager": (E, "counter", "n", "`next_id` only; created on load (" + RES + ")"),
    "triggered_event": (C, "repeated top-level (typed scopes)", "y", "365 events of copied people carried; 179 left out by the edge policy"),
    # ---- carried
    "living": (C, "character id", "y", "6,845 of 6,845 new-map living people"),
    "dead_unprunable": (C, "character id", "y", "537 of 537 (the reference writes each entry twice)"),
    "ai/ai_strategies": (C, "character id", "y", "937 of 937"),
    "landed_titles/landed_titles": (C, "own id (key= title key)", "y", "5,268 of 5,268 new-map titles; the 709 campaign-side keys ours lacks are titles R14 leaves out (holy orders on campaign land, unheld landless titles) or R15 renamed"),
    "provinces": (C, "province id", "y", "3,609 of 3,609 new-map provinces; ours has all 13,269"),
    "artifacts/artifacts": (C, "own id (owner -> character)", "y", "55 of 55"),
    "court_positions/database": (C, "own id (employer -> character)", "y", "84 of 84"),
    "character_memory_manager/database": (C, "own id (listed by a character)", "y", "883 of the 883 memories the copied living people list"),
    "dynasties/dynasty_house": (C, "own id (head_of_house -> character)", "y", "905 carried; the other 71 headed by copied people are joined by history key"),
    "dynasties/dynasties": (C, "own id (dynasty_head -> character)", "y", "865 carried; 78 joined by key"),
    "culture_manager/cultures": (C, "own id (culture_template)", "y", "55 new templates carried; the rest joined by template"),
    "coat_of_arms/coat_of_arms_manager_database": (C, "own id", "y", "6,211 coats carried; `next_id` raised"),
    "domiciles/database": (C, "own id (referenced from titles' domicile=)", "y", "412 carried (every domicile of a copied title); the 289 others (243 yurts, 21 camps, 21 estates, 8 ecclesiastical) hang off titles the transplant does not copy"),
    "clerical_region_manager/database": (C, "own id (title)", "y", "44 of 44 new-map"),
    "tax_slot_manager/database": (C, "own id (liege -> character)", "y", "9 of 9 new-map"),
    "diarchies/database": (C, "own id (liege -> character)", "y", "3 of 3 new-map"),
    "holy_orders/holy_orders": (C, "own id (title)", "y", "12 of 12 (expansion orders on)"),
    "situation_manager/database": (C, "own id", "y", "4 of 4 (China's situations)"),
    "situation_sub_region_manager/database": (C, "own id", "y", "11 of 11"),
    "situation_participant_group_manager/database": (C, "own id", "y", "55 of 55"),
    "relations/active_relations": (C, "anonymous pair (character, character)", "y", "621 of 621 with both people copied; 47 with one side copied left out by design"),
    "opinions/active_opinions": (C, "anonymous pair (character, character)", "y", "21 of 21 both-copied; 8 one-sided left out by design"),
    "traits_lookup": (C, "positional list of trait names", "y", "21 names the save lacked appended"),
    "faiths/database": (C, "identity id", "y", "copied whole by the religion rules (R8...)"),
    "rites/database": (C, "identity id", "y", "copied whole by the religion rules"),
    "religion/religions": (C, "identity id", "y", "copied whole by the religion rules"),
    "religion/holy_sites": (C, "identity id", "y", "copied by R8; R17 re-attaches the new baronies"),
    "organization_manager/database": (C, "identity id", "y", "copied by the religion rules"),
    "coat_of_arms": (C, "container + next_id", "y", "`next_id` raised by R17"),
    # ---- not applicable
    "landed_titles/important_locations": (N, "anonymous (county title id)", "n", "57 entries, all western counties (c_roma, c_byzantion, ...), 0 new-map; the chain and " + RES + " lack it too"),
    "landed_titles/dynamic_templates": (N, "anonymous (runtime x_ titles)", "n", "runtime `x_` titles are left out by design (R14)"),
    "struggle_manager/database": (N, "own id", "n", "the Iberian struggle, not a new-map object; the chain and " + RES + " lack it too"),
    "faiths/saints": (N, "anonymous (character, province)", "n", "45 saints, 0 of them copied people or new-map provinces; the chain and " + RES + " lack the block"),
    "variables/data": (N, "anonymous (global flags)", "n", "global variables, not per-object"),
    "variables/list": (N, "anonymous (global lists)", "n", "global variables, not per-object"),
    "game_rules/setting": (N, "bare list", "n", "game rules, not per-object"),
}


def default(row):
    p, cls = row["path"], row["class"]
    if p.startswith("meta_data"):
        return N, "header", "n", "the save's header block, re-derived from the gamestate"
    if cls == "ours lacks the block" and not row["ref"]:
        return E, row["kind"], "n", "an empty 1.20 database; its manager is created on load (the game's re-save of ours)"
    if row["ref"] is None:
        return N, row["kind"], "n", "absent from the 1.20 reference: campaign state, or a 1.8.1 shape"
    if cls == "ref empty: nothing to carry" or not row["ref"]:
        return N, row["kind"], "n", "the reference's block is empty: nothing to carry"
    if cls == "not in ref":
        return N, row["kind"], "n", "absent from the 1.20 reference (campaign state or a 1.8.1 shape)"
    if cls == "n/a: chain lost it too":
        return N, row["kind"], "n", "the chain lacks it too"
    if "/" not in p:
        return N, "container", "n", "a container; its databases have their own rows"
    if p.startswith("triggered_event/"):
        return N, row["kind"], "n", "part of one triggered_event block; the events have their own row"
    return N, row["kind"], "n", "player or global state, not keyed by an object the transplant adds"


def main():
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    order = {D: 0, E: 1, C: 2, N: 3}
    out = []
    for r in data["rows"]:
        v, kind, cons, why = V.get(r["path"]) or default(r)
        out.append((order[v], r["path"], v, kind, r, cons, why))
    out.sort(key=lambda x: (x[0], x[1]))
    lines = ["| section / database | key kind | ref | chain | ours | consulted by the transplant | verdict | evidence |",
             "|---|---|---:|---:|---:|:-:|---|---|"]

    def f(x):
        return "-" if x is None else f"{x:,}"
    for _, p, v, kind, r, cons, why in out:
        rep = f" (x{r['repeats']['ref']:,} / {r['repeats']['chain']:,} / {r['repeats']['ours']:,} blocks)" if r["repeats"] else ""
        lines.append(f"| `{p}`{rep} | {kind} | {f(r['ref'])} | {f(r['chain'])} | {f(r['ours'])} | {cons} | {v} | {why} |")
    table = "\n".join(lines)
    if len(sys.argv) > 3:                     # a document template with a {{TABLE}} line
        doc = Path(sys.argv[3]).read_text(encoding="utf-8").replace("{{TABLE}}", table)
        Path(sys.argv[2]).write_text(doc, encoding="utf-8")
    else:
        Path(sys.argv[2]).write_text(table + "\n", encoding="utf-8")
    print(f"{len(out)} rows: " + ", ".join(f"{k} {sum(1 for x in out if x[2] == k)}" for k in (D, E, C, N)))


if __name__ == "__main__":
    main()
