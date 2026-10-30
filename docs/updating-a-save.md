# Updating a save: the everyday flow

This page walks a player through bringing an old Crusader Kings III save forward to the game version installed now, using the commands as they ship today. The tool never changes the save you give it: every step writes a new file beside it.

## Before you start

- Install: `pip install ck3-save-updater` (Python 3.10 or newer). The command is `ck3update`. The project's old name, `ck3-save-migrator`, still works as a second name for the same command for now.
- Know three things on your machine:
  - **your save**: give its path, or just its name (with or without `.ck3`) and the tool looks in the game's `save games` folder: on Windows under your Documents folder wherever Windows keeps it (also when it is moved to OneDrive), on Linux under `~/.local/share/Paradox Interactive/Crusader Kings III/`, on macOS under `~/Documents/Paradox Interactive/Crusader Kings III/`;
  - **the game folder** of the version you play now: found by itself through Steam's own records (every Steam library, on any drive), Steam's usual folders, a `SteamLibrary` or `Steam` folder at the root of a drive, an Xbox app (Game Pass) install in `XboxGames` on a drive the Xbox app installs to (not yet checked against a real Game Pass install), or the current folder. `ck3update inspect` lists every install it finds, with where it found it and its version; when there are several, the newest is used. Give `--game-dir <...\Crusader Kings III\game>` (or set `CK3_GAME_DIR`) to choose one;
  - for a save from before the 2023-2024 map rework (1.8 to 1.12 era), **a save written by the new game at your campaign's date** (the "reference"; see the reference-save guide) and, if you have it, **the old game's `game` folder** (from Steam's betas).
- Save names below are placeholders: `My_Old_Campaign.ck3`.

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
- Your own scripts can be run unchanged as patches, or listed and run with the optional `tools` add-on ([tools](tools.md)).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | bad input (a missing file, a bad option) |
| 2 | refused by a guard (the output exists, or it would overwrite the input) |
| 3 | the written file failed its own verification; nothing was written |
| 4 | `lint` found an error |
| 5 | a patch failed (`migrate` writes nothing; `check` names it) |
