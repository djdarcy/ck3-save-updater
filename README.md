# ck3-save-updater

[![GitHub Workflow Status][workflow-badge]][workflow-url]
[![Version][version-badge]][version-url]
[![Python][python-badge]][python-url]
[![License][license-badge]][license-url]
[![GitHub Discussions][discussions-badge]][discussions-url]

[workflow-badge]: https://github.com/djdarcy/ck3-save-migrator/actions/workflows/ci-python.yml/badge.svg
[workflow-url]: https://github.com/djdarcy/ck3-save-migrator/actions
[version-badge]: https://img.shields.io/github/v/tag/djdarcy/ck3-save-migrator
[version-url]: https://github.com/djdarcy/ck3-save-migrator/releases
[python-badge]: https://img.shields.io/badge/python-%3E%3D3.10-darkgreen
[python-url]: https://python.org/downloads
[license-badge]: https://img.shields.io/badge/license-GPL--3.0--or--later-orange
[license-url]: https://github.com/djdarcy/ck3-save-migrator/blob/main/LICENSE
[discussions-badge]: https://img.shields.io/badge/discussions-Welcome-lightgrey
[discussions-url]: https://github.com/djdarcy/ck3-save-migrator/discussions

Update old Crusader Kings III saves to the current game version: inspect, patch, and revive .ck3 save files.

## What this is

Crusader Kings III will not load a save from an older game version once the save format has moved on far enough. `ck3update` rewrites such a save so the current game can load it: it removes what the new version rejects, moves data to where the new version expects it, and rebuilds religion from a save written by the target version, keeping custom faiths, religious heads and every character's faith. The save you give it is never changed; every result is a new file.

## Status: an early release

What is proven:

- A 1.8.1 campaign with 34 mods, updated with this tool, loads and plays in 1.20.1.2.
- The update is reproducible: the same save and the same options give the same result every time. A `.ck3` file is a zip, and a zip records when each file in it was written, so compare two saves by their content (`ck3update inspect` shows it), not by the bytes of the files.

What is not handled yet:

