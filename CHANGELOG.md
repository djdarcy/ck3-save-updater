# Changelog

All notable changes to ck3-save-migrator are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.29] - 2026-11-06

### Added
- Old faces are read without the old game or the old portrait-mod builds. The update ships small built-in tables of the face genes of the old game (the 1.7 and 1.8 versions) and of the 2022-2023 builds of Community Flavor Pack and Ethnicities and Portraits Expanded. Each table holds names only (gene names, template names, index numbers), none of the mods' own work. `--old-game-dir` and `--old-portrait-mods` still work and win when given. On the founding campaign the update with neither gives the same 11,230 faces as with both.
- When a portrait mod the save used is installed today in a newer build, the update reads the save's faces both ways and keeps the one that fits them. A newer build reads old faces wrongly, so being installed is not enough; on the founding campaign today's builds would misread about 13,600 face values in the first 3,000 faces, and the tables misread 7. The plan's notes say which was kept, and on what counts.
- `scripts/gene_table.py` writes such a table from any build, so more can be added.

### Changed
- The plan's note on face genes the update drops counts them after the renames and merges, and names the build each came from ("4 genes the faces use were dropped: ... (from epe_1.6.0)"). It used to say 6, counting the 2 the update carries. It suggests changing the playset only when a portrait mod you have installed, but not turned on, defines one of them; otherwise no playset can bring them back, and the note says so.
- The FACES block says what stands in for a portrait mod the save lists but you do not have, and what is installed now: "cfp_3.1.5: not installed; read from the built-in table (Community Flavor Pack 3.1.11, names only); installed now: Community Flavor Pack 3.3.7 (Workshop 2220098919)".

## [0.4.28] - 2026-11-06

### Added
- A new default rule, R31, repairs a vassal with no vassal contract. Such a ruler's title answers to a liege, but he pays no taxes and raises no levies, and the current game never makes one; a save edit can leave one behind. R31 writes the missing contract with his liege, in the form his government uses. `status` names each ruler it will repair. To keep them as they are (an edit you made on purpose), give `--rules all,-R31`, or run `ck3update disable R31` once. On the founding campaign it repairs two barons.

### Changed
- `update` and `status` refuse a pack you named with `--pack` when one of its patches cannot run for a missing variable. The refusal names the variable and how to give it, and nothing is written. Before, the patch was skipped with one line in the plan and the save was written without it. A pack in your packs folder is still skipped as before.
- A pack named with `--pack` that does not apply to the save (its version span) no longer passes silently: the plan's notes say so, and the run goes on without it.

## [0.4.27] - 2026-11-06

### Changed
- The new rulers the update places follow the game's own rules more closely:
  - A landless seat that is its holder's own office goes to the ruler of the land it stands on. On the founding campaign, the seat of Constantinople goes under the player, who rules Constantinople.
  - The Byzantine noble families are no longer placed under the player. A noble family belongs inside a realm whose government keeps noble families, and the game itself removes a family title outside one. Left unplaced, their titles go vacant as most of them already are at a new game's start. They hold no land, so nothing on the map changes.
  - Holy orders, mercenaries and adventurers are never placed under anyone, as the game's rules say.
  - Where the campaign would give a new ruler a kind of liege the current game never pairs him with, he stays with his current-game liege if that liege still rules.
- Each character the update copies in now has a liege and a vassal contract that agree. Tributaries keep their contract alone, as the game writes them.
- `update` shows what it is doing while it works. A spinner names reading the save, each patch as it runs ("running R11 empty-modifiers (10 of 29)"), the lint and the write. Before, it printed nothing for minutes between the plan and the result. `--plain`, `-q`, `-v`, `NO_COLOR` and a pipe turn it off.

## [0.4.26] - 2026-11-05

### Changed
- The rulers the current game adds to the new-map regions now take a place in the realms around them. A new ruler whose capital, or most of whose counties, the new map carved from land your realm held becomes a vassal inside your realm, under whoever ruled that land. Elsewhere a new ruler keeps the place the current game gives him, under the campaign's ruler where the current game puts him under a title the campaign holds. You never gain a vassal on land your realm did not hold. On the founding campaign that is 40 rulers. Among them are the archbishops of France under the King of France, Rome and Ravenna under the Papal State, York, Split and Constantinople's noble families under the player, and the former Caspian-Pontic emperor and his seven counties under the Duke of Pecheneg. Holy orders and the rulers the current game leaves independent stay independent. Each placement is listed in the report with its reason.
- The progress spinner is in colour: the star yellow, the stage cyan, its counter bold, the seconds dim. `--plain`, `NO_COLOR` and a pipe still turn colour off.

### Fixed
- The update's report listed 95 holy sites as lost even though the new-map step gives each its barony back. They are now listed as recovered, and only sites with no home in the current game stay under "lost". On the founding campaign that is one, a custom faith's site.

## [0.4.25] - 2026-11-05

### Changed
- The lint report `update` writes beside the save (`<save>.lint.json`) now names every key the game will drop when it loads the save, with its count. Before, it named the first 25. On the founding campaign that is 2,156 references.
- Each entry of the table of renamed keys now names the game version that dropped the old key, from the game versions 1.8.2 to 1.20.1.2.
- The update's report lists the old plot fields the current game has no place for under "lost", with how many plots had each. On the founding campaign: the success chance and its owner's share on 1,334 plots, and the "finished" flag on 10.

## [0.4.24] - 2026-11-05

### Fixed
- Plots carried from an old save are written in the current game's layout. The update now does what the game did when it loaded one. It drops the old success fields, writes the target in its new form, and gives each plot the game's starting values. On the founding campaign it matches the game's own output on all 1,334 plots, apart from the order in which the game lists a plot's script variables. The game no longer logs "Unexpected token: owner_influence" once per plot when the save loads.
- A carried plot still starts near the beginning of its first phase, as the game starts it. Older versions counted progress to 10, and the current game counts each phase to between 70 and 730. Carrying progress across in proportion is planned.
- A correction to 0.4.19's note: 1,268 of the 1,334 carried plots were given a secrecy, not all of them. The others already had one, or are of a kind the game does not define.

### Changed
- Artifacts that gave +4 opinion with all vassals now give exactly +4, as +3 and +1. Before, they gave +5. These are the same two bonuses used for old +3 and +1 artifacts, with their small extras.
- The README says what the update carries across.

### Added
- Contributing guidance: what every change must keep, how to report a bug, and what a pull request must say in the author's own words, including which AI tools were used and how the change was checked. A pull request template asks the same questions, and `AGENTS.md` gives AI coding agents the project's rules.

## [0.4.23] - 2026-11-05

### Changed
- An artifact bonus at a strength the current game no longer has keeps its full value. The update adds up smaller steps of the same bonus to match it exactly, so a −7% building cost becomes −4% and −3%. Before, it dropped to the nearest step the game keeps. When no exact sum exists, it still takes the nearest step.
- On the founding campaign this keeps the Stone of Scone at −7% and the Bengali Crown at −5%.

## [0.4.22] - 2026-11-05

### Fixed
- Artifacts keep their pictures and models. The current game renamed some artifact pictures, the armour artifacts' 3D models and one coat-of-arms emblem, so items like Excalibur and the Skull Cap of Charlemagne showed no picture. The update now points them at the new names. On the founding campaign that is 470 references.

### Changed
- Artifacts that gave +2 opinion with all vassals now give +5 and −3, which adds up to +2. The current game has no +2 of its own.
## [0.4.21] - 2026-11-05

