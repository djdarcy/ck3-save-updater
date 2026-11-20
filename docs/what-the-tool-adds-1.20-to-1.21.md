# What the updater repairs after 1.21's own conversion

Crusader Kings III can open a 1.20 save in 1.21. On that first load the game converts the save to 1.21's new economy, and the save plays. This page lists what that conversion keeps, what it gets wrong, and what it loses, and what the updater does about each.

Every item comes from a measurement. This project's founding campaign, updated to 1.20 and saved in 987, was converted by the game, saved, and compared with the save it came from. The counts below are from that campaign. Your own save will have different numbers, but the same kinds of losses.

The updater works in two steps around the game's own conversion. Before your first load in 1.21, it adds to your 1.20 save what the conversion would otherwise lose. After the game has converted and saved it, `update --witness` repairs the rest from your last 1.20 save. See [updating a save](updating-a-save.md) for how to run both, and [the rules](rules.md) for each patch.

## What the game's conversion keeps

The conversion does most of the work, and the updater leaves it to the game.

- Holding types come through unchanged: castles stay castles and cities stay cities.
- Characters, their faces, families, titles and realms come through.
- Markets are created empty on the first load, and the game fills them once time runs. On the founding campaign, production went from nothing to about 197,000 in seven months of play.

## What the conversion gets wrong, and the updater repairs

- **Title types.** The conversion writes an empty type on some titles (noble families, landless adventurers, cardinals, church titles, older mercenary companies). The game then fails to read it back, and logs an error for each title on every load. The updater fills each type the way a new 1.21 game would ([R38](rules.md)). On the founding campaign: 1,974 titles typed, and the error log shrank by exactly 1,974 lines.
- **Old cooldowns.** The conversion blanks the names of cooldowns for decisions the game later replaced (pilgrimages, hunts, feasts) and logs an error for each on every load. The updater drops them, since they do nothing ([R39](rules.md)). 2,187 dropped, and 2,187 fewer error lines.
- **Province sizes.** The conversion sets every province to the smallest size. A new 1.21 game gives great cities like Rome and Constantinople their historical size. Size decides how many districts a holding has room for, so after the conversion every great city has the fewest. The updater raises each province to the size a new game gives it and never lowers one ([R40](rules.md)). 547 raised.
- **Holding tiers.** The conversion puts every holding's main building back to tier 1. The updater restores the tier your last 1.20 save had ([R44](rules.md)). 274 restored.
- **Baronies that moved.** 1.21 moved some baronies to a different county, and the conversion hands each one to that county's ruler. The updater gives each back to its holder in your 1.20 save ([R37](rules.md)). 75 of 83 kept by the game; it reassigned the other 8.

## What the conversion loses, and the updater keeps

- **Wonders and special buildings.** The conversion drops every wonder and great work. The updater writes each back as its 1.21 district ([R33](rules.md) before the load, [R35](rules.md) after). All 134 came through on the founding campaign.
- **Regular buildings.** In 1.21 a holding's buildings live inside districts, and the conversion leaves every district empty. On the founding campaign, 19,569 buildings went to none. The updater writes your buildings into the districts 1.21 has for them, where 1.21's rules allow it ([R41](rules.md) before the load, [R42](rules.md) after). 1,764 districts with 1,985 buildings, all kept by the game. The buildings 1.21 has no place for are listed on [what is not carried over](not-carried-over.md).
- **Duchy-capital buildings.** The conversion drops every one: marches, jousting lists, blacksmiths, royal forests and the rest. The updater writes each into a 1.21 duchy-capital district, where the game allows that district ([R48](rules.md) before the load, [R45](rules.md) after). 7 of 9 on the founding campaign. 1.21 has no district for the other two (tax assessors). Checked in the game: the districts were still there after the game's own save, and the holding view shows them enabled.
- **Quarries, logging camps, orchards and elephant pens.** These became resource districts in 1.21 (stone, forestry, fruit, ivory), and the conversion writes none of them. The updater writes each where the county has the trade good, at your old tier, up to tier 2 ([R46](rules.md)). Where the game already placed a different resource district, it asks you what to do (see `--auto` in [updating a save](updating-a-save.md)). 426 districts written, 21 raised, 161 small buildings added. Checked in the game: all kept after its own save.
- **Roads.** The conversion makes no roads. A new 1.21 game has about 4,200. The updater brings in a 1.21 reference save's roads ([R34](rules.md), [R36](rules.md)). All kept.
- **The new innovations.** In a new 1.21 game every culture lists every innovation, and a culture can only research what it lists. The conversion adds none of the innovations new in 1.21, such as heavy plow, coppicing, prospecting and monasticism. So a converted culture can never research them, and some district levels can never be reached. The updater adds each missing innovation to each culture ([R47](rules.md)). 25 innovations were missing on the founding campaign, and 5,844 entries were added across 284 cultures. In two years of play afterwards, cultures researched them.

## The difference in play

The buildings matter in play. The founding campaign was played for about two years twice: once repaired without its buildings, and once with them carried. With the buildings, it produced 37% more goods and earned 16% more from its holdings, and Rome's output more than doubled. 1,758 of the 1,759 holdings the updater filled were still intact after the two years.

## What neither the game nor the updater carries

Some things 1.21 has no place for, such as the Great Wall's upper tiers and buildings with no clear 1.21 counterpart. They are listed, with the reasons, on [what is not carried over](not-carried-over.md).
