# Roadmap

This file is the plan, refreshed at each release. The repository's first issue, kept pinned, mirrors it section for section with checkboxes: https://github.com/djdarcy/ck3-save-updater/issues/1. Notes and quick ideas go to the second: https://github.com/djdarcy/ck3-save-updater/issues/2. The [CHANGELOG](CHANGELOG.md) says what each version actually shipped.

## Where this comes from

The tool began on 2026-10-24 with one campaign: an Empire of Ireland saved in January 2023 by game version 1.8.1 with 34 mods, which 1.20 would not load. Within a day the save loaded. Within a week it played, with its custom faith intact, the map regions added since 1.13 populated from a reference save, and the characters' faces restored. Every crash and freeze found in play was traced and fixed in the tool. The founding campaign is still the measure of every change: the same save through the same command must give the same bytes.

The general tool grew out of that. Rules became patch files anyone can read and write. A player's own fixes run in the same command as the built-in rules. The plan says what will run, what is skipped, and why.

## Done: 0.4.0, the first release (2026-11-03)

0.4.0 is on PyPI: `pip install ck3-save-updater`. It does the whole job for the founding campaign through the public command, with nothing a stranger could not also do.

- `ck3update status` says what an update will do, and whether it can, before anything runs. `ck3update update` writes the updated save beside the original.
- The game, the save folder and the reference save are found by themselves. `ck3update reference-mod` makes the bookmark mod for a reference save on the campaign's date.
- Religion is rebuilt from the reference save. A save from before the 1.13 map rework gets the new map's regions and their people, by default.
- Faces are converted to the gene layout of the portrait mods the player loads with, for modded saves too.
- A packs folder for the player's own fixes, a record per campaign, `--in-place` with a backup, and a re-check of an already-updated save.

## Done: 0.4.x and 0.5.x (2026-11-03 to 2026-11-17, released as v0.5.0 and v0.5.39)

- **Faces** ([#40](https://github.com/djdarcy/ck3-save-updater/issues/40), closed in 0.4.29): more of each 1.8.1 face carried, and built-in gene tables, so the old portrait mods need not be installed.
- **Titles without the old game** (0.5.0): the update carries the titles of the 1.8.2 map, so a 1.8 save needs nothing more.
- **Speed** (0.4.30 to 0.5.0): about half the time on the founding campaign, the update asks before it writes, and it stops at the first failure.
- **The save editor** (0.5.1 to 0.5.17): `ck3update edit` changes one thing on purpose, with a ledger and `revert`. The built-in edits are `ironman-off`, `set-sex`, `acknowledge-child`, the queued-event tools, and `artifacts` with `give-artifact`. A player can write their own edits in a pack.
- **Carried fields and builder contracts** (0.5.18 to 0.5.23): a field baseline per game version, and a check after every update that names any field the game's own saves carry and the update left out. Every rule that builds an entry declares each field.
- **Faith edits** (0.5.24 to 0.5.28): `set-eminent-holy-sites`, `set-faith` (to a faith or a rite) and `set-doctrines`, following the rules in the game's own files.
- **Names as the game shows them** (0.5.29 to 0.5.33, and `reference-mod` in 0.5.37): accents and case never matter, and a shared name is refused with each candidate listed.
- **Fields the game determines** (0.5.34 to 0.5.38): an updated save says only what the game itself would say. A carried faith gets the doctrine groups added since its version, and a carried culture its head determination. Lint says why it leaves a field unfilled. Uncompressed saves are read, never written.

## Next: 0.6.x, patch day

The 11-17 trade update is the first game update since the tool was released. Handling it is the case the tool was built for, and one of the conditions for 1.0.0.

1. **The founding campaign's v17 golden, looked at in the game.** Accepted, it becomes the pure golden that patch day starts from.
2. **Patch day for the trade update**, in this order:
   - `ck3update gamediff` between the old and the new game folder;
   - a fresh save at the campaign's date in the new version;
   - the field baseline for the new version, and the builder contracts checked against it;
   - a new pack with its version span;
   - the founding campaign played through it.
3. **An edit recipe**, beside patch day, as it does not depend on the new game. A campaign can say "after every update, make these edits", kept in a separate block of the report, so the pure update stays the update alone.

## Then

- **Saves older than 1.8, and a save that is not ours** ([#41](https://github.com/djdarcy/ck3-save-updater/issues/41)). Every fix gets a general form, tested on a campaign other than the founding one.
- **Saving while the game runs** ([#42](https://github.com/djdarcy/ck3-save-updater/issues/42)). Saving an updated campaign while it runs can crash it. Pause before you save until this is fixed.
- **Full coverage without the game.** The old shapes the game still converts on its own first load converted by the tool, so a save is current when the tool says so. The reader for the game's own uncompressed re-saves, and the check of what the game fills on load, are now the instruments for it.
- **The rest of the speed design.** The one-pass re-check loop, `--ask each`, and showing the steps left while an update runs.
- **More edits.** `fix-house`: a matrilineal marriage's descendants take the mother's house.
- **Small fixes.** A note above `ck3update rules` saying the list is in run order. A bare `ck3update tools` that explains itself.
- **Waiting on evidence.** Some fields stay unknown until something settles them:
  - an old artifact's type, wealth, quality and modifiers, which need a rule that holds in every one of the game's own saves (a third reference save, or the artifact definitions);
  - the template of a culture made in play, which needs a 1.20 save holding a hybrid or divergent culture.

## Toward 1.0.0

A proposal. 1.0.0 would mean:

- [ ] **A second campaign proven**, from someone else's machine and mod list. Not yet.
- [ ] **More than one starting version proven** (#41). Not yet.
- [ ] **One game update handled after release** ("patch day"). Next, with the trade update.
- [x] **Faces judged right by eye** on the founding campaign (#40). Met in 0.4.29: I accepted the results (with some caveats).
- [ ] **A beta period** with players other than me (or any other maintainers), and their reports closed. Not yet.

## Later

- **Reaching back into our own libraries.** Pieces built here that the shared DazzleLib stack lacks and could take: the byte-verified atomic save writer, the one-plan pattern, trust-once for user extensions, the block renderer, game discovery, and the core shared with the Stellaris save tool.
- **Ironman saves.** The flag flip shipped as `ironman-off`. Reading a binary save waits until a reader can be shipped legally.
- **Companion content.** The founding campaign's custom faith, its artifacts and its founder's lineage as a mod of their own. The maintainer's own project, tracked and not scheduled. The tool stays general.
- **The old game, as an optional mod set** ([#43](https://github.com/djdarcy/ck3-save-updater/issues/43)), and the founding campaign's old mods one by one. Tracked, not scheduled.
- **Performance.** An old large save stalls periodically in 1.20. A small mod works around it, and a proper fix is an idea.

## What this tool will not do

- Invent an outcome. A rule carries what the save holds and reports what it cannot carry. What the game does to every save on load is data; a change of our choosing is an edit, and edits are a separate command the player asks for.
- Fill a field by guessing. A value is written only when the game itself would decide it. Otherwise the field stays unknown, and lint says so.
- Run code you did not trust. A pack that runs a script or a program runs only after `ck3update trust <pack>`, and the plan shows it either way.
- Change the save you gave it, unless you ask for `--in-place`, and then only after a backup.