### Added
- Agents who had joined a plot in the old save keep their place. They take the plot's agent positions, strongest first. On the founding campaign that is 107 of 180 agents. The rest were in plots the current game gives no positions, or beyond the positions a plot has.
- A new page, [What doesn't carry over](docs/not-carried-over.md), lists what an old save has that the current game no longer keeps, and where to ask for it back.
- Troubleshooting now explains the crash when saving an updated campaign while the game runs, and the workaround: pause first.

### Changed
- Artifacts that gave +3 opinion with all vassals now give exactly +3, with a little prestige, instead of +5.

## [0.4.20] - 2026-11-04

### Added
- A county's "Tax Relief" from an old hold court becomes the current game's own "Tax Relief". The event that gave the old one is gone. The current one is stronger: half the tax and more opinion, where the old one also slowed development.
- On the founding campaign that is 7 counties.

## [0.4.19] - 2026-11-04

### Added
- The plots the old save was running carry on. The old game marked every scheme in a way the current game reads as frozen for good, so murders, seductions, lessons and the rest never moved. They now run again.
- Each carried scheme also gets what the current game's start-up would have given it. A scheme with a secrecy starts at the formula's base value instead of an error. Hostile schemes like murder get their empty agent positions, so agents can join.
- On the founding campaign that is 1,334 schemes, each given a secrecy, and 275 given agent positions.

## [0.4.18] - 2026-11-04

### Added
- A marriage the old save marked childless stays childless. An older game gave the rejected spouse a "Rejected From Marriage Bed" bonus. The current game marks it as a hidden relation between the two spouses instead. The update gives each living character who had the bonus that relation with each living spouse.
- A county's "Rice Fields" becomes "Agricultural Innovation". The same Iberian event gives it in the current game, with the same effect.
- On the founding campaign that is 47 characters (36 with a living spouse) and 2 counties.

### Changed
- `ck3update status` names the two houses of each house feud it will carry.

## [0.4.17] - 2026-11-04

### Added
- House feuds carry over. An older game ran each feud between two houses as a story, which the current game no longer runs. The update turns each one into the current game's own house relation at the feud level, so the two houses stay at odds until they reconcile in play.
- On the founding campaign that is 2 feuds.

## [0.4.16] - 2026-11-04

### Added
- Artifacts that gave "+opinion with all vassals" keep a bonus with all vassals. The current game dropped that bonus, so the nearest bonus it defines that does nothing else takes its place:
  - +3 and +4 become +5;
  - +1 stays +1, with two small extras.
  - The current game has no bonus at +2. Those artifacts wait on a check of how a replacement shows in game.
- On the founding campaign this covers 39 artifacts.

## [0.4.15] - 2026-11-04

### Added
- More of what the current game renamed now carries over under its new name:
  - Chu-ko-nu regiments become Shenbigong. The current game's repeating-crossbow innovation now unlocks them for the same cultures.
  - The completed Bombard innovation becomes Gunpowder, its successor in the same era.
  - The medium animal-hide artifact look becomes the large hide, which hangs in the same wall slot.
  - Artifact bonuses at a step the current game no longer has take the nearest step it keeps.
- On the founding campaign this keeps 25 regiments, the innovation for 229 cultures, 49 artifact looks and 5 artifact bonuses.

### Docs
- The note on face genes no portrait mod defines moved from the README to the troubleshooting guide.

## [0.4.14] - 2026-11-04

Developer tooling only. Nothing a player runs changes in this version.

### Fixed
- The test harness's autosave guard now also puts back an autosave the game renamed away during a test run. Before, a batch of runs could leave the user's own autosaves missing.

### Added
- Tools for diagnosing a game crash from its crash dump, and for repeating a crash test across several saves.

## [0.4.13] - 2026-11-04

### Added
- The Hawk of Quraysh modifiers keep working. The current game corrected their spelling (Quarysh became Quraysh), and an older save still used the old name, so the game dropped them on load. One character on the founding campaign keeps the bonus.

## [0.4.12] - 2026-11-04

### Changed
- `lint` no longer calls the cultures' old innovation-spread fields "converted on load".
  - The game drops them, and with them the innovation each culture was learning.
  - They are now listed as rejects that say what is lost and name the step that keeps it.
- `lint`'s warning about cultures missing from the game's list of template cultures now says what goes wrong: scripts that name the culture cannot find it.

### Docs
- The lint guide and "Differences from the game" describe the cultures' spread targets and the renamed perks, regiments and artifact bonuses.

## [0.4.11] - 2026-11-04

### Added
- Each culture keeps the innovation it was learning from a neighbour, a co-religionist or its realm.
  - Older saves name that innovation in a field the current game no longer reads, so the game forgot it on load. The progress was kept, but the culture lost track of what it was picking up.
  - The update now writes it where the current game reads it.
  - On the founding campaign that is 201 cultures, and 407 fewer errors when the save loads.

## [0.4.10] - 2026-11-04

### Added
- A new step renames perks, regiments and artifact bonuses that the current game no longer has to the ones that replaced them. Without it, the game deletes them when the save loads.
  - The Scholar perk becomes Erudite, which sits in the same place in the same tree.
  - Teutonic Knights become Order Serjeants: the holy-order heavy infantry with the nearest strength.
  - An artifact's bonus to scheme power becomes the same bonus to scheme phase duration, for the same scheme and tier.
- Each replacement was chosen by what the thing is, never by its name alone.
- A key is renamed only when neither the game nor the save's mods still define it, and its replacement is defined. Anything else is left as it is and listed in the report.
- On the founding campaign this keeps 142 characters' Scholar perk, 11 regiments and 247 artifact bonuses.
- `status` counts what the step would rename.

## [0.4.9] - 2026-11-04

Developer tooling for comparing an updated save with the game's own re-save of it. Nothing a player runs changes in this version.

### Added
- A way to have the game re-save an updated save straight after loading it, with nothing played, for comparison.
- Probes that compare culture entries, county cultures and characters' cultures across the original save, the updated save and the game's re-save.

## [0.4.8] - 2026-11-04

### Changed
- The face changes are on by default: `renames`, `merges`, `fallback` and `known-genes`. An update now carries more of each old face without any option.
- `--face-changes none` brings back 0.4.0's faces, and a list picks some of the changes.
- On the founding campaign the difference is small: spot checks in the game found the faces close to before, with the late-2022 eye genes of about 2,700 newer characters now kept.

## [0.4.7] - 2026-11-04

### Added
- `--face-changes known-genes` carries face genes that a later build of a portrait mod added to every face, without that old build.
  - The tool ships a small table of them: gene and template names only, none of the mod's own work.
  - It knows Ethnicities & Portraits Expanded's three genes from late 2022: the lower-lid size and eye-shape genes, which today's build still draws, and a hair-aging gene it no longer has.
  - A face that carries those genes keeps their values. Every other face is read as before.
  - Off by default, like the other face changes. The update's report counts the faces it read this way.

## [0.4.6] - 2026-11-03

### Documentation
- A hand-run checklist for the face changes (`tests/checklists/v0.4.5__Feature__face-changes.md`): the default left unchanged, each switch and its report, the wrong-layout warning, and a side-by-side screenshot round in the game.

## [0.4.5] - 2026-11-03

### Changed
- `status` warns that the save's old portrait mods are probably not the ones its faces were made with only when a real share of the faces disagree with them: at least 0.1% of the face templates it reads. A handful below that is still counted, with a line saying it is too few to doubt the mods. It is usually one template a single mod build added. Before, a single one raised the warning.
- The update's report gives the number of face templates read beside that count, and whether it reached the warning.

### Documentation
- The rules reference describes `--face-changes` (renames, merges, fallback) and the warning's threshold.

## [0.4.4] - 2026-11-03

### Added
- `--face-changes merges`: carries a face gene that a portrait mod folded into another gene. The first one it knows is Ethnicities & Portraits Expanded's second eye-fold gene, which today's build moved into its main eye-fold gene. The old value is carried only where the face has no eye fold of its own, so nothing the face already has is replaced.
- `--face-changes fallback`: when a portrait mod removed or renamed a face template, the face takes the closest-named template still there, instead of the gene's first template. It never lands on a template that draws nothing ("no beard", "no scar") unless the old one was one too. The update's report lists each template it moved this way.
- Both are off by default. They combine with `renames`, as in `--face-changes renames,merges,fallback`, and the choice is kept in the update's record.

## [0.4.3] - 2026-11-03

### Fixed
- The update's report no longer lists a face gene as "carried under a new name" when the portrait mods you have installed do not contain the new name. Such a gene is reported as dropped, which is what happens to it.

## [0.4.2] - 2026-11-03

### Added
- `--face-changes renames` (on `update`, `status`, `migrate` and `check`): carries a face gene that a portrait mod renamed between builds under its new name, instead of dropping the old gene and giving the new one a neutral value. The first rename it knows is Ethnicities & Portraits Expanded's head-roundness gene. Off by default, so faces come out as in 0.4.0 unless you ask for it; `--face-changes none` says so explicitly. The choice is kept in the update's record, so a re-run repeats it. The update's report lists which genes were carried under a new name.

### Changed
- The help's first lines now say the README's Quick start walks through every step, and the reference-save step reads "save as soon as it loads, before you unpause" (in `ck3update`, `reference-mod`, `status` and the docs).
- The download-statistics page's banner is the original with a transparent background, so it blends with the page.

## [0.4.1] - 2026-11-03

Developer tooling for the work on carrying more of each face (#40). Nothing a player runs changes in this version.

### Added
- A way to compare a character's face as the old game drew it with how the updated save draws it today: scripts that launch an old game build or today's game on a staged test save, put any character's face on the player's portrait, close the game afterwards, and crop the portraits side by side.
- A guard for the game's Documents folder around those runs. It backs up the settings and mod list, puts them back afterwards, never writes a save, and reports anything it could not restore.
- Probes that measure which genes of an old portrait-mod build carry over to today's: by the face shapes each gene moves, by whether each saved face's template still exists, and by fitting saved faces against candidate mod builds.

## [0.4.0] - 2026-11-03

The first release on PyPI: `pip install ck3-save-updater`, then `ck3update`. It brings an old Crusader Kings III save forward to the game version you have installed, and was measured end to end on one campaign of 34 mods, from 1.8.1 to 1.20.1.2. Everything in 0.3.x below is part of it. In short:

- `ck3update status "My Save"` says what an update will do, and whether it can, before anything runs; `ck3update update "My Save"` writes the updated save beside yours and never changes the one you give it (unless you ask for `--in-place`, which keeps the original as `<name>.bak.ck3`).
- It finds the game, your save folder and the reference save by itself; `ck3update reference-mod` makes the bookmark mod for a reference save on your campaign's date. The README's Quick start walks through it, the game's part included.
- Religion is rebuilt from the reference; a save from before the 1.13 map rework gets the new map's regions and their people; faces are carried into the gene layout of the portrait mods you play with.
- Your own fixes go in a packs folder; `ck3update -h` lists every command by what it is for, and `ck3update help <rule>` explains each rule.

The built-in rules cover saves from 1.8 on; an older save is refused with the gap named.

### Added
- Download and install tracking ([ghtraf](https://github.com/djdarcy/github-traffic-tracker)): a daily workflow keeps the Installs badge and the [stats page](https://djdarcy.github.io/ck3-save-updater/stats/) current.

## [0.3.30] - 2026-11-03

### Fixed
- `update --in-place` names the lint report by the file that exists (`<name>.lint.json`), not by the temporary name the report had for a moment before the swap.

### Changed
- The README's Quick start says what its commands write (a small mod in the game's mod folder, a new file beside your save) instead of "every command is safe to run"; the reference bookmark is turned on with no other mod that changes bookmarks; "Before you start" lists four things, and its `reference-mod` example no longer passes the `--out` it does not need.
- [The reference save](docs/reference-save.md): `status` and `update` find the reference by themselves; a reference named on another date is refused for the new-map steps; `--out` must name a folder that exists.

## [0.3.29] - 2026-11-03

### Added
- Faces (R19, dna-layout, on by default): every face (`dna=`) is rewritten from the gene layout it was written in to the layout you will load with, gene by gene and template by template by name, and `portraits_version` is set to the target's, so the game keeps the faces instead of making up new ones. The source is the save's own layout (its game's genes, from `--old-game-dir` when given, plus the portrait mods it lists), or the reference save's for characters the transplant adds; the target is the installed game's genes plus the portrait mods the launcher enables (`dlc_load.json`), or `--portrait-mods`. `status` shows both in a new FACES block; the report lists every character under its outcome. `--no-dna` turns it off. An unmodded save needs it too: 1.20 put `no_eyes` and `no_teeth` first in their genes' template lists, so a 1.8 face carried as it is would load without eyes or teeth, and without an error.
- `--old-portrait-mods <id-or-folder>,...` (migrate, status, update, check): the portrait mods the save was written with, for R19's source layout, when the installed builds have updated or gone; an entry that is neither an installed mod nor a folder is refused. The record keeps it for the campaign's next update. The plan names every source mod and where it came from, counts the template indexes the source layout does not define (the sign it is not the save's), and says when the target layout drops genes the faces use.

### Changed
- `--portraits-version` is gone from `migrate`, `status`, `update` and `check`: R19 sets the target's portraits_version, and R7 no longer touches it. A record that stores one still reads; the plan says once that it is no longer used.
- lint's "Unexpected DNA string length" expects the length of the layout you load with (the game's genes plus your portrait mods), not vanilla's.

## [0.3.28] - 2026-11-03

### Changed
- The sample pack (`_example-pack` in your packs folder) now changes the name the load screen shows for the save, to "Edited with ck3update", with `set` on a key every save has, so you can see a pack of your own at work. It used to add a `migrated_by` key the game does not know, which the game reports as an error when the save loads. A packs folder made by an earlier version keeps its old sample: delete `_example-pack` and run any command to get the new one.
- The insert example in [Writing a patch](docs/writing-a-patch.md) no longer uses an unknown key, and the guide says to insert only keys the game itself writes.

### Added
- A test that no shipped rule and no sample patch writes a key the game does not define, checked against the keys of a save the game wrote itself.

## [0.3.27] - 2026-11-02

### Changed
- The new-map steps are on by default (`transplant = "auto"`): a save from before the 1.13 map rework gets the regions the new map added whenever a reference save is found, with no `--transplant` flag; a newer save is untouched. `--transplant off` (or `transplant = "off"` in the settings file) leaves them out. The Quick start and the docs drop the flag.

### Added
- A reference save named with `--reference` (or `CK3_REFERENCE_SAVE`) on a date other than the save's own is refused when the new-map steps would run, since they copy the new regions' rulers and families as the reference has them: the plan says both dates and how to make one on the right date. The reference the tool finds by itself is already on the save's date; a reference used only for religion may be from any date.

## [0.3.26] - 2026-11-02

### Added
- A Quick start in the README: install, make the reference save (the command, then each step in the game's launcher and menu), `status`, `update`, and loading the result.

### Changed
- `ck3update` alone, and the top of `ck3update -h`, give the three steps in order: the reference save's bookmark mod (and what to do in the game), `status`, `update`, pointing at the README's Quick start for the rest.
- `ck3update reference-mod` writes into the game's own mod folder when `--out` is not given (found the way the save folder is, OneDrive included). Its closing lines name the mod as the launcher lists it, and say that `status` and `update` find the new save by themselves.
- [The reference save](docs/reference-save.md) walks through `status` and `update` instead of `migrate`.

## [0.3.25] - 2026-11-02

### Added
- `ck3update -h` says where to start: three lines (`status`, `status "My Save"`, `update "My Save"`), then every command once, grouped by what you want to do (updating a save, when something looks wrong, your own packs, setup, advanced), instead of one flat list of twenty.
- `ck3update` with nothing after it prints the same "start here" lines and how to see every command, instead of an error.
- `ck3update -V`, the short form of `--version`.
- The release checklist (`tests/checklists/v0.4.0__Epic__general-updater.md`): from `pip install` to an updated save, on copies, for a person to run before 0.4.0; and the first sweep's results (`tests/checklists/results/`).

### Changed
- `ck3update <command> -h` opens with a line saying what the command does.

## [0.3.24] - 2026-11-02

### Fixed
- An `--old-game-dir` that is not a folder, or not a game's `game` folder, is refused at once with how to fix it. Before, a mistyped path was taken as an old map with no titles: the update ran on, and two baronies ended up with no county above them (a lint error in the output).

## [0.3.23] - 2026-11-02

### Changed
- The block-index cache is on by default: a second `status` or `update` on the same unchanged save skips rebuilding the index. Only the newest 2 saves' indexes are kept (about 140 MB each for a large save), none longer than a day; the plan's DETECTORS block says when it wrote or read one and where; `[cache] index = false` turns it off.

## [0.3.22] - 2026-11-02

### Added
- An optional cache of each save's block index: with `[cache] index = true` in the settings file, the index the `**` patches search with is kept in a temp folder the tool names, so a second `status` or `update` on the same unchanged save loads it (0.2 s) instead of building it again (about 8 s on a large save). Off by default. Entries older than a day are removed when a new one is written; `ck3update cache where` shows the folder, `ck3update cache clear` empties it. An entry is used only for the exact same bytes. See [Configuration](docs/config.md).
- A glossary (`docs/glossary.md`): every word the tool uses that a player may not know (the reference save, the transplant, packs and patches, the plan and its verdicts, detectors, the record, lint), and every header `status` prints, each with where you meet it.

### Changed
- A save one hotfix behind the game is ALREADY CURRENT "on the game's version line (1.20)", no longer said to be "at the game's version".
- Verbs agree with their lists: "needs R14, R16, which are skipped" ("which is skipped" for one), and "name them in --rules" for several rules turned off.
- RECORD's pre-filled inputs: one row each, a long path or a list on its own lines under the value column, and the record they came from named once at the end.
- R23's detector counts only the nicknames R23 can write a text for (from the game and the save's listed mods). One whose text no listed mod has is reported apart (`not fixable: 1 nickname whose text no listed mod has`, and in the notes); a save with only such nicknames is ALREADY CURRENT. One nickname reads "1 nickname without text".
- A run patch whose `done_command` `status` runs says so on its row ("runs `<command>` to check").
- `ck3update help <patch id>` for a patch whose pack is not installed says "no pack found holds patch <id>" and points at `ck3update packs`.
- The README now leads a first-time player from `pip install` through what to have ready, `ck3update status` and `ck3update update`, to what to do when a plan is refused, and says plainly what has been measured (one 34-mod campaign from 1.8.1 to 1.20.1.2) and what is only expected. "Updating a save" follows the same order, with the step-by-step `inspect` / `check` / `migrate` flow kept at its end.
- The README's badges: the PyPI version, release date, downloads, CI, Python, licence, discussions and platforms.
- The package's licence metadata is the current form (`License-Expression: GPL-3.0-or-later`, with the licence file included), which PyPI shows on the project page.
- Platform support says what CI does on Linux: it builds the package there; the test suite runs on Windows.

## [0.3.21] - 2026-11-02

### Changed
- `status` and `update` are faster on large saves: the rules that search the whole save for what they fix (R5, R11, and any pack patch whose path uses `**`) find where each match sits from an index of every block, built once per save, instead of walking down from the top for each search. On the founding 1.8.1 save (222 MB), the checks `status` runs before anything else went from 215 s to 98 s, and a full `update` from 678 s to 542 s, with the same output byte for byte. The patch path syntax is unchanged.

## [0.3.20] - 2026-11-02

### Changed
- `status`, `update` and `check` read the save once for checks that several rules share: the new-map rules (R14, R16, R17) share one check, the religion rules (R8, R9, R10, R12) another, the dead-title rules (R6, R15) a third. Each check's answer is kept only for the save in memory it was made from, so a dry run and a real update never share an answer.

## [0.3.19] - 2026-11-01

### Added
- `status` and `update` print their plan as blocks: a header in capitals (`SAVE`, `GAME`, `REFERENCE`, ...), then one fact per line as `field: value`, laid out for the terminal's width (between 60 and 120 characters). A value too long for the line continues under its own column, never under a header; the patches table keeps its columns, and a reason too long for its row goes on the line below it.
- A `[display]` table in the settings file chooses the layout: `gap` (the spaces after a header, default 2), `spacing` (`"compact"`, no blank lines, the default; or `"blank"`) and `align` (`"flow"`, the default: each block as tight as the gap allows, a one-line block keeping the column of a wider block above it; `"global"`: every colon in one column; `"blocks"`: every header padded to the longest). A value that is not valid stops the command, naming the file and the setting.
- [Configuration](docs/config.md): every setting in the settings file, `[display]` with the three layouts side by side, and the environment variables.
- While `status` or `update` reads and judges a save, a spinner on the terminal names the stage running (`reading the whole save`, then `checking R23 nickname-text (11 of 19)`) and the seconds so far, and is erased when the plan prints. It is drawn only on a terminal, and never with `--plain`, `-q` or `NO_COLOR`.
- `--plain` on `status` and `update`: no colour and no spinner, for pasting the output.
- The verdict line ends with the time the command took; the `DETECTORS` block shows the read of the save (its size and seconds) apart from the judging (the steps and their seconds, and the three slowest).
- The `SAVE` block shows the save's seed (its `random_seed`), which names its save game: the value a pack's `campaign` scope uses.

### Changed
- A plan that is already refused (several saves could be the reference, a gap no pack covers, no game found) does not read and judge the whole save: the refusal is the answer, in about a second instead of minutes on a large save. `DETECTORS` says they were not run and why. `status` and `update` still make the same plan.
- `status` without a save prints the game and the save folder as blocks too.
- The repository is now https://github.com/djdarcy/ck3-save-updater: the package's URLs (PyPI's links), the README's badges and links, and the changelog's compare links name it (the old URL redirects). The config and cache folders, the `ck3-save-migrator` command alias and the `ck3_save_migrator` package keep their names.
- The roadmap (`ROADMAP.md`) is the plan in prose: where the tool comes from, what 0.4.0 holds and what is left before it, what comes next in order, and what the tool will not do.

### Fixed
- `ck3update disable`, `enable`, `trust` and `untrust` keep the `[display]` table when they rewrite the settings file (a table they do not know is still not kept; written down as a known gap).

## [0.3.18] - 2026-11-01

### Added
- Detectors: `check`, `status` and `update` judge each built-in rule needed (with a count of what it fixes) or done, read only, instead of "unknown": R2, R21 and R23 run their own matcher without editing, and the others use the lint check that sees what they fix. The plan reads the whole save once for them and says how long it took (`--no-detect` skips it). A save already on the game's version line is re-checked: a rule its record shows applied, or whose detector finds nothing, is skipped; one whose detector finds something runs (READY, and `update` writes a new save); one that cannot be judged, and the transplant, run only when `--rules` names them. The re-check is skipped when the record says this tool version updated the save.
- lint: a mercenary company whose title key is `x_mc_<another company's id>` is a warning (a candidate check; no rule behind it).
- A record per save game: after each successful `update`, a row (inputs, outputs and their hashes, patches, game version, the inputs used) is added to `games/<random_seed>.toml` beside the config file. `status` and `update` show it and pre-fill any input not given from its latest row; a recorded folder that is gone is not used. `--no-record` turns it off. `update --in-place` replaces the save, keeping the original as `<name>.bak.ck3`.
- `update` and `status` decide everything before anything runs. A pack can be for one save game only (`campaign` in `[applies]`). A save one hotfix behind the game is already current. The reference save is looked for only when a patch that will run needs one. A run patch's unmet `needs` and its done check (`done`, or `done_command`) skip it, saying why. `--var <patch id>.<name>` gives a variable to one patch. `ck3update help <id>` explains a rule, patch or pack. `--transplant auto` (or `transplant = "auto"` in the config) selects the new-map rules when a save crosses the 1.13 map rework and a reference is present; it is off by default.
- `ck3update setup` (run it as `python -m ck3_save_migrator setup` when `ck3update` is "not recognized"): says where pip put the command and, on Windows, offers to add that folder to your user PATH, through dazzlecmd-lib's self-setup (now a dependency, loaded by this command only). `--dry-run` prints what it would do and changes nothing in PATH or the registry (on some terminals it writes small helper scripts to your temp folder); `--yes` does not ask.

### Changed
- lint: the six `Unexpected token` families the game converts on load (schemes `owner_influence` and `ready`, culture_manager `exposure_type` and `exposure_marker`, landed_titles `localization_key` and `renamed`) are info, not rejects. "title names only inside title_name_data" also fires on a title with inline names and no `title_name_data`.
- A bare `--var name=value` (or a bare key in a `--vars` file) reaches every selected patch of one pack that needs it; it is refused only when patches of different packs need it (an earlier change in this release refused any two patches that needed the same name).
- The config file and the JSON reports (the `--report`, the lint file beside each output, `lint --json`, `gamediff --json`) are written atomically, through dazzle-filekit: a crash, a full disk or a kill mid-write leaves the old file whole instead of a torn one. Their bytes are unchanged.
- `ck3update tools run` runs a script directly, `[python, <script>] + args`, the same way a run patch's `tool =` does: nothing extra to install (the `[tools]` extra is gone), no cache folder written (`--cache-dir` and `CK3SM_TOOLS_CACHE` are gone), and a scripts folder holding an `__init__.py` no longer breaks it.

### Fixed
- `status` on an up-to-date save no longer refuses because several saves in the save folder could be the reference: the reference is only looked for when something that will run needs it.
- `--show`'s help lists every output channel (`gamediff` was missing).

## [0.3.17] - 2026-10-31

### Added
- `ck3update update "<save>"`: one command that brings a save to the installed game's version. It works out a plan first and runs exactly that plan: it finds the game, reads the save's version and date, chooses the patch packs whose declared version span covers the gap, finds a reference save, and writes `<name>__updated__<game version>.ck3` beside the save (never over it; an existing output needs `--force`). `ck3update status "<save>"` prints the same plan and writes nothing; `update --dry-run` runs every patch in memory and prints the plan with each patch's counts. A save already at the game's version is reported "already current". A version gap that no pack covers is named and refused. Exit codes are `migrate`'s. `migrate` is unchanged and stays the lower-level command.
- The plan picks the reference save from the save folder by itself: a save written by the game's version on the campaign's date, never one that descends from the save being updated (they share the campaign's random seed) and never this tool's own output. When several could be the reference, it refuses and lists them, so you choose one with `--reference`.
- Patch packs can declare which save and game versions they apply to (`[applies]` in `pack.toml`) and where their patches run (`after = "<patch id>"`). See `docs/writing-a-patch.md`.
- Your own packs folder: every pack in it runs on every update. A pack that runs code (a script or a program) runs only after you trust it once with `ck3update trust <pack>`, and stops again if any of its files change. `ck3update packs` lists them; extra folders can be added in the config.
- Finding the game and the save on any machine: the Steam library is read from Steam's own records, the game's version from its launcher files, and a save can be named by its file name in the game's save folder.
- `ck3update reference-mod`: writes a small bookmark mod that starts a new game at your campaign's date, so you can make the reference save the update needs. It picks the ruler from the game's own history files.
- A new default rule writes the text of each character's nickname, which 1.20 expects beside the nickname itself; without it, nicknames show garbled in game.
- Colour in the terminal: the plan opens with its verdict (READY, ALREADY CURRENT or REFUSED), section labels are bold, paths cyan, patches that run green, skips you can fix yellow, refusals red, notes grey. Colour is on in a terminal and off when output is piped or when `NO_COLOR` is set; `CK3UPDATE_COLOR=never` or `=always` overrides it. The colour helpers are a copy of dazzlecmd-lib's, whose 0.10.35a0 release adds the same blue.
- The README as a tutorial, with topic pages under `docs/` (rules, options, reports, lint, troubleshooting, the new-map regions, the reference save).
- A diagnostic that thins a save's population for testing (`docs/thin-population.md`).

### Changed
- A refusal is printed once, at the end of the plan, with the fix on the next line, and a list of files names their folder once.

### Fixed
- savediff no longer reports false alarms for 1.20's dead characters written twice or for the 64-bit "none" id.

## [0.3.16] - 2026-10-30

### Changed
- Renamed for PyPI: the project installs as `ck3-save-updater` (`pip install ck3-save-updater`) and its command is `ck3update`. The old command, `ck3-save-migrator`, still works as a second name for now. The settings folder keeps its old name (`%APPDATA%\ck3-save-migrator`, `~/.config/ck3-save-migrator`), so an existing config keeps working. The Python package inside is still `ck3_save_migrator`, and the GitHub repository keeps its name.
- The README and `docs/updating-a-save.md` describe the early release: what is proven (a 1.8.1 campaign with 34 mods loads and plays in 1.20.1.2, and the update is reproducible, comparing saves by content), and what is not handled yet.

### Added
- Performance notes for large updated saves: two vanilla top-bar alerts that each cost about half a second per check, and portraits recalculated every 30 frames, with the workarounds for both. A packaged performance mod is planned.
- A short list of mods known to misbehave in 1.20 (Better Barbershop).
- savediff's reference graph, a diagnostic library inside the package (not used when updating a save): which record points at which by id, with checks for broken references, liege cycles, duplicate ids, a primary title outranked by another title of the same ruler, and title keys that break a naming rule, plus a way to compare one record's links across two saves.
- Diagnostic scripts used to find the causes of the stalls in large updated saves (per-thread CPU timing, stack sampling inside a stall, reading which top-bar alert the game is checking) and to compare which fields a save's characters and other records carry against a save the game itself wrote.

## [0.3.15] - 2026-10-28

### Added
- `--rules` can leave a rule out: `--rules all,-R21`, or `--rules -R21` for every default rule but R21. An unknown id is refused, and so is leaving out a rule another selected rule needs.
- `ck3-save-migrator gamediff <old game> <new game> [--save <save>] [--json <file>]`: what a game update added, removed and changed, definition by definition, and with `--save` which of the removed or changed ones your save uses. Reads only. See `docs/gamediff.md`.
- `ck3-save-migrator soak <save>`: **starts the game**, loads the save, lets it run, closes it through Exit to Desktop, and says whether it exited cleanly or crashed. Your autosaves and mod list are backed up first and put back afterwards, and only one soak runs at a time. See `docs/soak.md`.

## [0.3.14] - 2026-10-28

### Added
- `docs/updating-a-save.md`: the everyday flow on one page, from looking at a save and checking what it needs, through migrating and linting, to loading it, plus what to do when the game updates again and what each exit code means. Linked from the README.

## [0.3.13] - 2026-10-28

### Added
- `ck3-save-migrator check <save>`: what each rule would do to a save, without writing anything: `needed` (with how many edits), `done`, `unknown` (rules written as code, which only running can tell), or `fails` (a patch whose expectation is not met, named with its path; exit code 5).
- `ck3-save-migrator disable <id>` / `enable <id>` / `disabled`: turn a rule off for `--rules all`, kept in a small config file the tool owns (`%APPDATA%\ck3-save-migrator\config.toml` on Windows, `~/.config/ck3-save-migrator/config.toml` elsewhere; `CK3SM_CONFIG` points it elsewhere). A rule named explicitly in `--rules` still runs.

## [0.3.12] - 2026-10-28

### Changed
- The tool's rules now come from the shipped pack of patch files. Five of them (dropping the old "converging" opinion blocks, blank game-rule entries, empty keys, empty modifiers, and setting the version) are plain patch files; the Python code that did the same work is gone. Nothing a player sees changes: the same 19 rules in the same order, and on the founding campaign the migrated save is byte-for-byte the one 0.3.11 wrote.

## [0.3.11] - 2026-10-28

### Added
- Rules as patch files. A patch is a folder with a `patch.toml`. It either edits the save by a path through its structure (delete a key, a value or an entry; rename; set; insert; with simple conditions and `@@variable@@` values filled in at run time), names a Python function, or, for hard cases, runs a separate program over the save. The 19 current rules ship as a pack: five as plain patch files, the other fourteen pointing at their unchanged code. The migration still uses the Python rule list in this version; switching to the pack waits on a proof on a real save.
- `migrate --pack <folder>` (repeatable) applies your own packs after the selected rules, with `--var name=value` and `--vars <file.toml>` for their values. A pack loaded from a folder may not run code (a script or a program) unless you pass `--allow-run`, because that code runs with your permissions.
- A patch that fails (its `expect` not met, or its program exiting with an error) is reported by name and stops the migration: nothing is written, exit code 5.
- `ck3-save-migrator tools list | run | path`: an optional add-on that lists and runs a folder of standalone scripts exactly as they are, each as its own process. Install it with `pip install "ck3-save-migrator[tools]"`; nothing else in the tool needs it.
- Guides: `docs/writing-a-patch.md` and `docs/tools.md`.

## [0.3.10] - 2026-10-28

### Fixed
- A campaign migrated with the new-map transplant crashed every time the player chose Exit to Desktop, with or without mods (the game's own save of the same date did not). The new game reuses some history ids for different people than the old game did: one id belongs to a man born in 923 in 1.20 and to a man born in 725, dead in 779, in 1.8.1. The migration matched people by that id alone, so a vassal contract copied from the new game named the long-dead man as its vassal, and the game crashed tearing that contract down on exit. Two people now count as one only if their lives can be one life: never when the campaign's person died before the other was born, and not when their births are more than 60 years apart under different first names. Otherwise the new game's person is brought in as their own character. The founding campaign has 13 such ids; the migration report lists each one with its reason.

### Added
- `lint` reports as an error any vassal contract whose liege or vassal is dead (the state that crashed the game on exit; the game's own saves have none), and warns about a living courtier whose employer is dead.

## [0.3.9] - 2026-10-27

### Fixed
- When the migration gave a campaign character back the new titles for land 1.20 redrew, the old title was removed but references to it stayed: character variables that remembered a title (the founding campaign has 113, written by the Biography mod: a character's titles and primary title) pointed at a title that no longer existed. They now name the new title that character holds. The report lists them, per old title. References to titles that still exist are never touched.

## [0.3.8] - 2026-10-27

### Fixed
- `lint --game-dir` and the lint that `migrate` runs on its output never ran the check for things left on impassable land, added in 0.3.7: the game folder was not passed through. The 1.8.1 founding campaign now shows its 10 such problems, and its migrated output none.

### Added
- `lint` warns about stored script scopes (the targets of events, schemes, stories, council tasks and variables) that name a character, title, province, artifact or faith the save does not have, and, with `--game-dir`, reports as an error any such scope aimed at a province the new map made impassable. Old saves carry some dangling scopes the game tolerates (the founding campaign: about 500); a new game's save has none. The game's "none" value is not counted.

## [0.3.7] - 2026-10-27

### Fixed
- The migrated save lacked 323 titles a new 1.20 game has at the same date, all of them empty and waiting to be created or earned: the Roman and Indian hegemonies, empires such as Carthage, and the monastic and military orders. The game's own scripts name most of them (restoring the Roman Empire, faction demands, clothing), so those features could not work, and portrait mods logged errors. The new-map transplant now carries every title the new game has, empty as the new game has it; nobody is given a title. The one title the game creates by itself in a migrated campaign (the Knights Hospitaller) is left to it.
- Titles a campaign character held where 1.20 split or redrew the land (on the old eastern edge: Xia, the Ordos, Gansu, Ustyurt) used to go to the new game's rulers, leaving several campaign rulers with nothing. Their holder now keeps the new titles for that land, with the vassals under them; the new game's ruler who loses everything joins his court.
- Handing those titles back left some realms out of step with their vassal contracts: a ruler given his county back with no liege while still bound to one, a new-game ruler's counts left under a duchy he no longer held, and a baron bound to his old count while his barony sat in another man's county. Each now agrees: the ruler takes his contract's liege, the counts take the liege above the lost duchy, and the baron's contract moves to his county's holder.

- The migrated campaign crashed on 1 January 989 once the held titles went back to their holders. 1.20's new map made some 1.8.1 land impassable mountains (in the Ordos), but the save kept what stood there: a castle and a tribal holding with their soldiers, a siege of the castle, an army on it, and two council tasks aimed at it. With its ruler landed again, the game appointed a councillor to one of those tasks at New Year, filed it under the province, and crashed. A new rule (R22, on by default, needs `--game-dir`) clears them: the holding becomes the empty one a new game has, its soldiers and the siege go, the army steps back to where it came from, and the council tasks aim at a province of their ruler's own.

### Added
- `lint` with `--game-dir`: nothing may stand on, or be aimed at, a province the new map made impassable (an error).
- `lint` with `--reference`: every title the reference (a new game at the campaign's date) has must exist in the save. Inside `migrate`, the check runs when the new-map transplant ran.
- `lint` checks that a count or higher under a liege has a vassal contract with that liege (an error), and warns when a baron's contract names someone other than his county's holder, or a domain lists a title someone else holds.
- `lint` checks the save's metadata: every entry has a key (an error; a bare block there makes the game refuse the save).

## [0.3.6] - 2026-10-27

### Fixed
- The New Year crash: the new-map transplant now registers every mercenary company title it carries in the save's runtime title list. The game rejected the unregistered ones at load, destroyed most of them within a year, and then crashed on a company left pointing at a destroyed title. The founding save played through two New Years without it.
- A migrated save could stop the game at a random date (20 March 989 in one run, after 1 January 990 in another) while its memory grew past 100 GB. The 1.8.1 campaign kept six AI war plans that had been created and never run, with a supply limit of 0; 1.20 loads them as they are, and when armies are assigned to one, the AI splits the army stack to fit a supply limit of 0, forever. A new rule (R20) removes those never-run war coordinators, the war plans that name them, and their entries in the characters' AI strategies; the game builds fresh ones for those wars. The founding save now plays past 1003.
- A new rule (R21) drops the recorded liege of dead characters whose liege chain loops (the 1.8.1 campaign had one: two Abbasid caliphs recorded as each other's liege). A ruler who died independent, recorded as his own liege, is left as the game writes him.

### Added
- `lint`: a title's liege chain must end (a title that is its own liege, or a chain that loops, is an error; the game's walk up such a chain never ends).
- `lint`: army checks: an army's map unit, regiments, soldier pools, commander, and the unit's owner must exist and point back; an army with no soldiers is a warning.
- `lint`: AI war state checks: every AI war coordinator must have a war stance and a supply limit above 0, and every war plan and every plan an AI strategy lists must exist (a strategy listing a missing plan crashes the load).

## [0.3.5] - 2026-10-27

### Fixed
- A migrated save could freeze the game a few days into play. When the new-map transplant gave a redrawn county to a baron of the player's family, the county was listed after his barony, so the barony stayed his primary title; when the game later made him independent it set the county as its own liege, and a routine that looks up a title's kingdom then looped forever. The county now becomes his primary title. Found by tracing the frozen game in a debugger; the founding save froze on 8 November 987 and now plays through it.

### Added
- `lint`: a ruler's primary title (the first title of his domain) must be his highest title; any other order is an error.
- `lint`: mercenary company checks: every runtime (`x_`) title must be registered in the save's runtime title list, which the game requires (an unregistered one is rejected at load and destroyed in play); a company's title must exist (a company left pointing at a destroyed title crashes the game's yearly pass, so this check is worth running on the game's own autosaves too); a company title that names its company must name the right one.
- `savediff`, a save-aware comparison library inside the package (`ck3_save_migrator/_vendor/savediff/`), not yet used by any command: it reads a text save's sections, counts each section's entries, reads the keys entries carry, and translates ids between saves. Standard library only, kept liftable into its own package, with tests that it gives the same results as the probe it was lifted from.
- A hand-run checklist for the coming 0.4.0 (`tests/checklists/v0.4.0__Epic__playable-campaign.md`), including the real-campaign steps.

### Known
- The new-map transplant carries mercenary companies without registering their titles in the save's runtime title list; the game then destroys most of those titles within a year and crashes. The fix is proven on a copy of the founding save and goes into the next version.

## [0.3.4] - 2026-10-26

### Changed
- `migrate save.ck3` with no `--rules` now runs the full migration (it used to write an unchanged copy that looked migrated). `--rules all,R14,R15,R16` adds the new-map transplant to it. An empty `--rules` is refused.
- A rule chosen without the rules it depends on is refused before anything is read, and the message names what is missing (for example, the transplant rules need the religion rules, so that copied people's faiths point at something).
- When no rule changes anything (the save is already migrated, or nothing matched), nothing is written and the tool says so; `--force` does not change that. Migrating a migrated save is therefore safe.
- `--bump-version` is deprecated and does nothing: the version bump is part of the default rules.

### Fixed
- `--force` never overwrites the input save, also when the output path is a second name for it (a hard link, a junction or a mapped drive).
- Migrating an already-migrated save with the map rules (R15) used to undo part of the first migration: it renamed two baronies back and removed baronies that had already moved to their 1.20 place. A save that is already at the current version now leaves R15 nothing to do.
- Migrating an already migrated save no longer adds the new regions' situations a second time (China's dynastic cycle and the others, with their regions and groups).
- Titles left without a de jure parent, because the title above them in 1.8.1 is gone, get the parent 1.20's map gives them (22 on the founding campaign).
- `lint` reports characters carrying 1.20 rite numbers in a save that has no rites database, instead of skipping the religion checks there.

## [0.3.3] - 2026-10-26

### Fixed
- Where 1.20 drew a new county around baronies your campaign held, that county now goes to your campaign rather than staying with the ruler 1.20's history gave it. A baron of the player's family (the player's house or dynasty, or a spouse's) is promoted to count of it; otherwise the count who held those baronies in your campaign takes the new county, and his barons stay his vassals. Barons whom 1.20's history put in the county keep their baronies, as vassals of the new count.
- The ruler who loses the county keeps the rest of his lands; one left with nothing joins the new count's court.
- A baron whose barony is the capital of the new county, when someone else becomes its count, gives the barony to the new count and joins his court (a county's holder always holds its capital, and none of these counties has a built barony free). Each such case is listed in the report.
- On the founding campaign, the game's own load now moves only the baronies the report names (6, down from 29).

### Added
- The transplant's report has a row for every barony it settles: the old county and its count, the new county, who held it and who holds it now, and what happened to the baron.

## [0.3.2] - 2026-10-26

### Fixed
- 1.20 redrew county borders, so 194 of the founding campaign's baronies now belong to a different county than in 1.8.1. The game used to re-seat each one under its new county on load and give it to that county's holder, or to no one. A moved barony now belongs to its 1.20 county and its baron keeps it, as a vassal of the new county's holder.
- What the game's own rules will not allow is now listed in the report, with the reason, instead of disappearing on load: a barony whose count also holds land outside its new county (one person cannot have two lieges), a barony that is the capital of its new county (a county's holder always holds its capital), and a new barony of a copied ruler inside one of your counties, which goes to your count. On the founding campaign, the baronies that still change hands on load are exactly the ones the report lists.
- New-map baronies on provinces the old map had left empty used to lose their holders on load; they now arrive with their 1.20 holding, buildings and garrison. Provinces of your own that your campaign never built stay as they were and are counted in the report.
- A previous release note said the campaign's mercenary leaders had no government; that was a measuring error, and they do.

### Added
- The transplant's report names every barony it re-parents or leaves to the game, and counts the empty provinces it fills.

## [0.3.1] - 2026-10-26

### Fixed
- A named history id (`han_1176=5552`) was read as the number inside it, so 2,460 of the reference's history ids were lost or overwritten and 583 character matches the new-map transplant should have made were missed. History ids are now read whole.
- Every county the transplant brings in now gets its county record (culture, faith or rite, development), the record the game reads for epidemics, buildings and tournaments. Without it a migrated save filled the game's error log with "culture trigger [Failed context switch]" within a minute of play. The count now equals a fresh 1.20 game's. A county renamed by the map matching keeps its record under the new name; a removed county's record is dropped.
- `lint` reports a held county with no county record.
- `-v` and `-q` count the same whether they come before or after the command.
- A copied ruler's men-at-arms come with them (433 regiments on the founding campaign), and the new regions get the mercenary companies a fresh 1.20 game has (167, with their titles and regiments). A copied title whose runtime name the campaign already uses is renumbered so no name points at two titles.
- The copied cultures, history dynasties and history houses are added to the game's start-of-game lists, and the copied coats of arms keep their names; a name the campaign already has keeps the campaign's coat.
- `lint` warns when a copied culture is missing from the game's list of cultures.
- The version the tool reports is now 0.3.1; the first 0.3.1 tag pointed at a tree that still said 0.3.0.

### Added
- The new map regions, opt-in and still in progress: `--rules R14,R16` brings the lands, provinces and people that 1.20 added after your save's version (East and Southeast Asia, Tibet, Japan, ...) in from a save written by 1.20 at your campaign's date (`--reference`). R14 takes the titles and provinces your save has never had; R16 takes their rulers, courts and close families, with their houses, cultures and the objects they own; a write step (R17) runs after them by itself. Without them, 1.20 leaves those titles unheld and hands them to the player. Not yet part of `--rules all`.
- Every object copied in gets a new number that cannot clash with anything in your save, while everything it points at keeps pointing at the right thing. The game numbers its objects by slot, and the copied ones take free slots above your save's own. Where your save already has the same thing (a title, a culture, a dynasty, a historical character), the copy points at yours instead of bringing a second one. Links to things that are not brought along are removed rather than left pointing at nothing.
- Your campaign's own titles keep their structure. A new title is added under an existing one where 1.20's map puts it there, and nothing of your realm is given to a copied ruler.
- `lint` reports two objects of the same kind sharing a number, which the game cannot load.
- Tried on the founding 1.8.1 campaign: one copied kingdom loads and plays two months with no new kind of error and no new object taking a copied object's place; the same copy without the renumbering crashes the game on load, as it should; the whole new map (about 5,700 titles, 3,600 provinces and 6,700 people) reaches the map.
- Titles your save has that 1.20 removed or moved (R15, with `--old-game-dir`, the game folder of the version your save was made with): each is matched to what 1.20 calls the same land. Where the match is exact, your title takes the 1.20 name and stays with its holder; where 1.20 split or redrew the land, the 1.20 titles and their rulers take it, and every case is listed in the report with what happened to it. Ten baronies that 1.20 moved to another province keep their place on the map and take the name 1.20 gives that place.
- The new regions now arrive complete: guests at their courts, the relations and opinions among their people, their queued events, every culture 1.20 added, and China's situations (the dynastic cycle). A ruler of 1.20's history whose land your campaign already holds comes in without land, at the court of the one who holds it.
- Holy sites of the new regions (Angkor, Borobudur, Samarkand, ...) are attached to their places again once those places exist.
- The 1.20 monastic orders that hold lands in the old world are added as the new version has them, and listed as expansion content; `--no-expansion-orders` leaves them out.
- `lint` checks the title tree as the game does (unique names; a barony inside its own county; a county's capital barony with a county above it) and that every vassal contract names both people. Its count of rejected `localization_key` fields now matches the game's.

### Changed
- Large saves migrate much faster: finding a section no longer reads the whole save again each time (a full migration of the founding campaign in both religion shapes went from 11 to 7 minutes).

## [0.3.0] - 2026-10-25

### Added
- `lint <save>`: checks a save before you load it and reports what the game will still complain about. Findings come in four kinds:
  - **errors**: something the game reads by number is broken (a brace that does not close, a faith or rite that points nowhere, a character without a rite). The migration rules write these, so an error means a rule did not finish its job.
  - **warnings**: links the migration does not write that point at nothing (a spouse who is no longer in the save, a county without a culture). Old saves often carry some of these already.
  - **what the game will log**: each kind of error 1.20 writes to its error log when it reads the save (portrait DNA of the wrong length, settings it no longer accepts, references to modifiers, perks or events it no longer has, titles it no longer defines, dynasty names it cannot find), with a predicted number of lines and examples. Cultures the game's own scripts ask for but the save lacks are listed by name.
  - **unknown names**: setting names that neither the game nor the save's mods know.
- `migrate` now runs the same checks on every output by default and prints them. It writes them next to the output as `<name>.lint.json` and adds them to `--report`. `--no-lint` skips the checks.
- `--lint-mods save|none` (on `migrate`) and `--mods save|none` (on `lint`): whether the checks assume the save's own Workshop mods will be active when it loads (the default, for those installed) or a load with no mods. Mods the save lists that are not installed are named, and the report records which game folder, reference save and mod folders the checks used.
- Every finding is described in plain words first; for what the game will log, the game's own log wording follows, so it can be found in the game's error log.
- Exit code 4: the checks found an error. `migrate` still writes the output so it can be inspected.

### Changed
- The test suite no longer finds the real game install or the project's reference save by itself; a test that needs one names it. `CK3_GAME_DIR=none` and `CK3_REFERENCE_SAVE=none` now turn the automatic search off for anyone, the same as `--reference none`.
- A game folder named with `--game-dir` or `CK3_GAME_DIR` that is not the game's `game` folder is now refused with a message naming what was expected, instead of being silently replaced by the installed game.
- The README's version badge now follows the repository's latest tag by itself.
- Package metadata: author name, keywords, a games classifier and a link to this changelog.

## [0.2.1] - 2026-10-25

### Fixed
- Writing a migrated save no longer fails at random on Windows with "Access is denied" when another program (an antivirus scanner or the search indexer) briefly holds the output file: the final step that puts the finished file in place is retried for up to about two seconds before giving up with the original error.

## [0.2.0] - 2026-10-24

The first working version: a save written by Crusader Kings III 1.8 can be rewritten so that 1.20 loads it.

### Added
- `inspect <save>`: shows a save's header, its metadata block and the files inside its zip.
- `migrate <save>`: reads a save and writes a migrated copy. The input is never modified: the output may not be the input file, an existing output is refused unless `--force` is given, and the written file is re-read and verified before it replaces anything. These refusals, and a missing output folder, are reported before any migration work starts.
- `migrate --rules all` brings a 1.8-era save forward to 1.20. It:
  - removes entries the 1.20 game rejects when loading: `converging` blocks inside temporary opinions, empty entries in the game-rule settings, entries with an empty key, and modifiers with an empty name;
  - moves each title's name, adjective, prefix and article into the block where 1.20 reads them;
  - re-encodes relationship flags to the width 1.20 expects;
  - sets the save's version fields to the target version;
  - rebuilds religion from a reference save written by the target game version (faiths, rites, holy sites, religious organizations), translating titles and cultures by name to the save's own numbering;
  - points every character, county and holy order at the matching 1.20 rite instead of an old faith, and updates script variables that refer to a faith or religion;
  - keeps Catholicism and Orthodoxy as independent faiths, each with its religious head carried over; when two old faiths would hand the same new faith different heads, the first is kept and the other is reported;
  - carries a player-made custom faith across, either as a faith of its own or as a rite of the faith its template now belongs to, with its doctrines, fervor, religious head, holy sites, founder (when that character is still in the save) and dated history, wherever 1.20 has a place for each;
  - gives characters with no recorded faith their house head's rite, falling back to the dynasty head, then the employer, then the player;
  - reports titles the current game no longer defines.
- `migrate` options:
  - `--reference <save>`: the target-version save the religion rebuild copies from. The default is `$CK3_REFERENCE_SAVE`; `--reference none` skips the rebuild.
  - `--wos-shape faith|rite|both`: how a custom faith is carried. `both` (the default) writes two outputs, `<name>__wos-faith` and `<name>__wos-rite`; a save without a custom faith gets a single output under the plain name.
  - `--report <file.json>`: counts for every rule, what was dropped and why, and the assumptions made.
  - `--dry-run`: build and verify the result in memory and write nothing.
  - `--portraits-version`, `--game-dir`, `--recompress`, `-o/--output`.
  - Without `--rules`, `migrate` applies no rules and writes an unchanged copy.
- `rules`: lists the migration rules, with the game versions each one applies to.

### Known limits
- The regions 1.20's map rework changed are not yet transplanted; holy sites whose barony no longer exists are dropped and listed in the report.
- Cultures 1.20 no longer defines, portrait genes added by mods, and mod content in general are not handled yet. A migrated save loads, but these produce errors in the game's error log, and characters may not look as they did.
- Tested on one campaign, 1.8.1 to 1.20.1.2. The religion rebuild needs a save from the target game version.

## [0.1.0] - 2026-10-24

### Added
- The project's structure, from git-repokit.

[Unreleased]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.29...HEAD
[0.4.29]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.28...v0.4.29
[0.4.28]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.27...v0.4.28
[0.4.27]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.26...v0.4.27
[0.4.26]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.25...v0.4.26
[0.4.25]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.24...v0.4.25
[0.4.24]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.23...v0.4.24
[0.4.23]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.22...v0.4.23
[0.4.22]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.21...v0.4.22
[0.4.21]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.20...v0.4.21
[0.4.20]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.19...v0.4.20
[0.4.19]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.18...v0.4.19
[0.4.18]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.17...v0.4.18
[0.4.17]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.16...v0.4.17
[0.4.16]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.15...v0.4.16
[0.4.15]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.14...v0.4.15
[0.4.14]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.13...v0.4.14
[0.4.13]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.12...v0.4.13
[0.4.12]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.11...v0.4.12
[0.4.11]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.10...v0.4.11
[0.4.10]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.9...v0.4.10
[0.4.9]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.8...v0.4.9
[0.4.8]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.7...v0.4.8
[0.4.7]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/djdarcy/ck3-save-updater/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/djdarcy/ck3-save-updater/compare/129a17e...v0.4.0
[0.3.30]: https://github.com/djdarcy/ck3-save-updater/compare/72ca601...129a17e
[0.3.29]: https://github.com/djdarcy/ck3-save-updater/compare/c596844...72ca601
[0.3.28]: https://github.com/djdarcy/ck3-save-updater/compare/1a6a7a5...c596844
[0.3.27]: https://github.com/djdarcy/ck3-save-updater/compare/4f0f998...1a6a7a5
[0.3.26]: https://github.com/djdarcy/ck3-save-updater/compare/db54e04...4f0f998
[0.3.25]: https://github.com/djdarcy/ck3-save-updater/compare/12e2d4e...db54e04
[0.3.24]: https://github.com/djdarcy/ck3-save-updater/compare/ad77aaf...12e2d4e
[0.3.23]: https://github.com/djdarcy/ck3-save-updater/compare/39da8d0...ad77aaf
[0.3.22]: https://github.com/djdarcy/ck3-save-updater/compare/159560b...39da8d0
[0.3.21]: https://github.com/djdarcy/ck3-save-updater/compare/45391ee...159560b
[0.3.20]: https://github.com/djdarcy/ck3-save-updater/compare/014e275...45391ee
[0.3.19]: https://github.com/djdarcy/ck3-save-updater/compare/a87f1ac...014e275
[0.3.18]: https://github.com/djdarcy/ck3-save-updater/compare/a6c23f0...a87f1ac
[0.3.17]: https://github.com/djdarcy/ck3-save-updater/compare/3e0ecc4...a6c23f0
[0.3.16]: https://github.com/djdarcy/ck3-save-updater/compare/ea04cea...3e0ecc4
[0.3.15]: https://github.com/djdarcy/ck3-save-updater/compare/c3ad245...ea04cea
[0.3.14]: https://github.com/djdarcy/ck3-save-updater/compare/dd2e901...c3ad245
[0.3.13]: https://github.com/djdarcy/ck3-save-updater/compare/08dd941...dd2e901
[0.3.12]: https://github.com/djdarcy/ck3-save-updater/compare/1a7a626...08dd941
[0.3.11]: https://github.com/djdarcy/ck3-save-updater/compare/1c8eda4...1a7a626
[0.3.10]: https://github.com/djdarcy/ck3-save-updater/compare/8af64dd...1c8eda4
[0.3.9]: https://github.com/djdarcy/ck3-save-updater/compare/174e82f...8af64dd
[0.3.8]: https://github.com/djdarcy/ck3-save-updater/compare/b8fa75b...174e82f
[0.3.7]: https://github.com/djdarcy/ck3-save-updater/compare/1564d12...b8fa75b
[0.3.6]: https://github.com/djdarcy/ck3-save-updater/compare/1d61473...1564d12
[0.3.5]: https://github.com/djdarcy/ck3-save-updater/compare/e0a6ab3...1d61473
[0.3.4]: https://github.com/djdarcy/ck3-save-updater/compare/8e9309c...e0a6ab3
[0.3.3]: https://github.com/djdarcy/ck3-save-updater/compare/4d6ca3b...8e9309c
[0.3.2]: https://github.com/djdarcy/ck3-save-updater/compare/v0.3.1...4d6ca3b
[0.3.1]: https://github.com/djdarcy/ck3-save-updater/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/djdarcy/ck3-save-updater/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/djdarcy/ck3-save-updater/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/djdarcy/ck3-save-updater/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/djdarcy/ck3-save-updater/releases/tag/v0.1.0
