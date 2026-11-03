# Updating a save: the process...

This page walks a player through bringing an old Crusader Kings III save forward to the game version installed now: `ck3update status` to see what will happen, then `ck3update update` to do it. Words the tool coins are explained in the [glossary](glossary.md).

**The tool never launches the game, and never changes the save you give it** unless you ask for `--in-place`, and then only after keeping the original as `<name>.bak.ck3`. Every other result is a new file beside your save. (`ck3update soak` is the one command that starts the game; it is separate, and neither `status` nor `update` runs it.)

## Before you start

- Install: `pip install ck3-save-updater` (Python 3.10 or newer). The command is `ck3update`; the project's old name, `ck3-save-migrator`, still works as a second name for it. If your shell says `'ck3update' is not recognized`, run `python -m ck3_save_migrator setup` ([Troubleshooting](troubleshooting.md#ck3update-is-not-recognized)).
- Know where these are on your machine:
  - **your save**: give its path, or just its name (with or without `.ck3`) and the tool looks in the game's `save games` folder: on Windows under your Documents folder wherever Windows keeps it (also when it is moved to OneDrive), on Linux under `~/.local/share/Paradox Interactive/Crusader Kings III/`, on macOS under `~/Documents/Paradox Interactive/Crusader Kings III/`;
  - **the game folder** of the version you play now: found by itself through Steam's own records (every Steam library, on any drive), Steam's usual folders, a `SteamLibrary` or `Steam` folder at the root of a drive, an Xbox app (Game Pass) install in `XboxGames` on a drive the Xbox app installs to (not yet checked against a real Game Pass install), or the current folder. When there are several, the newest is used. Give `--game-dir <...\Crusader Kings III\game>` (or set `CK3_GAME_DIR`) to choose one;
  - **a [reference save](glossary.md#reference-save)**: a save written by the new game at your campaign's date. The religion rules rebuild religion from it, and for a save from before the [map rework](glossary.md#map-rework) (the 1.8 to 1.12 era) the new-map rules copy the new regions from it. [The reference save](reference-save.md) explains how to make one with `ck3update reference-mod`. If you have it, **the old game's `game` folder** too (from Steam's betas), for the new-map rule R15;
  - **your [packs folder](glossary.md#packs-folder)**, only for fixes of your own ([Your own packs folder](writing-a-patch.md#your-own-packs-folder)).
- Save names below are placeholders: `My_Old_Campaign.ck3`.

## 1. See what it will do: status

```
ck3update status My_Old_Campaign
```

`status` prints [the plan](glossary.md#plan) and writes nothing. Its first line is the verdict: [READY](glossary.md#ready), [ALREADY CURRENT](glossary.md#already-current), [NOTHING TO DO](glossary.md#nothing-to-do) or [REFUSED](glossary.md#refused). Below it come blocks, each under a header in capitals ([what each block holds](glossary.md#what-status-prints)):

- SAVE: the save, its versions, its date and its mods; GAME: the game it will be brought to (the install used; others found are listed under ALSO);
- RECORD: [the record](glossary.md#record) of this campaign, if it was updated before;
- GAP: the [gap](glossary.md#gap) between the two versions. The packs are chosen by it: each pack may say which saves and games it is for (`[applies]` in its `pack.toml`), and the built-in pack is for saves from 1.8 to before 1.20 going to a 1.20 game. A gap no selected pack covers is [NOT COVERED](glossary.md#covered-and-not-covered), and nothing is written;
- REFERENCE: the reference save: given with `--reference`, named by `CK3_REFERENCE_SAVE`, or found in the save folder (a save written by the game's version on the save's date). It never picks a save that [descends from](glossary.md#descends-from) yours, and when two saves could each be the reference it asks you to choose one with `--reference`. With none, it lists the rules that will skip and the steps to make a reference. It is looked for only when a patch that will run needs one; otherwise it says "not needed";
- PACKS and PATCHES: every [pack](glossary.md#pack) and [patch](glossary.md#patch), in the order they run, with whether each runs and why not (turned off, not trusted, not selected by `--rules`, needing a reference save or the old game folder that is not there, or needing a `--var` a [run patch](glossary.md#run-patch) names);
- DETECTORS: what the [detectors](glossary.md#detector) read, and how long it took;
- OUTPUT: the file `update` will write, `<name>__updated__<game version>.ck3` beside the save (`-o` for another);
- NOTES: anything else, such as a save that crosses the map rework.

Each built-in rule that will run is judged before anything runs, by its detector (the rule's own matcher, or the lint check that sees what it fixes). Its PATCHES row says [needed](glossary.md#needed) with a count (`needed: 851 nicknames without text`), [done](glossary.md#done) (`done: none found`), or [unknown](glossary.md#unknown) when its detector needs the game folder or a reference save. The detectors need the whole save: the plan reads it once and says how long it took (`--no-detect` skips it, and the plan reads only the save's first megabyte). A plan that is already refused does not read it at all ([fail early](glossary.md#fail-early)).

The [transplant](glossary.md#transplant): a save from before the 1.13 map rework going to a 1.20 game loads only with R14-R17. They are selected by default when a reference is present (`--transplant auto`, or `transplant = "auto"` in the config file), and the plan says the save needs one when it is not. A reference you name with `--reference` must be on the save's own date: on another date the plan refuses and says how to make the right one. `--transplant off` (or `transplant = "off"`) leaves them out; NOTES then says how to add them.

A save one [hotfix](glossary.md#hotfix) behind the game (1.20.1.2 with a 1.20.1.3 game) is ALREADY CURRENT: the same 1.20 [version line](glossary.md#version-line) is assumed compatible, and the plan says so. `ck3update help <rule, patch or pack>` explains any one of them. `--plain` prints the plan without colour, for pasting; [Configuration](config.md#display-how-the-plan-is-laid-out) says how to change its layout.

## 2. Update it

```
ck3update update My_Old_Campaign --dry-run
ck3update update My_Old_Campaign
```

`update --dry-run` runs every patch in memory and prints the same plan with each patch's counts; it writes nothing. `update` runs the plan `status` printed: it writes `<name>__updated__<game version>.ck3` beside the save, and `<output>.report.json` beside that (the plan and the counts), and checks the result with [lint](glossary.md#lint) before it finishes. An output that exists is refused without `--force`. `update` takes `migrate`'s options for the rules (`--rules`, `--wos-shape`, `--portraits-version`, `--old-game-dir`) and exits with the same codes (below).

Then copy the updated save into the save games folder (if it is not there already), open the launcher with the mods the save names (the report and `inspect` list them), and load it. Mods made for an older game version can break windows (character, court, tooltips) without touching the save itself: if a window looks wrong, disable the mods that replace that window first. The mods known to misbehave in 1.20 are listed below.

`ck3update soak My_Old_Campaign__updated__1.20.1.2.ck3` starts the game, loads the save, lets it run, exits through Exit to Desktop and says whether that went cleanly ([soak](soak.md)).

## When it refuses

A REFUSED plan ends with each reason, and a `fix:` line under it:

```
REFUSED: the gap 1.8.1 -> 1.21.0: no selected pack declares it covers it (a pack's [applies] span); nothing would bring
         the save to the game's version
  fix: a pack in your packs folder whose [applies] declares this span (docs/writing-a-patch.md), or `ck3update migrate`
       with the rules you choose
```

Do what the fix says, then run `status` again. Nothing is written while a plan is refused. [Troubleshooting](troubleshooting.md) covers the common messages.

## A save you already updated

A save already on the game's version line, which the built-in pack's span does not select (one you updated before, then played), is [re-checked](glossary.md#re-check): it skips what it already has and gets what is left. Each built-in rule is judged in turn:

- one the save game's record shows applied (an update of this save, or of one written before it) is skipped: `already applied (record: <date>)`;
- one whose detector finds nothing is skipped: `done: none found`;
- one whose detector finds something runs: `needed: 851 nicknames without text`. The verdict is READY, and `update` writes a new save as usual;
- one that cannot be judged (no detector, and not in the record) does not run: `unknown: not in the record and no detector; name it with --rules to run it`. The transplant (R14-R17) is never judged on such a save, so it runs there only when `--rules` names it. R6 (it only reports) and R7 (the version bump, which the same line does not need) run there only by name too.

`--rules` still selects (`--rules R23` runs R23 alone) and leaves out (`--rules all,-R23`). The re-check is skipped, and the save is not read past its first megabyte, when the record says this tool version, or a later one, updated it.

## The record of a save game

A campaign is updated more than once: a later save of the same ruler, or the next game version. Every save of one campaign carries the same `random_seed` (its [seed](glossary.md#seed)) in its gamestate, so after each successful `update` the tool adds a row to that campaign's record, `games/<random_seed>.toml` in the config folder (beside `config.toml`; `CK3SM_CONFIG` moves both). `--dry-run`, `status` and `migrate` never write one.

The record's `label` is the file name of the first save updated (later updates keep it). Each `[[update]]` row holds:

- the date;
- the input and output files with their sha256;
- the tool version and the game version;
- the patches that ran (id and pack);
- the inputs it used: `--var` values (qualified names as given), `--old-game-dir`, `--transplant`, `--wos-shape` and `--portraits-version`.

A reference save is never recorded, since it belongs to one date, and no part of any save is. A save whose `random_seed` cannot be read gets no record, and the plan says so.

`status` and `update` show the record in the RECORD block:

```
RECORD      status: My_Old_Campaign: last updated 2026-11-01 14:02 by ck3-save-updater 0.3.17 from My_Old_Campaign.ck3 (1 update)
        pre-filled: --var witness=W1
        pre-filled: --var tools_dir
                    D:/my ck3 tools/a folder whose path is longer than the line
                    (from the record of My_Old_Campaign)
```

One row per input; a value too long for the line, or a list, goes on its own lines under the value column; the record they came from is named once, after them.

Any input you do not give this time takes the record's latest value ([pre-filled](glossary.md#pre-filled)); anything you give wins. A recorded folder or file that no longer exists is not used: the plan says the recorded value was missing, and a step that needs it is skipped with its usual "needs" reason. `--no-record` (on `status` and `update`) neither reads nor writes the record.

## Updating in place

`update --in-place` gives the updated save the original's name and keeps the original as `<name>.bak.ck3`:

1. The output is written to a temporary name in the same folder and verified, as any output is.
2. The original is renamed to `<name>.bak.ck3`.
3. The output is renamed to `<name>.ck3`.

If the last rename fails, the first is undone: the original keeps its own name, and the run exits 1 naming both files. Only a clean run is put in place: when lint finds an error (exit 4), the original is left as it is and the output is written to `<name>__updated__<game version>.ck3` for inspection, with its lint file and report beside it. An existing `.bak.ck3` is refused (exit 2) unless you give `--force`. The report is `<name>.report.json`. `--in-place` does not take `-o`. A custom faith with no `--wos-shape` gives two outputs, so in place needs `--wos-shape faith` or `rite` (or one in the record). Without `--in-place`, the output is still `<name>__updated__<game version>.ck3`.

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
- A new fix is a folder with a `patch.toml`. Put its pack in your packs folder, or run it with `migrate ... --pack <your folder>`; see [writing a patch](writing-a-patch.md). A pack that runs code (a script or a program) runs once you [trust](glossary.md#trusted-pack) it, or with `--allow-run`.
- Your own scripts can be run unchanged as patches, or listed and run with `ck3update tools` ([tools](tools.md)).

## Doing it by hand

`update` runs `migrate`, the lower-level command, with the rules its plan chose. The same flow can be done step by step.

**Look at the save.** `ck3update inspect My_Old_Campaign.ck3` shows the version the save was written by (`version`, `save_game_version`, `portraits_version`), its mods and its size, and the game installs found with their versions. Nothing is written. `migrate` refuses a save written by a newer game version than the game it uses, naming both versions; when it cannot read the game's version, it says so and goes on.

**See what it needs.** `ck3update check My_Old_Campaign.ck3` lists every rule (patch) with its verdict on this save: `needed` (and how many edits, or how many of what the rule fixes), `done`, `unknown` (a code or run patch: only running it tells; or a rule whose detector needs the game folder or a reference save), or `fails`. Nothing is written. Exit code 5 means a patch would fail; the line names it. `ck3update rules` lists the rules with what each does.

**Migrate.** The everyday command, with the default rules:

```
ck3update migrate My_Old_Campaign.ck3 --game-dir "<game folder>" -o My_Old_Campaign__updated.ck3
```

For a save from before the map rework, add the new-map rules and the two extra folders:

```
ck3update migrate My_Old_Campaign.ck3 --rules all,R14,R15,R16 ^
    --reference Reference_At_My_Date.ck3 --game-dir "<game folder>" --old-game-dir "<old game folder>" ^
    -o My_Old_Campaign__updated.ck3 --report My_Old_Campaign.report.json
```

(`^` continues a line in cmd.exe; use a backtick in PowerShell and `\` in bash.) The report lists every change and why. `migrate` ends by linting its output.

The update is reproducible: the same save and the same options give the same result every time. A `.ck3` file is a zip that records when each file inside it was written, so two runs give files with different bytes but the same content; compare saves by their content (`ck3update inspect`), not by the files' bytes.

Choosing rules:
- `--rules all,-R21` or `--rules -R21` leaves one out for this run;
- `ck3update disable R21` leaves it out of `--rules all` from now on (`enable R21` undoes it; `disabled` lists them). Naming a rule in `--rules` still runs it.

**Check the result before loading it.** `ck3update lint My_Old_Campaign__updated.ck3 --game-dir "<game folder>"`. Errors are things the game is known to crash or refuse on; warnings are things old campaigns carry and play with. Exit code 4 means an error was found.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done |
| 1 | bad input (a missing file, a bad option), or a refused plan |
| 2 | refused by a guard (the output exists, or it would overwrite the input) |
| 3 | the written file failed its own verification; nothing was written |
| 4 | `lint` found an error |
| 5 | a patch failed (`migrate` writes nothing; `check` names it) |
