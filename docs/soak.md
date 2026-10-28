# soak: load a save in the game and watch it

**`soak` starts Crusader Kings III.** It loads a save in the game, lets it run, closes it through the game's own Exit to Desktop, and tells you how that went: a clean exit, a crash on exit, a crash while running, a save that did not load, or a game that did not close. Use it on a migrated save before you play it, to see that it loads, runs and exits.

It runs on Windows, where it presses keys in the game window and clicks its Exit to Desktop button. It takes over the game for the length of the run: do not play while it runs.

## Using it

```bash
ck3-save-migrator soak "My_Old_Campaign.migrated.ck3"
ck3-save-migrator soak "My_Old_Campaign.migrated.ck3" --minutes 30 --speed 3 --mods mod/ugc_2220098919.mod
```

| Option | What it does |
|---|---|
| `--game <folder>` | the CK3 install folder, the one holding `binaries` and `game` (default: found from `CK3_GAME_DIR` or the usual Steam paths) |
| `--docs <folder>` | the game's documents folder (default: `Documents\Paradox Interactive\Crusader Kings III`; give it if your Documents folder is elsewhere, for example in OneDrive) |
| `--minutes N` | how long the game runs once it is in game (default 10) |
| `--exit-after SECONDS` | the same in seconds; overrides `--minutes` |
| `--speed 1..5` | the game speed (default 5) |
| `--mods <descriptor> ...` | enable exactly these mods for the run, e.g. `mod/ugc_2220098919.mod` |
| `--run-dir <folder>` | where the run's files go (default: a new folder in the tool's cache folder) |

## What it does

1. **It refuses to start** if another soak is running (a lock file in the tool's cache folder), if the game is already running, if the save's staging name (below) is taken by a different file, or if a mod you named has no descriptor. A refused soak changes nothing.
2. **It backs up your autosaves.** Every `autosave*.ck3` in your save folder is copied into the run folder with its checksum. A long run makes the game write its yearly autosave, which would otherwise replace yours.
3. **It backs up `dlc_load.json`**, the file that says which mods the game loads. With `--mods` it then lists exactly those mods in it for this run.
4. **It stages the save.** The save is copied into your save folder as `MIGRATE_TEST__<name>.ck3`, so the game can load it, and the game is started with `-debug_mode -loadsave=MIGRATE_TEST__<name>.ck3`.
5. **It runs the game.** It watches the game's logs. Once the game is in game, it presses space (to unpause) and the speed key. If the date in the corner stops moving, it presses space once; the game pauses itself for some messages.
6. **It closes the game.** After the time you gave, it closes the window, which opens the game's Exit Game dialog, and clicks Exit to Desktop. If the game is still running 25 seconds later, it clicks again with the real mouse. If the game has not closed after two minutes, it is stopped and the result is "did not exit".
7. **It puts everything back, however the run ended**, even when the game crashed or the soak itself failed:
   - it stops the game if it still runs;
   - every autosave the game changed gets your copy back (the game's version is kept in the run folder);
   - autosaves the game made are moved into the run folder;
   - the staged save is removed;
   - `dlc_load.json` gets its original bytes back.

   Each of these is checked and reported. If one cannot be verified, the command says so and exits with code 8, and the originals are in the run folder.

Nothing else is written into your documents or save folders. The run folder holds the backups, a timeline of what happened, a copy of the game's logs and of any crash folder the run produced.

## What it reports

```
soak: crash on exit (Exception during shutdown: heap corruption)
  autosave autosave.ck3: put back and verified
  dlc_load.json: put back and verified
  run folder: ...
```

| Result | Meaning | Exit code |
|---|---|---|
| clean exit | the game closed through Exit to Desktop and wrote no crash folder | 0 |
| crash on exit | the game wrote a crash folder after the close; the first line of its `exception.txt` is shown | 6 |
| crash while running | the game crashed, or ended, before the close | 6 |
| did not load | the game logged that it could not load the save, or was not in game after 15 minutes | 7 |
| did not exit | the game was still running two minutes after the close, and was stopped | 7 |
| (refused) | another soak, a running game, a taken staging name or an unknown mod | 2 |
| (a check failed) | an autosave or `dlc_load.json` could not be verified after the run | 8 |

## Where it comes from

`soak` is the project's own test harness, `tests/one-offs/launch_load_test.py`, made into a command. The harness's window functions are copied into `ck3_save_migrator/soak.py` unchanged, and a test checks that they stay the same. The harness itself is left as it is.
