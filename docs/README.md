# ck3-save-updater documentation

ck3-save-updater brings an old Crusader Kings III save up to the game version you have installed. These pages explain how to use it and what it does. New here? Start with the [Quick start](https://github.com/djdarcy/ck3-save-updater#quick-start) in the main README.

## Updating a save

- [Updating a save](updating-a-save.md): the whole process, from `status` to `update`, and how to do it by hand.
- [The reference save](reference-save.md): how to make a new game on your campaign's date, with `reference-mod`.
- [Glossary](glossary.md): every term the tool uses, and every header `status` prints.

## Settings and options

- [Options](options.md): the options you will use most.
- [Configuration](config.md): the settings file and the environment variables.
- [Output and verbosity](output-and-verbosity.md): `-v`, `-q` and `--show`.

## When something looks wrong

- [Troubleshooting](troubleshooting.md): what the common messages mean, and what to do about them.
- [Checking a save](lint.md): what `lint` checks before you load an updated save.
- [Reports](reports.md): what the report beside each updated save contains.
- [Differences from the game](differences-from-the-game.md): where the tool deliberately does something other than the game's own conversion.

## How it works

- [Rules](rules.md): every built-in rule, what it changes, and why.
- [New-map regions](new-map-regions.md): how the regions the 1.20 map added are brought into an older save.
- [Platform support](platform-support.md): what the tool is tested on.

## Your own fixes

- [Writing a patch](writing-a-patch.md): your own fixes, as `patch.toml` files in your packs folder.

## Advanced tools

- [gamediff](gamediff.md): what a game update changed, and which of those changes your save uses.
- [soak](soak.md): load a save in the game and watch it run. This one starts the game.
- [Tools](tools.md): `ck3update tools` lists and runs the project's standalone scripts.
- [Thinning a save's population](thin-population.md): a diagnostic copy of a save with fewer characters.

## Project

- [Download and install statistics](stats/): updated daily.
- [CHANGELOG](https://github.com/djdarcy/ck3-save-updater/blob/main/CHANGELOG.md): what each release changed.
- [The project on GitHub](https://github.com/djdarcy/ck3-save-updater): issues, discussions and the source.