# Updating a save: the everyday flow

This page walks a player through bringing an old Crusader Kings III save forward to the game version installed now, using the commands as they ship today. The tool never changes the save you give it: every step writes a new file beside it.

## Before you start

- Install: `pip install ck3-save-updater` (Python 3.10 or newer). The command is `ck3update`. The project's old name, `ck3-save-migrator`, still works as a second name for the same command for now.
- Know three things on your machine:
  - **your save**: give its path, or just its name (with or without `.ck3`) and the tool looks in the game's `save games` folder: on Windows under your Documents folder wherever Windows keeps it (also when it is moved to OneDrive), on Linux under `~/.local/share/Paradox Interactive/Crusader Kings III/`, on macOS under `~/Documents/Paradox Interactive/Crusader Kings III/`;
  - **the game folder** of the version you play now: found by itself through Steam's own records (every Steam library, on any drive), Steam's usual folders, a `SteamLibrary` or `Steam` folder at the root of a drive, an Xbox app (Game Pass) install in `XboxGames` on a drive the Xbox app installs to (not yet checked against a real Game Pass install), or the current folder. `ck3update inspect` lists every install it finds, with where it found it and its version; when there are several, the newest is used. Give `--game-dir <...\Crusader Kings III\game>` (or set `CK3_GAME_DIR`) to choose one;
  - for a save from before the 2023-2024 map rework (1.8 to 1.12 era), **a save written by the new game at your campaign's date** (the "reference"; see the reference-save guide) and, if you have it, **the old game's `game` folder** (from Steam's betas).
- Save names below are placeholders: `My_Old_Campaign.ck3`.

## The short way: status, then update

```
ck3update status My_Old_Campaign
ck3update update My_Old_Campaign --dry-run
ck3update update My_Old_Campaign
```

`status` prints the plan and writes nothing:

- the save (its versions, date and mods) and the game it will be brought to (the install used, and the others found);
- the gap between the two versions. The packs are chosen by it: each pack may say which saves and games it is for (`[applies]` in its `pack.toml`), and the built-in pack is for saves from 1.8 to before 1.20 going to a 1.20 game. A gap no selected pack covers is named, and nothing is written;
- every pack and patch, in the order they run, with whether each runs and why not (turned off, not trusted, not selected by `--rules`, or needing a reference save or the old game folder that is not there);
- the reference save: given with `--reference`, named by `CK3_REFERENCE_SAVE`, or found in the save folder: a save written by the game's version on the save's date. It never picks a save that descends from yours (one this tool wrote, or one you made by playing an updated save), and when two saves could each be the reference it asks you to choose one with `--reference`. With none, it lists the rules that will skip and the steps to make a reference. It is looked for only when a patch that will run needs one: an up-to-date save needs none, and says "not needed";
- what each of your run patches still needs (`needs --var <name>`, with its help), and whether one is already done (its done check), so a patch that cannot run, or has run, is skipped before anything starts;
- the new-map transplant: a save from before the 1.13 map rework going to a 1.20 game loads only with R14-R17. `--transplant auto` (or `transplant = "auto"` in the config file) selects them when a reference is present, and says the save needs one when it is not; without the switch, the plan says how to add them;
- the output: `<name>__updated__<game version>.ck3` beside the save (`-o` for another).

A save one hotfix behind the game (1.20.1.2 with a 1.20.1.3 game) is "already current": the same 1.20 line is assumed compatible, and the plan says so. `ck3update help <rule, patch or pack>` explains any one of them.

`update --dry-run` runs every patch in memory and prints the same plan with each patch's counts; it writes nothing. `update` runs the plan `status` printed, writes the output and `<output>.report.json` beside it (the plan and the counts). An output that exists is refused without `--force`. A save already at the game's version, with no pack selected for it, is "already current": nothing is written. `update` takes `migrate`'s options for the rules (`--rules`, `--wos-shape`, `--portraits-version`, `--old-game-dir`) and exits with the same codes.

### The record of a save game

A campaign is updated more than once: a later save of the same ruler, or the next game version. Every save of one campaign carries the same `random_seed` in its gamestate, so after each successful `update` the tool adds a row to that campaign's record, `games/<random_seed>.toml` in the config folder (beside `config.toml`; `CK3SM_CONFIG` moves both). `--dry-run`, `status` and `migrate` never write one.

The record's `label` is the file name of the first save updated (later updates keep it). Each `[[update]]` row holds:

- the date;
- the input and output files with their sha256;
- the tool version and the game version;
- the patches that ran (id and pack);
- the inputs it used: `--var` values (qualified names as given), `--old-game-dir`, `--transplant`, `--wos-shape` and `--portraits-version`.

A reference save is never recorded, since it belongs to one date, and no part of any save is. A save whose `random_seed` cannot be read gets no record, and the plan says so.

`status` and `update` read the record back:

```
record    My_Old_Campaign: last updated 2026-11-01 14:02 by ck3-save-updater 0.3.17 from My_Old_Campaign.ck3 (1 update)
pre-filled: --var witness=W1 (from the record of My_Old_Campaign)
```

Any input you do not give this time takes the record's latest value; anything you give wins. A recorded folder or file that no longer exists is not used: the plan says the recorded value was missing, and a step that needs it is skipped with its usual "needs" reason. `--no-record` (on `status` and `update`) neither reads nor writes the record.

### Updating in place

`update --in-place` gives the updated save the original's name and keeps the original as `<name>.bak.ck3`:

1. The output is written to a temporary name in the same folder and verified, as any output is.
2. The original is renamed to `<name>.bak.ck3`.
3. The output is renamed to `<name>.ck3`.

If the last rename fails, the first is undone: the original keeps its own name, and the run exits 1 naming both files. An existing `.bak.ck3` is refused (exit 2) unless you give `--force`. The report is `<name>.report.json`. `--in-place` does not take `-o`. A custom faith with no `--wos-shape` gives two outputs, so in place needs `--wos-shape faith` or `rite` (or one in the record). Without `--in-place`, the output is still `<name>__updated__<game version>.ck3`.

The steps below are the same flow done by hand, with `migrate`, the lower-level command `update` runs.

## 1. Look at the save

```
ck3update inspect My_Old_Campaign.ck3
```

Shows the version the save was written by (`version`, `save_game_version`, `portraits_version`), its mods and its size, and the game installs found with their versions. Nothing is written. `migrate` refuses a save written by a newer game version than the game it uses, naming both versions; when it cannot read the game's version, it says so and goes on.

## 2. See what it needs

```
ck3update check My_Old_Campaign.ck3
```

Lists every rule (patch) with its verdict on this save: `needed` (and how many edits), `done`, `unknown` (rules written as code: only running them tells), or `fails`. Nothing is written. Exit code 5 means a patch would fail; the line names it.

`ck3update rules` lists the rules with what each does.

## 3. Migrate

The everyday command, with the default rules:

```
ck3update migrate My_Old_Campaign.ck3 --game-dir "<game folder>" -o My_Old_Campaign__updated.ck3
```

For a save from before the map rework, add the new-map rules and the two extra folders:

```
ck3update migrate My_Old_Campaign.ck3 --rules all,R14,R15,R16 ^
    --reference Reference_At_My_Date.ck3 --game-dir "<game folder>" --old-game-dir "<old game folder>" ^
    -o My_Old_Campaign__updated.ck3 --report My_Old_Campaign.report.json
```

(`^` continues a line in cmd.exe; use a backtick in PowerShell and `\` in bash.) The report lists every change and why. `migrate` ends by linting its output (step 4).

The update is reproducible: the same save and the same options give the same result every time. A `.ck3` file is a zip that records when each file inside it was written, so two runs give files with different bytes but the same content; compare saves by their content (`ck3update inspect`), not by the files' bytes.

Choosing rules:
- `--rules all,-R21` or `--rules -R21` leaves one out for this run;
- `ck3update disable R21` leaves it out of `--rules all` from now on (`enable R21` undoes it; `disabled` lists them). Naming a rule in `--rules` still runs it.

## 4. Check the result before loading it

```
ck3update lint My_Old_Campaign__updated.ck3 --game-dir "<game folder>"
```

Errors are things the game is known to crash or refuse on; warnings are things old campaigns carry and play with. Exit code 4 means an error was found.

## 5. Load it

Copy the updated save into the save games folder, open the launcher with the mods the save names (the report and `inspect` list them), and load it. Mods made for an older game version can break windows (character, court, tooltips) without touching the save itself: if a window looks wrong, disable the mods that replace that window first. The mods known to misbehave in 1.20 are listed below.

`ck3update soak My_Old_Campaign__updated.ck3` starts the game, loads the save, lets it run, exits through Exit to Desktop and says whether that went cleanly ([soak](soak.md)).

## Performance after updating a large save

A large updated campaign can stutter in 1.20.1.2 where a new game with the same mods does not. Both causes below were measured on the founding campaign on 2026-10-28. Both are the game's own 1.20.1.2 behaviour, which a big updated save makes visible, and both have workarounds.

### Top-bar alerts checked one at a time

The game re-checks the player's top-bar alerts one at a time, even while paused. On this save two vanilla alerts each cost about 0.55 seconds per check, and together they froze the game every 2 to 3 seconds:

- **The tutorial advice for great projects** (`action_reactive_advice_great_projects`): turn tutorial and reactive advice off in the game's settings, and it is gone.
- **The great-cathedral upgrade alert** for clergy rulers (`action_can_upgrade_great_cathedral`): a small local mod that turns this alert off removes it. The cathedral decision itself still works from the decisions screen.

### Portraits recalculated every 30 frames

Portraits on screen are recalculated every 30 frames, paused or not; the number is `PORTRAIT_CACHE_EXPIRE_FRAMES` in `common/defines/jomini/portraits.txt`. A character window with a large family keeps dozens of portraits rebuilding, and froze the game for 0.5 to 0.7 seconds in every 5.

Overriding that file in a mod with a value of 600 cut the freezes about tenfold. The mod must override `common/defines/jomini/portraits.txt` itself: a define file elsewhere in `common/defines/` did not take effect (checked by reading the value the running game was using).

### A performance mod

A packaged mod with these settings is planned. Until then, the settings change and the small local mods above are the workarounds.

## Mods known to misbehave in 1.20

- **Better Barbershop** (Workshop 2220326926) replaces the barbershop and interaction-menu windows, and in 1.20 the barbershop then shows no characters. Disabling it brings the built-in barbershop back.

## When the game updates again

- `ck3update gamediff <old game folder> <new game folder> --save My_Campaign.ck3` lists what the update changed and what your save uses of it: the starting point for a new patch ([gamediff](gamediff.md)).
- A new fix is a folder with a `patch.toml`. Run it with `migrate ... --pack <your folder>`; see [writing a patch](writing-a-patch.md). A pack that runs code (a script or a program) needs `--allow-run`.
- Your own scripts can be run unchanged as patches, or listed and run with `ck3update tools` ([tools](tools.md)).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | bad input (a missing file, a bad option) |
| 2 | refused by a guard (the output exists, or it would overwrite the input) |
| 3 | the written file failed its own verification; nothing was written |
| 4 | `lint` found an error |
| 5 | a patch failed (`migrate` writes nothing; `check` names it) |
