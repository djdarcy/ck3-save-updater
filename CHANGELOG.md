# Changelog

All notable changes to ck3-save-migrator are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `ck3update setup` (run it as `python -m ck3_save_migrator setup` when `ck3update` is "not recognized"): says where pip put the command and, on Windows, offers to add that folder to your user PATH, through dazzlecmd-lib's self-setup (now a dependency, loaded by this command only). `--dry-run` changes nothing; `--yes` does not ask.

### Changed
- The config file and the JSON reports (the `--report`, the lint file beside each output, `lint --json`, `gamediff --json`) are written atomically, through dazzle-filekit: a crash, a full disk or a kill mid-write leaves the old file whole instead of a torn one. Their bytes are unchanged.
- `ck3update tools run` runs a script directly, `[python, <script>] + args`, the same way a run patch's `tool =` does: nothing extra to install (the `[tools]` extra and dazzlecmd-lib are no longer needed), no cache folder written (`--cache-dir` and `CK3SM_TOOLS_CACHE` are gone), and a scripts folder holding an `__init__.py` no longer breaks it.

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

[Unreleased]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.17...HEAD
[0.3.17]: https://github.com/djdarcy/ck3-save-migrator/compare/3e0ecc4...v0.3.17
[0.3.16]: https://github.com/djdarcy/ck3-save-migrator/compare/ea04cea...3e0ecc4
[0.3.15]: https://github.com/djdarcy/ck3-save-migrator/compare/c3ad245...ea04cea
[0.3.14]: https://github.com/djdarcy/ck3-save-migrator/compare/dd2e901...c3ad245
[0.3.13]: https://github.com/djdarcy/ck3-save-migrator/compare/08dd941...dd2e901
[0.3.12]: https://github.com/djdarcy/ck3-save-migrator/compare/1a7a626...08dd941
[0.3.11]: https://github.com/djdarcy/ck3-save-migrator/compare/1c8eda4...1a7a626
[0.3.10]: https://github.com/djdarcy/ck3-save-migrator/compare/8af64dd...1c8eda4
[0.3.9]: https://github.com/djdarcy/ck3-save-migrator/compare/174e82f...8af64dd
[0.3.8]: https://github.com/djdarcy/ck3-save-migrator/compare/b8fa75b...174e82f
[0.3.7]: https://github.com/djdarcy/ck3-save-migrator/compare/1564d12...b8fa75b
[0.3.6]: https://github.com/djdarcy/ck3-save-migrator/compare/1d61473...1564d12
[0.3.5]: https://github.com/djdarcy/ck3-save-migrator/compare/e0a6ab3...1d61473
[0.3.4]: https://github.com/djdarcy/ck3-save-migrator/compare/8e9309c...e0a6ab3
[0.3.3]: https://github.com/djdarcy/ck3-save-migrator/compare/4d6ca3b...8e9309c
[0.3.2]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.1...4d6ca3b
[0.3.1]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/djdarcy/ck3-save-migrator/releases/tag/v0.1.0
