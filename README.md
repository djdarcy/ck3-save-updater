# ck3-save-updater

[![PyPI](https://img.shields.io/pypi/v/ck3-save-updater?color=green)](https://pypi.org/project/ck3-save-updater/)
[![Release Date](https://img.shields.io/github/release-date/djdarcy/ck3-save-updater?color=green)](https://github.com/djdarcy/ck3-save-updater/releases)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/ck3-save-updater?period=total&units=international_system&left_color=black&right_color=green&left_text=downloads)](https://pypistats.org/packages/ck3-save-updater)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-green.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Installs](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/djdarcy/a5a1c9f7d7d4790b6c16cf492646e3b3/raw/installs.json)](https://djdarcy.github.io/ck3-save-updater/stats/#installs)
[![GitHub Discussions](https://img.shields.io/github/discussions/djdarcy/ck3-save-updater)](https://github.com/djdarcy/ck3-save-updater/discussions)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](docs/platform-support.md)

`ck3update` brings an old Crusader Kings III save forward to the game version you have installed, so the current game can load it. It removes what the new version rejects, moves data to where the new version expects it, and rebuilds the map and religion from a save written by the new version, keeping custom faiths, religious heads and every character's faith.

## Quick start

Wherever you see `My Save`, put your save's name (without `.ck3`). Your save itself is never changed, the update is written to a new file beside it.

**1. Install** (Python 3.10 or newer):

```
pip install ck3-save-updater
```

**2. Make a reference save.** The tool rebuilds religion, and the regions the 1.20 map added, from a new game started by the game you have now, on your campaign's date. The game starts new games only on its own bookmark dates, so first add a bookmark on yours:

```
ck3update reference-mod --save "My Save"
```

That writes a small mod into the game's mod folder. Then, in the game:

1. In the launcher, turn on the mod **Reference bookmark _your date_ (ck3update)** and play. Your usual mods can stay off, but leave out any other mod that changes bookmarks.
2. Choose **New Game**, pick the bookmark **_your date_ Reference (ck3update)**, pick any character, and start.
3. **Save at once**, before unpausing (any name will do, e.g. `Reference`), and quit to the desktop.
4. Back in the launcher, turn the reference mod off again.

**3. Set the launcher's playset, then check and update.** In the game's launcher, set the playset to the mods you will play with, portrait mods included, then close the launcher. The faces are converted to match that playset's [gene layout](docs/glossary.md#gene-layout). Then:

```
ck3update status "My Save"
ck3update update "My Save"
```

`status` writes nothing. Its first line is the answer: READY, with what will run, or REFUSED, with a `fix:` line saying what to do. It finds the reference save by itself. `update` writes `My Save__updated__<game version>.ck3` next to your save. If your save is from before the 1.13 map rework, the update also brings in the regions the new map added, copied from the reference save.

**4. Play.** Start the game with that same playset, and load `My Save__updated__...`.

Faces are converted to the [gene layout](docs/glossary.md#gene-layout) of the game and portrait mods you play with (rule R19, [#8](https://github.com/djdarcy/ck3-save-updater/issues/8)). Set the launcher's playset before you update, or name the mods with `--portrait-mods`. If a portrait mod your save was made with has since been updated or removed, point `--old-portrait-mods` at the build the save used. Stuck? `ck3update -h`, [Troubleshooting](docs/troubleshooting.md), or the sections below.

## What ck3update has been measured against

I used one campaign, with 34 mods, updated from 1.8.1 to 1.20.1.2, and it loads and plays in 1.20.1.2. The built-in rules cover saves from 1.8 onwards. Saves from 1.8.x through 1.19.x should work, since each game version after 1.8 has only added to what a save holds, but so far only 1.8.1 has been tested end to end. Saves older than 1.8 are refused for now, and `status` names the gap. Support for them is planned. The [CHANGELOG](CHANGELOG.md) says what each release covers.

Not handled yet: cultures the game renamed or removed ([#7](https://github.com/djdarcy/ck3-save-updater/issues/7)), genes a portrait mod adds that the layout you load with lacks (they are dropped, and the report names them), and mod content in general. For a save from before the [map rework](docs/glossary.md#map-rework), the regions it added are brought in by default whenever a reference save is found. That step is still being finished ([#6](https://github.com/djdarcy/ck3-save-updater/issues/6)), and `--transplant off` leaves it out.

## Install

Python 3.10 or newer:

```bash
pip install ck3-save-updater
```

This installs the `ck3update` command (its old name, `ck3-save-migrator`, still works too). If your shell then says `'ck3update' is not recognized` (common on Windows after `pip install --user`, when pip puts the command in a folder that is not on PATH), run `python -m ck3_save_migrator setup`: it says where pip put the command and, on Windows, offers to add that folder to your PATH. After that, `ck3update setup` does the same ([Troubleshooting](docs/troubleshooting.md#ck3update-is-not-recognized)).

## Before you start

**The tool never launches the game, and never changes the save you give it** unless you ask for `--in-place`, and then only after keeping the original as `<name>.bak.ck3`. Every other result is a new file beside your save. (One separate command, `ck3update soak`, does start the game, and says so in its name and help; `status` and `update` never do.)

Have these ready:

- **The game folder.** The tool finds your installed game by itself through Steam's records, on any drive. If it does not, give `--game-dir "<...>\Crusader Kings III\game"` (or set `CK3_GAME_DIR`). `status` shows which install it used in its GAME block.
- **A [reference save](docs/glossary.md#reference-save)**, for most old saves: a save written by the game you have now, on your campaign's date. Religion is rebuilt from it, and the new-map regions are copied from it. The game only starts new games on its own bookmark dates, so `ck3update reference-mod --save "My_Old_Campaign.ck3"` writes a small mod into the game's mod folder that adds a bookmark on your date; enable it, start a new game from that bookmark, and save at once. [The reference save](docs/reference-save.md) walks through it. Without one, `status` lists the rules that will skip and these same steps.
- **The launcher's playset**, set to the mods you will play with: the faces are carried into that playset's [gene layout](docs/glossary.md#gene-layout) (its portrait mods, read from the launcher's `dlc_load.json`). `--portrait-mods` names them instead. If the portrait mods the save was made with have updated or gone since, keep a copy of the builds it used and give them with `--old-portrait-mods`.
- **Your [packs folder](docs/glossary.md#packs-folder)**, only if you have fixes of your own: `packs` beside the config file (`%APPDATA%\ck3-save-migrator\packs` on Windows, `~/.config/ck3-save-migrator/packs` elsewhere). The tool creates it the first time it loads rules, with `_example-pack`, a complete pack to copy when you write your own; the example itself never runs. You can ignore it to update a save.

## See what it will do: `ck3update status`

```bash
ck3update status "My_Old_Campaign"
```

Name the save by its path, or by its name in the game's `save games` folder. `status` writes nothing. It prints [the plan](docs/glossary.md#plan): what `update` will do, decided before anything runs.

Read the first line first. It is the verdict:

- [READY](docs/glossary.md#ready): `update` will write an updated save, and the line says how many patches run;
- [ALREADY CURRENT](docs/glossary.md#already-current): the save is at the game's version; there is nothing to do;
- [NOTHING TO DO](docs/glossary.md#nothing-to-do): no patch will run;
- [REFUSED](docs/glossary.md#refused): something has to be fixed first (below).

Below the verdict come blocks, one per header: SAVE, GAME, RECORD, [GAP](docs/glossary.md#gap), REFERENCE, PACKS, PATCHES (every fix in the order it runs, with why it runs or is skipped), DETECTORS, OUTPUT (the file `update` will write) and NOTES. The [glossary](docs/glossary.md#what-status-prints) says what each holds; [Configuration](docs/config.md#display-how-the-plan-is-laid-out) says how to change the layout. `--plain` prints it without colour, for pasting.

## Update it: `ck3update update`

```bash
ck3update update "My_Old_Campaign"
```

This runs the plan `status` printed and writes `My_Old_Campaign__updated__<game version>.ck3` beside your save, with a report beside it. It checks the result ([lint](docs/glossary.md#lint)) before it finishes. Copy the new file into the game's `save games` folder if it is not there already, start the game with the mods the save lists, and load it.

- `--dry-run` runs everything in memory and writes nothing.
- `--in-place` gives the updated save your save's own name, after keeping the original as `<name>.bak.ck3`; a clean result only.
- The tool remembers each campaign it updated ([the record](docs/glossary.md#record)), so the next save of the same campaign is updated with the same inputs without your giving them again.

## When it refuses

A refused plan ends with each reason and a `fix:` line under it saying what to do:

```
REFUSED: the gap 1.8.1 -> 1.21.0: no selected pack declares it covers it (a pack's [applies] span); nothing would bring
         the save to the game's version
  fix: a pack in your packs folder whose [applies] declares this span (docs/writing-a-patch.md), or `ck3update migrate`
       with the rules you choose
```

Do what the fix says, then run `status` again. Nothing is written while a plan is refused. [Troubleshooting](docs/troubleshooting.md) covers the common messages.

## Performance after updating a large save

A large updated campaign can stutter in 1.20.1.2 where a new game does not. Both causes measured so far are the game's own behaviour, which a big save makes visible, and both have workarounds:

- **Two top-bar alerts.** The game re-checks the player's alerts one at a time, even while paused. On the measured campaign two vanilla alerts cost about half a second per check each, freezing the game every 2 to 3 seconds:
  - the tutorial advice for great projects: **turn tutorial and reactive advice off** in the game's settings;
  - the great-cathedral upgrade alert (for clergy rulers): a small local mod that turns the alert off removes it, and the cathedral decision itself still works from the decisions screen.
- **Portraits.** Portraits on screen are recalculated every 30 frames, paused or not. A character window with a large family kept dozens rebuilding and froze for over half a second in every five. A mod that overrides `common/defines/jomini/portraits.txt` with a larger `PORTRAIT_CACHE_EXPIRE_FRAMES` (600 was tried) cut that about tenfold.

[Updating a save](docs/updating-a-save.md#performance-after-updating-a-large-save) has the details.

## Mods known to misbehave in 1.20

- **Better Barbershop** (Workshop 2220326926) replaces the barbershop and interaction-menu windows, and in 1.20 the barbershop then shows no characters. Disabling it brings the built-in barbershop back.

## Documentation

The [documentation guide](docs/README.md) groups these pages by what you are trying to do. It is also the front page of [the project's site](https://djdarcy.github.io/ck3-save-updater/).

- [Updating a save](docs/updating-a-save.md): the whole process, `status` then `update`, and doing it by hand.
- [Glossary](docs/glossary.md): every term the tool uses, and every header `status` prints.
- [The reference save](docs/reference-save.md): making a save at your campaign's date, with `reference-mod`.
- [Troubleshooting](docs/troubleshooting.md): what the common messages mean and what to do.
- [Configuration](docs/config.md): the settings file and the environment variables.
- [Options](docs/options.md): the most used options.
- [Rules](docs/rules.md): every built-in rule, what it changes and why.
- [New-map regions](docs/new-map-regions.md): how the regions 1.20 added are brought in.
- [Checking a save](docs/lint.md): what `lint` checks.
- [Output and verbosity](docs/output-and-verbosity.md): `-v`, `-q`, `--show`.
- [Reports](docs/reports.md): what the report beside each output contains.
- [Differences from the game](docs/differences-from-the-game.md): where the tool deliberately does something other than the game's own conversion.
- [Writing a patch](docs/writing-a-patch.md): your own fixes, as `patch.toml` files in your packs folder.
- [gamediff](docs/gamediff.md): what a game update changed, and what of it your save uses.
- [soak](docs/soak.md): load a save in the game and watch it (this one starts the game).
- [Tools](docs/tools.md): `ck3update tools` lists and runs the project's standalone scripts.
- [Thinning a save's population](docs/thin-population.md): a diagnostic copy of a save with fewer characters.
- [Platform support](docs/platform-support.md): what the tool is tested on.

## Contributing

Contributions are welcome (see [CONTRIBUTING.md](CONTRIBUTING.md) for details about bug reports, feature requests, and pull requests). To help work on the code:

```bash
git clone https://github.com/djdarcy/ck3-save-updater.git
cd ck3-save-updater
pip install -e ".[dev]"
pytest
```

Like the project?

 [!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/djdarcy)

## License

ck3-save-updater, Copyright (C) 2026 Dustin Darcy

Licensed under the GNU General Public License v3.0 or later (GPL-3.0-or-later) -- see [LICENSE](LICENSE).
