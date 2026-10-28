# Updating a save: the everyday flow

This page walks a player through bringing an old Crusader Kings III save forward to the game version installed now, using the commands as they ship today. The tool never changes the save you give it: every step writes a new file beside it.

## Before you start

- Install: `pip install ck3-save-migrator` (Python 3.10 or newer). The command is `ck3-save-migrator`. A shorter command name, `ck3update`, and the PyPI name `ck3-save-updater` are planned.
- Find three things on your machine:
  - **your save**, under `Documents\Paradox Interactive\Crusader Kings III\save games\`;
  - **the game folder** of the version you play now, for example `...\steamapps\common\Crusader Kings III\game`;
  - for a save from before the 2023-2024 map rework (1.8 to 1.12 era), **a save written by the new game at your campaign's date** (the "reference"; see the reference-save guide) and, if you have it, **the old game's `game` folder** (from Steam's betas).
- Save names below are placeholders: `My_Old_Campaign.ck3`.

## 1. Look at the save

```
ck3-save-migrator inspect My_Old_Campaign.ck3
```

Shows the version the save was written by, its mods and its size. Nothing is written.

## 2. See what it needs

```
ck3-save-migrator check My_Old_Campaign.ck3
```

Lists every rule (patch) with its verdict on this save: `needed` (and how many edits), `done`, `unknown` (rules written as code: only running them tells), or `fails`. Nothing is written. Exit code 5 means a patch would fail; the line names it.

`ck3-save-migrator rules` lists the rules with what each does.

## 3. Migrate

The everyday command, with the default rules:

```
ck3-save-migrator migrate My_Old_Campaign.ck3 --game-dir "<game folder>" -o My_Old_Campaign__updated.ck3
```

For a save from before the map rework, add the new-map rules and the two extra folders:

```
ck3-save-migrator migrate My_Old_Campaign.ck3 --rules all,R14,R15,R16 ^
    --reference Reference_At_My_Date.ck3 --game-dir "<game folder>" --old-game-dir "<old game folder>" ^
    -o My_Old_Campaign__updated.ck3 --report My_Old_Campaign.report.json
```

(`^` continues a line in cmd.exe; use a backtick in PowerShell and `\` in bash.) The report lists every change and why. `migrate` ends by linting its output (step 4).

Choosing rules:
- `--rules all,-R21` or `--rules -R21` leaves one out for this run (coming in the next version);
- `ck3-save-migrator disable R21` leaves it out of `--rules all` from now on (`enable R21` undoes it; `disabled` lists them). Naming a rule in `--rules` still runs it.

## 4. Check the result before loading it

```
ck3-save-migrator lint My_Old_Campaign__updated.ck3 --game-dir "<game folder>"
```

Errors are things the game is known to crash or refuse on; warnings are things old campaigns carry and play with. Exit code 4 means an error was found.

## 5. Load it

Copy the updated save into the save games folder, open the launcher with the mods the save names (the report and `inspect` list them), and load it. Mods made for an older game version can break windows (character, court, tooltips) without touching the save itself: if a window looks wrong, disable the mods that replace that window first.

A command that loads a save in the game, lets it run, and exits through Exit to Desktop (`soak`) is coming.

## When the game updates again

- `gamediff <old game folder> <new game folder> --save My_Campaign.ck3` (coming) lists what the update changed and what your save uses of it: the starting point for a new patch.
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
