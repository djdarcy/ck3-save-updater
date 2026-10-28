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

The commands:

- `ck3update inspect <save>`: show a save's header, metadata block and the files inside it.
- `ck3update migrate <save> --rules all`: write an updated copy; `--report` writes a JSON account of every change. `--rules all,-R21` leaves one rule out.
- `ck3update lint <save>`: check a save before loading it (below).
- `ck3update rules`: list the update rules and the game versions they apply to.
- `ck3update check <save>`: say, for each rule, whether this save still needs it, without changing anything ([Checking a save](docs/writing-a-patch.md#checking-a-save)).
- `ck3update disable <id>`, `enable <id>`, `disabled`: turn a rule off for every later `--rules all`, turn it back on, and list what is off ([Turning rules off](docs/writing-a-patch.md#turning-rules-off)).
- `ck3update gamediff <old game> <new game> [--save <save>]`: what a game update added, removed and changed, and which of it a save uses ([gamediff](docs/gamediff.md)).
- `ck3update soak <save>`: **starts the game**, loads the save, lets it run, closes it through Exit to Desktop and says whether it exited cleanly or crashed; your autosaves and mod list are put back afterwards ([soak](docs/soak.md)).

Updating a 1.8-era save for 1.20, with religion rebuilt from a save you made in 1.20 (start any game in 1.20 and save it; a save at the same start date is closest):

```bash
ck3update migrate "My_Old_Campaign.ck3" --rules all \
    --reference "A_New_1_20_Game.ck3" \
    -o "My_Old_Campaign.migrated.ck3" --report "My_Old_Campaign.report.json"
```

A custom faith is written two ways by default, as its own faith and as a rite of the faith its template now belongs to, giving `My_Old_Campaign__wos-faith.migrated.ck3` and `My_Old_Campaign__wos-rite.migrated.ck3`; pass `--wos-shape faith` or `--wos-shape rite` for one. Copy the result into your `save games` folder and load it from the game. `--dry-run` builds and verifies everything without writing a file. [Updating a save](docs/updating-a-save.md) walks through the whole flow.

### Checking a save before you load it

`lint` reads a save and reports, without changing it:

- **errors**: broken links the game reads by number, such as a faith or rite that points nowhere or a character without a rite;
- **warnings**: links that point at nothing but that the update does not write, which old saves often carry already;
- **what the game will log**: each kind of complaint the current game writes to its error log when it reads this save, with a predicted count and examples;
- **unknown names**: setting names neither the game nor the mods know.

`migrate` runs the same checks on every output by default, prints them, and writes them next to the output as `<name>.lint.json` (`--no-lint` skips them). The predictions depend on which mods will be active: by default the checks assume the Workshop mods the save itself lists (those installed); `--mods none` on `lint`, or `--lint-mods none` on `migrate`, predicts a load with no mods. Pointing the checks at the game folder (found automatically, or `--game-dir`) and a save from the current version (`--reference`) makes them more complete.

Exit codes: 0 done with no error from the updater itself (the save can still carry thousands of predicted log lines; that is reported, not an error), 1 bad input, 2 refused (the output exists, or would overwrite the input), 3 the written file failed verification, 4 the checks found an error (`migrate` still writes the output so it can be inspected), 5 a patch failed (`migrate` prints why and writes nothing; `check` exits 5 when a patch would fail).

### How much it says

Every command takes `-v` and `-q`, and they can be repeated:

- `-v` adds each rule's time and a one-line summary of the new-map transplant;
- `-vv` adds how long reading and writing the save took;
- `-q` leaves only the results: what was written, and the checks' verdict;
- `-qqq` leaves only errors;
- `-qqqq` prints nothing, so only the exit code tells.

`--show CHANNEL:LEVEL` raises a single part of the output, e.g. `--show transplant:1`. The parts are `rules`, `transplant`, `lint`, `io` and `timing`. Where there is no command line to add flags to (a script, a scheduler), the environment does the same: `CK3SM_VERBOSITY` (a number, or a level name such as `extra`) and `CK3SM_SHOW` (e.g. `transplant:1,timing:1`).

Results go to standard output; warnings, errors and the extra detail go to standard error. The `--report` JSON is the same at every level.

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
- [Writing a patch](docs/writing-a-patch.md): fixes as `patch.toml` files, run with `migrate --pack <folder>`.
- [gamediff](docs/gamediff.md): what a game update changed, and what of it your save uses.
- [soak](docs/soak.md): load a save in the game and watch it (starts the game).
- [Tools](docs/tools.md): an optional add-on that lists and runs the project's standalone scripts as they are.
- [Platform support](docs/platform-support.md): what the tool is tested on.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers:

- the code of conduct
- reporting bugs
- suggesting enhancements
- pull requests

Like the project?

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

ck3-save-updater, Copyright (C) 2026 Dustin Darcy

Licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later) -- see [LICENSE](LICENSE).
