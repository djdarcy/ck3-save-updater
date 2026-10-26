# Changelog

All notable changes to ck3-save-migrator are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.3...HEAD
[0.3.3]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/djdarcy/ck3-save-migrator/releases/tag/v0.1.0
