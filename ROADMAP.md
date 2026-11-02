# Roadmap

The living roadmap for ck3-save-updater lives in the repository's first issue, kept pinned: https://github.com/djdarcy/ck3-save-updater/issues/1. Notes and quick ideas go to the second: https://github.com/djdarcy/ck3-save-updater/issues/2. This file is the plan in prose, refreshed every so often (ideally at each release). The issue holds the detail and its history, and the [CHANGELOG](CHANGELOG.md) says what each version actually shipped.

## Where this comes from

The tool began on 2026-10-24 with one campaign: an Empire of Ireland saved in January 2023 by game version 1.8.1 with 34 mods, which 1.20 would not load. Within a day the save loaded; within a week it played, with its custom faith intact, the map regions added since 1.13 populated from a reference save, the characters' faces restored, and every crash and freeze found in play traced and fixed in the tool. The founding case is still the measure of every change, where the same save through the same command must give the same bytes.

The general tool grew out of that: rules became patch files anyone can read and write, a user's own steps run in the same call as the built-in rules, and the "plan" says what will run, what is skipped and why. What is measured so far is one campaign from 1.8.1 to 1.20.1.2. Saves from older starting points are expected to update as well, because every game version since has only added to what a save holds, but that is a reasonable guess until a second campaign proves it in practice.

## Now: 0.4.0, the first release

The bar for the first release is that the tool does the whole job for its own founding campaign through the one public command, with nothing that a stranger could not also do (originally the process was an ad-hoc set of one-off scripts). Here's what is planned for 0.4.0, on `main`:

- `ck3update status` and `ck3update update`: one plan, built from the save's header and the game folder, that `status` prints, `--dry-run` runs in memory and `update` executes. The plan names the game it found, the version gap, every rule with its reason to run or be skipped, the reference save it will use or how to make one, and the output file.
- The game and the save found on any machine: Steam's own records and its libraries on any drive, the Documents folder wherever Windows keeps it, a save by name.
- Your own packs folder: a pack dropped there runs on every update; a pack that runs code runs only after you trust it once, and never again after its files change until you say so again.
- Rules declare what they need: the game versions they apply to, the save game they belong to, the inputs a step takes. A rule whose needs are not met is skipped and listed with the reason and the flag that would supply it. `ck3update help <rule>` says what a rule changes and what it needs.
- A record per save game, kept outside the save and keyed by the world's own seed, so a later save of the same game is updated with the same inputs and nothing retyped; `--in-place` with a backup for people who want their save replaced where it is.
- An already-updated save is re-checked: what was already applied is skipped, what newer rules would still change is run, and what cannot be judged is listed rather than guessed.
- Lint that tells the difference between what the game will reject and what the game converts by itself on load.

Left before the release:

- The output's layout and the documentation for a first-time reader: a `status` that reads cleanly on a narrow console, a README that leads from install to `status` to `update`, and the version span stated as measured versus expected.
- Faces for saves without portrait mods: when every face in the save already has the layout the game expects, the update keeps them as they are; otherwise it says plainly that the game will regenerate them. The general face translation for modded saves follows (see Next).
- Whether the new-map transplant runs by default for a save that crosses the 1.13 map rework, or stays opt-in. Today it runs when asked for.
- The release itself: a human checklist run by a tester, a 0.4.0 version, and publication to PyPI as `ck3-save-updater`.

## Next: 0.4.x

In the order they are planned:

1. **Editing a save on purpose.** The same engine with a second front door for changes a player asks for by name: a ledger of every edit so it can be reverted, a new save beside the original by default or in place with a backup. The first edit: change a character's sex, found by id or by full name, for the succession cases where a mixed-law inheritance would split the realm. Edits are never part of an update; `update` only carries what the save holds.
2. **Full coverage without the game.** The old shapes the game still converts on its own first load (schemes, contracts, activities, culture fields) converted by the tool, so a save is current when the tool says so, and a check on the game's own re-save that reports anything a future game version stops converting.
3. **Faces for modded saves.** Translation of every face by gene name from the layout the save was written in to the layout the game and the enabled portrait mods use now. The source layout of a modded save is the open problem: Workshop mods update in place, so the build the save was written with is often gone.
4. **A field-coverage check**, shipped with its baseline per game version: fields the target game writes on every character, title or dynasty that a carried entry lacks. It would have caught the missing nickname text before a player saw a garbled name.
5. **Patch day.** When the game updates, `ck3update gamediff` shows what changed between two game folders, a new pack declares the new version span, and the campaign is soaked through it. This is the case the tool was built for and the reason version spans exist.

## Later

- **Reaching back into our own libraries.** Pieces built here that the shared DazzleLib stack lacks and could take: the byte-verified atomic save writer, the one-plan pattern with its "not knowable yet" state, trust-once for user extensions, the block renderer, and game discovery when a second game tool exists.
- **Companion content.** The founding campaign's custom faith, its artifacts and its founder's lineage as a mod of their own, installed by the tool as an option with an honest label, and the campaign's end state carried into the later Paradox games through the community converters, with a small mod per game carrying what the converters cannot. These are the maintainer's own project; the tool stays general.
- **The mods.** The founding campaign's old mod set, one by one: which still work in 1.20, which need a maintained replacement, which the maintainer takes over. Tracked, not scheduled.
- **Performance.** A measured cause for the periodic stall an old large save shows in 1.20 (an alert's check running on a timer, and portrait rebuilds on a short cache) is worked around by a small mod; a proper fix, or a general performance mod, is an idea.

## What this tool will not do

- Invent an outcome. A rule carries what the save holds and reports what it cannot carry; it never writes something to make a plan happen. What the game does to every save on load is data; a change of our choosing is an edit, and edits are a separate command the player asks for.
- Run code you did not trust. A pack that runs a script or a program runs only after `ck3update trust <pack>`, and the plan shows it either way.
- Change the save you gave it, unless you ask for `--in-place`, and then only after a backup.
