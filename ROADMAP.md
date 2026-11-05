# Roadmap

The living roadmap for ck3-save-updater is the repository's first issue, kept pinned: https://github.com/djdarcy/ck3-save-updater/issues/1. Notes and quick ideas go to the second: https://github.com/djdarcy/ck3-save-updater/issues/2. This file is the plan in prose, refreshed at each release. The [CHANGELOG](CHANGELOG.md) says what each version actually shipped.

## Where this comes from

The tool began on 2026-10-24 with one campaign: an Empire of Ireland saved in January 2023 by game version 1.8.1 with 34 mods, which 1.20 would not load. Within a day the save loaded. Within a week it played, with its custom faith intact, the map regions added since 1.13 populated from a reference save, and the characters' faces restored. Every crash and freeze found in play was traced and fixed in the tool. The founding campaign is still the measure of every change: the same save through the same command must give the same bytes.

The general tool grew out of that. Rules became patch files anyone can read and write. A player's own fixes run in the same command as the built-in rules. The plan says what will run, what is skipped, and why.

## Done: 0.4.0, the first release (2026-11-03)

0.4.0 is on PyPI: `pip install ck3-save-updater`. It does the whole job for the founding campaign through the public command, with nothing a stranger could not also do.

- `ck3update status` says what an update will do, and whether it can, before anything runs. `ck3update update` writes the updated save beside the original.
- The game, the save folder and the reference save are found by themselves. `ck3update reference-mod` makes the bookmark mod for a reference save on the campaign's date.
- Religion is rebuilt from the reference save. A save from before the 1.13 map rework gets the new map's regions and their people, by default.
- Faces are converted to the gene layout of the portrait mods the player loads with, for modded saves too. `--old-portrait-mods` covers a save whose mods have changed since.
- A packs folder for the player's own fixes, a record per campaign so a later save is updated with the same inputs, `--in-place` with a backup, and a re-check of an already-updated save.
- A Quick start, a glossary, a grouped `-h`, and a documentation site.

Measured: one campaign of 34 mods, from 1.8.1 to 1.20.1.2. The built-in rules cover saves from 1.8 onwards. Saves older than 1.8 are refused for now.

## Next: 0.4.x

Fixes and measurements on what 0.4.0 shipped, in roughly this order:

1. **Small fixes found while releasing.** A note above `ck3update rules` saying the list is in run order. A bare `ck3update tools` that explains itself. `--in-place` refusing an existing backup before the update runs, not after.
2. **More of each face** ([#40](https://github.com/djdarcy/ck3-save-updater/issues/40)). Nine of the 133 values in each 1.8.1 face are not carried yet. The first step is an hour's measurement of which old portrait-mod build the save's last three places belong to. Then six portrait genes that a mod renamed. Every change is judged by side-by-side screenshots against the old game.
3. **Saves older than 1.8** ([#41](https://github.com/djdarcy/ck3-save-updater/issues/41)). The point is to test how well the update works across very different game versions. Older saves of the founding campaign run through the rules first, with the game's major updates on either side of each break tested.
4. **The open issues 0.4.0 touched**, checked against what shipped and closed or updated: the map rework ([#6](https://github.com/djdarcy/ck3-save-updater/issues/6)), cultures ([#7](https://github.com/djdarcy/ck3-save-updater/issues/7)), portraits ([#8](https://github.com/djdarcy/ck3-save-updater/issues/8)).

## Then: 0.5.x

1. **Editing a save on purpose.** The same engine with a second front door, for changes a player asks for by name. Every edit goes in a ledger so it can be reverted, into a new save by default or in place with a backup. Edits are never part of an update.
   - The first edit: change a character's sex, found by id or by full name, for the succession cases where a mixed-law inheritance would split the realm.
   - The second: a queued event whose outcome the game rolled when it was created. A player can remove it, or change its outcome, so one bad roll does not wreck a storyline.
2. **Full coverage without the game.** The old shapes the game still converts on its own first load (schemes, contracts, activities, culture fields) converted by the tool. A save is then current when the tool says so, and a check on the game's own re-save reports anything a future game version stops converting.
3. **A field-coverage check**, shipped with its baseline per game version: fields the target game writes on every character, title or dynasty that a carried entry lacks. It would have caught the missing nickname text before a player saw a garbled name.

## Toward 1.0.0

A proposal, for discussion. 0.4.0 is alpha. 1.0.0 would mean:

- **A second campaign proven**, from someone else's machine and mod list, not only the founding one.
- **More than one starting version proven**, from #41's measurements.
- **One game update handled after release** ("patch day"): `ck3update gamediff` shows what changed between two game folders, a new pack declares the new version span, and a campaign is played through it. This is the case the tool was built for.
- **Faces judged right by eye** on the founding campaign's tracked characters (#40).
- **A beta period** with players other than the maintainer, and their reports closed.

## Later

- **Reaching back into our own libraries.** Pieces built here that the shared DazzleLib stack lacks and could take: the byte-verified atomic save writer, the one-plan pattern with its "not knowable yet" state, trust-once for user extensions, the block renderer, and game discovery once a second game tool exists.
- **Companion content.** The founding campaign's custom faith, its artifacts and its founder's lineage as a mod of their own, installed by the tool as an option with an honest label. The campaign's end state carried into the later Paradox games through the community converters, with a small mod per game for what the converters cannot carry. These are the maintainer's own project; the tool stays general.
- **The mods.** The founding campaign's old mod set, one by one: which still work in 1.20, which need a maintained replacement, which the maintainer takes over. Tracked, not scheduled.
- **Performance.** An old large save stalls periodically in 1.20 (an alert's check running on a timer, and portrait rebuilds on a short cache). A small mod works around it. A proper fix, or a general performance mod, is an idea.

## What this tool will not do

- Invent an outcome. A rule carries what the save holds and reports what it cannot carry. What the game does to every save on load is data; a change of our choosing is an edit, and edits are a separate command the player asks for.
- Run code you did not trust. A pack that runs a script or a program runs only after `ck3update trust <pack>`, and the plan shows it either way.
- Change the save you gave it, unless you ask for `--in-place`, and then only after a backup.