- The regions added to the map since the save's version are brought in from a 1.20 save of the same date. This is opt-in (`--rules all,R15,R14,R16`) and still being finished ([#6](https://github.com/djdarcy/ck3-save-migrator/issues/6)).
- Cultures the game renamed or removed ([#7](https://github.com/djdarcy/ck3-save-migrator/issues/7)).
- Portrait DNA across portrait versions, and the extra portrait genes some mods add ([#8](https://github.com/djdarcy/ck3-save-migrator/issues/8)).
- Mod content in general.

A general updater, from any game version to any later one, is the roadmap ([#14](https://github.com/djdarcy/ck3-save-migrator/issues/14)). The [CHANGELOG](CHANGELOG.md) says what each version covers.

## Installation

Python 3.10 or newer.

```bash
pip install ck3-save-updater
```

This installs the `ck3update` command. The project's old name, `ck3-save-migrator`, still works as a second name for the same command for now.

To work on the code instead:

```bash
git clone https://github.com/djdarcy/ck3-save-migrator.git
cd ck3-save-migrator
pip install -e .
```

## Usage

[Updating a save](docs/updating-a-save.md) walks through the whole flow; the steps in short:

- Update a save to the game you have installed, by its name in the game's `save games` folder:
  ```bash
  ck3update status "My_Old_Campaign"     # what update will do: the game, the version gap, the patches, the reference save
  ck3update update "My_Old_Campaign" --dry-run   # run it all in memory, with each patch's counts; nothing is written
  ck3update update "My_Old_Campaign"
  ```
  It writes `My_Old_Campaign__updated__<game version>.ck3` beside the save, and its report beside that. The packs it runs are chosen by the save's and the game's versions; a reference save (a 1.20 game at your campaign's date) is found in the save folder when there is one, and when there is none `status` says which rules skip and how to make one. `migrate`, below, is the lower-level command it runs.

  In a terminal the plan is coloured, verdict first; set `NO_COLOR` (or `CK3UPDATE_COLOR=never`) for plain text. Piped output is always plain unless `CK3UPDATE_COLOR=always`.
- `ck3update inspect "My_Old_Campaign.ck3"` shows a save's header, metadata block, the files inside it and its versions, and the game installs found (Steam's own records, its libraries on any drive) with their versions. A save can be named by its path, or by its name in the game's `save games` folder.
- Update a 1.8-era save for 1.20, with religion rebuilt from a save you made in 1.20 (start any game in 1.20 and save it; a save at the same start date is closest). This is the usual update; copy the result into your `save games` folder and load it from the game:
  ```bash
  ck3update migrate "My_Old_Campaign.ck3" --rules all --reference "A_New_1_20_Game.ck3" -o "My_Old_Campaign.migrated.ck3" --report "My_Old_Campaign.report.json"
  ```
  A save with a custom faith gives two outputs, one per way of carrying it ([Options](docs/options.md#custom-faiths)); `--dry-run` builds and verifies everything without writing a file.
- Update with the new-map regions turned on, so the lands and rulers 1.20 added arrive held instead of being handed to the player. The reference should be a 1.20 save at your campaign's own date, because the new regions' rulers and families are copied from it as they are on that date; `--old-game-dir` is the game folder of the version your save was made with:
  ```bash
  ck3update migrate "My_Old_Campaign.ck3" --rules all,R15,R14,R16 --reference "A_1_20_Game_At_My_Campaign_Date.ck3" --old-game-dir "Old_CK3/game"
  ```
- `ck3update lint "My_Old_Campaign.migrated.ck3"` checks a save before you load it and predicts what the game will complain about (`migrate` already runs it on every output).
- `ck3update rules` lists the update rules and the game versions each one applies to; `ck3update check <save>` says which of them a save still needs, without changing anything. `--rules all,-R21` leaves one rule out, and `ck3update disable <id>` turns one off for every later run ([Turning rules off](docs/writing-a-patch.md#turning-rules-off)).
- Your own fixes run in the same `migrate` call when you put their pack in your packs folder (`packs` beside the config file, created on the first run with a README and an example); a pack that runs code runs once you trust it with `ck3update trust <pack id>`, and `ck3update packs` lists what was found ([Your own packs folder](docs/writing-a-patch.md#your-own-packs-folder)).
- `ck3update gamediff <old game> <new game> [--save <save>]` shows what a game update added, removed and changed, and which of it a save uses ([gamediff](docs/gamediff.md)).
- `ck3update soak <save>` **starts the game**, loads the save, lets it run, closes it through Exit to Desktop and says whether it exited cleanly or crashed; your autosaves and mod list are put back afterwards ([soak](docs/soak.md)).

## Performance after updating a large save

A large updated campaign can stutter in 1.20.1.2 where a new game does not. Both causes measured so far are the game's own behaviour, which a big save makes visible; both have workarounds:

- **Two top-bar alerts.** The game re-checks the player's alerts one at a time, even while paused. On the founding campaign two vanilla alerts cost about half a second per check each, freezing the game every 2 to 3 seconds:
  - the tutorial advice for great projects: turn tutorial and reactive advice off in the game's settings;
  - the great-cathedral upgrade alert (for clergy rulers): a small local mod that turns the alert off removes it, and the cathedral decision itself still works from the decisions screen.
- **Portraits.** Portraits on screen are recalculated every 30 frames, paused or not. A character window with a large family kept dozens rebuilding and froze for over half a second in every five. A mod that overrides `common/defines/jomini/portraits.txt` with a larger `PORTRAIT_CACHE_EXPIRE_FRAMES` (600 was tried) cut that about tenfold.

A packaged performance mod is planned; until then these are the workarounds. [Updating a save](docs/updating-a-save.md#performance-after-updating-a-large-save) has the details.

## Mods known to misbehave in 1.20

- **Better Barbershop** (Workshop 2220326926) replaces the barbershop and interaction-menu windows, and in 1.20 the barbershop then shows no characters. Disabling it brings the built-in barbershop back.

## More

- [Updating a save](docs/updating-a-save.md): the everyday flow, from `inspect` and `check` to `migrate`, `lint` and loading it, what to do when the game updates again, and performance after the update.
- [Options](docs/options.md): the most used options of `migrate`.
- [Rules](docs/rules.md): every rule, what it changes and why, and how to choose them.
- [New-map regions](docs/new-map-regions.md): how the regions 1.20 added are brought in from a 1.20 save.
- [Checking a save](docs/lint.md): what `lint` checks, and the exit codes.
- [Output and verbosity](docs/output-and-verbosity.md): `-v`, `-q`, `--show`, and where each kind of output goes.
- [Reports](docs/reports.md): what the `--report` JSON contains.
- [Differences from the game](docs/differences-from-the-game.md): where the tool deliberately does something other than the game's own conversion.
- [The reference save](docs/reference-save.md): making a 1.20 save at your campaign's date, with `reference-mod`.
- [Troubleshooting](docs/troubleshooting.md): what the common messages mean and what to do.
- [Writing a patch](docs/writing-a-patch.md): fixes as `patch.toml` files, run with `migrate --pack <folder>`.
- [gamediff](docs/gamediff.md): what a game update changed, and what of it your save uses.
- [soak](docs/soak.md): load a save in the game and watch it (starts the game).
- [Tools](docs/tools.md): an optional add-on that lists and runs the project's standalone scripts as they are.
- [Thinning a save's population](docs/thin-population.md): a diagnostic that writes a copy of a save with fewer characters.
- [Platform support](docs/platform-support.md): what the tool is tested on.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the code of conduct, reporting bugs, suggesting enhancements and pull requests.

Like the project? [!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

ck3-save-updater, Copyright (C) 2026 Dustin Darcy

Licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later) -- see [LICENSE](LICENSE).
