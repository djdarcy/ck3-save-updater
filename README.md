# ck3-save-migrator

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

Migrate old Crusader Kings III saves forward to the current game version: inspect, patch, and revive .ck3 save files

## What this is

Crusader Kings III will not load a save from an older game version once the save format has moved on far enough. ck3-save-migrator rewrites such a save so the current game can load it: it removes what the new version rejects, moves data to where the new version expects it, and rebuilds religion from a save written by the target version, keeping custom faiths, religious heads and every character's faith. The input file is never modified. **Status:** a 1.8.1 campaign migrated with this tool loads into 1.20.1.2, and the `lint` command predicts what the game will still log for a migrated save. The regions 1.20's map rework added can be brought in from a 1.20 save of the same date (opt-in, `--rules all,R15,R14,R16`, still in progress); renamed or removed cultures, mod portrait genes and mod content are not handled yet; see the [CHANGELOG](CHANGELOG.md) for what each version covers and the [roadmap](https://github.com/djdarcy/ck3-save-migrator/issues/1) for what comes next.

## Installation

Python 3.10 or newer.

```bash
git clone https://github.com/djdarcy/ck3-save-migrator.git
cd ck3-save-migrator
pip install -e .
```

## Usage

The commands:

- `ck3-save-migrator inspect <save>`: show a save's header, metadata block and the files inside it.
- `ck3-save-migrator migrate <save> --rules all`: write a migrated copy; `--report` writes a JSON account of every change.
- `ck3-save-migrator lint <save>`: check a save before loading it (below).
- `ck3-save-migrator rules`: list the migration rules and the game versions they apply to.
- `ck3-save-migrator check <save>`: say, for each rule, whether this save still needs it, without changing anything ([Checking a save](docs/writing-a-patch.md#checking-a-save)).
- `ck3-save-migrator disable <id>`, `enable <id>`, `disabled`: turn a rule off for every later `--rules all`, turn it back on, and list what is off ([Turning rules off](docs/writing-a-patch.md#turning-rules-off)).
- `ck3-save-migrator soak <save>`: **starts the game**, loads the save, lets it run, closes it through Exit to Desktop and says whether it exited cleanly or crashed; your autosaves and mod list are put back afterwards ([soak](docs/soak.md)).

Migrating a 1.8-era save for 1.20, with religion rebuilt from a save you made in 1.20 (start any game in 1.20 and save it; a save at the same start date is closest):

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --rules all \
    --reference "A_New_1_20_Game.ck3" \
    -o "My_Old_Campaign.migrated.ck3" --report "My_Old_Campaign.report.json"
```

A custom faith is written two ways by default, as its own faith and as a rite of the faith its template now belongs to, giving `My_Old_Campaign__wos-faith.migrated.ck3` and `My_Old_Campaign__wos-rite.migrated.ck3`; pass `--wos-shape faith` or `--wos-shape rite` for one. Copy the result into your `save games` folder and load it from the game. `--dry-run` builds and verifies everything without writing a file.

### Checking a save before you load it

`lint` reads a save and reports, without changing it:

- **errors**: broken links the game reads by number, such as a faith or rite that points nowhere or a character without a rite;
- **warnings**: links that point at nothing but that the migration does not write, which old saves often carry already;
- **what the game will log**: each kind of complaint the current game writes to its error log when it reads this save, with a predicted count and examples;
- **unknown names**: setting names neither the game nor the mods know.

`migrate` runs the same checks on every output by default, prints them, and writes them next to the output as `<name>.lint.json` (`--no-lint` skips them). The predictions depend on which mods will be active: by default the checks assume the Workshop mods the save itself lists (those installed); `--mods none` on `lint`, or `--lint-mods none` on `migrate`, predicts a load with no mods. Pointing the checks at the game folder (found automatically, or `--game-dir`) and a save from the current version (`--reference`) makes them more complete.

Exit codes: 0 done with no error from the migrator itself (the save can still carry thousands of predicted log lines; that is reported, not an error), 1 bad input, 2 refused (the output exists, or would overwrite the input), 3 the written file failed verification, 4 the checks found an error (`migrate` still writes the output so it can be inspected), 5 a patch failed (`migrate` prints why and writes nothing; `check` exits 5 when a patch would fail).

### How much it says

Every command takes `-v` and `-q`, and they can be repeated:

- `-v` adds each rule's time and a one-line summary of the new-map transplant;
- `-vv` adds how long reading and writing the save took;
- `-q` leaves only the results: what was written, and the checks' verdict;
- `-qqq` leaves only errors;
- `-qqqq` prints nothing, so only the exit code tells.

`--show CHANNEL:LEVEL` raises a single part of the output, e.g. `--show transplant:1`. The parts are `rules`, `transplant`, `lint`, `io` and `timing`. Where there is no command line to add flags to (a script, a scheduler), the environment does the same: `CK3SM_VERBOSITY` (a number, or a level name such as `extra`) and `CK3SM_SHOW` (e.g. `transplant:1,timing:1`).

Results go to standard output; warnings, errors and the extra detail go to standard error. The `--report` JSON is the same at every level.

## More

- [Writing a patch](docs/writing-a-patch.md): fixes as `patch.toml` files, run with `migrate --pack <folder>`.
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

ck3-save-migrator, Copyright (C) 2026 Dustin Darcy

Licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later) -- see [LICENSE](LICENSE).
