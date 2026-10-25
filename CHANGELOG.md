# Changelog

All notable changes to ck3-save-migrator are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/djdarcy/ck3-save-migrator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/djdarcy/ck3-save-migrator/releases/tag/v0.1.0
