# ck3-save-migrator

[![GitHub Workflow Status][workflow-badge]][workflow-url]
[![Version][version-badge]][version-url]
[![Python][python-badge]][python-url]
[![License][license-badge]][license-url]
[![GitHub Discussions][discussions-badge]][discussions-url]

[workflow-badge]: https://github.com/djdarcy/ck3-save-migrator/actions/workflows/ci-python.yml/badge.svg
[workflow-url]: https://github.com/djdarcy/ck3-save-migrator/actions
[version-badge]: https://img.shields.io/badge/version-0.2.0-blue
[version-url]: https://github.com/djdarcy/ck3-save-migrator/releases
[python-badge]: https://img.shields.io/badge/python-%3E%3D3.10-darkgreen
[python-url]: https://python.org/downloads
[license-badge]: https://img.shields.io/badge/license-GPL--3.0--or--later-orange
[license-url]: https://github.com/djdarcy/ck3-save-migrator/blob/main/LICENSE
[discussions-badge]: https://img.shields.io/badge/discussions-Welcome-lightgrey
[discussions-url]: https://github.com/djdarcy/ck3-save-migrator/discussions

Migrate old Crusader Kings III saves forward to the current game version: inspect, patch, and revive .ck3 save files

## What this is

Crusader Kings III will not load a save from an older game version once the save format has moved on far enough. ck3-save-migrator rewrites such a save so the current game can load it: it removes what the new version rejects, moves data to where the new version expects it, and rebuilds religion from a save written by the target version, keeping custom faiths, religious heads and every character's faith. The input file is never modified. **Status:** 0.2.0 brings a 1.8.1 campaign into 1.20.1.2, where it loads into the game. Map regions changed by 1.20's map rework, renamed or removed cultures, mod portrait genes and mod content are not handled yet; see the [CHANGELOG](CHANGELOG.md) for what each version covers and the [roadmap](https://github.com/djdarcy/ck3-save-migrator/issues/1) for what comes next.

## Installation

Python 3.10 or newer.

```bash
git clone https://github.com/djdarcy/ck3-save-migrator.git
cd ck3-save-migrator
pip install -e .
```

## Usage

Three commands:

- `ck3-save-migrator inspect <save>`: show a save's header, metadata block and the files inside it.
- `ck3-save-migrator migrate <save> --rules all`: write a migrated copy; `--report` writes a JSON account of every change.
- `ck3-save-migrator rules`: list the migration rules and the game versions they apply to.

Migrating a 1.8-era save for 1.20, with religion rebuilt from a save you made in 1.20 (start any game in 1.20 and save it; a save at the same start date is closest):

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --rules all \
    --reference "A_New_1_20_Game.ck3" \
    -o "My_Old_Campaign.migrated.ck3" --report "My_Old_Campaign.report.json"
```

A custom faith is written two ways by default, as its own faith and as a rite of the faith its template now belongs to, giving `My_Old_Campaign__wos-faith.migrated.ck3` and `My_Old_Campaign__wos-rite.migrated.ck3`; pass `--wos-shape faith` or `--wos-shape rite` for one. Copy the result into your `save games` folder and load it from the game. `--dry-run` builds and verifies everything without writing a file.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Contributions
Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details on how to contribute.

Like the project?

[!["Buy Me A Coffee"](https://camo.githubusercontent.com/0b448aabee402aaf7b3b256ae471e7dc66bcf174fad7d6bb52b27138b2364e47/68747470733a2f2f7777772e6275796d6561636f666665652e636f6d2f6173736574732f696d672f637573746f6d5f696d616765732f6f72616e67655f696d672e706e67)](https://www.buymeacoffee.com/djdarcy)

## License

This project is licensed under the terms specified in the LICENSE file.

## Acknowledgements

Dustin 6962246+djdarcy@users.noreply.github.com
