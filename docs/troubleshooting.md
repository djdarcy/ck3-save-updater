# Troubleshooting

What the common messages mean and what to do about them. The exit codes are listed in [Checking a save](lint.md#exit-codes).

## "ck3update is not recognized"

```
'ck3update' is not recognized as an internal or external command
```

pip installed the command, but into a folder your shell does not search. This is common on Windows after `pip install --user ck3-save-updater`: the command lands in a per-user `Scripts` folder that Windows never adds to PATH, and pip warns about it only once. Run:

```bash
python -m ck3_save_migrator setup
```

This works whatever PATH holds, because it starts the tool through Python itself. It says where the command was installed and whether that folder is on PATH. On Windows it offers to add the folder to your user PATH (a backup of the old value is kept), and you then open a new terminal. With `--dry-run` it prints what it would do and changes nothing in PATH or the registry; on some terminals it still writes small helper scripts (`ck3update-path.cmd`, `.ps1`, `.sh`) to your temp folder. With `--yes` it changes PATH without asking. Inside a virtual environment it tells you to activate the environment instead; on Linux and macOS it prints the line to add to your shell's profile. Until then, `python -m ck3_save_migrator <command> ...` runs any command, `python -m ck3_save_migrator update "My_Old_Campaign"` included.

## "output already exists"

```
ERROR: output already exists: My_Old_Campaign.migrated.ck3 (use --force to overwrite)
```

An earlier run already wrote this output (exit code 2). Delete or rename it, choose another name with `-o`, or pass `--force` to overwrite it.

`--force` only lifts this refusal. The tool never overwrites the save it reads, also when the output path is a second name for it (a hard link, a junction or a mapped drive); that is refused with "refusing to write over the input file" (exit code 2) whatever the flags.

## "nothing to write"

```
nothing to write: 15 rules ran and edited 0 (matched 2); the save is already migrated, or nothing in it matched
```

No selected rule changed anything, so no file was written (exit code 0). This is what updating an already updated save gives, and it is safe: the save is left as it is. `--force` does not change it. If you expected changes, check that you gave the old save, not an updated one, and read each rule's line: a rule that could not run says why there (for example "no reference save (--reference)").

## "rule prerequisites missing"

```
ERROR: rule prerequisites missing: R14 needs R8 (add them, or use --rules all,R14,R15,R16 for the full migration with the transplant)
```

Some rules use what an earlier rule did, and a selection without those rules is refused before the save is read (exit code 1). Add the rules named, or start from `all`: `--rules all,R15,R14,R16` is never refused for this reason. The table of what each rule needs is in [Rules](rules.md#prerequisites).

## "lint found ... error(s)" (exit code 4)

```
ERROR: lint found 3 error(s) in the output; it was written so it can be inspected (see the lint lines above)
```

The checks run on every output found something the game reads by number that is broken. The output was still written, so it can be inspected, but treat it as not ready to load. The `ERROR` lines above the message name each failed check with examples, and the same findings are in `<output>.lint.json`. An update that runs its rules to the end should not produce errors; an error usually means a rule did not finish its job, which is worth reporting with the `.lint.json` attached. See [Checking a save](lint.md).

## The game shows generic faces

Faces are stored in the save as portrait data (DNA). `lint` reports portrait data in an older format than the current game writes as "Unexpected DNA string length"; how those faces then look has not been checked yet. Portrait genes added by mods are not handled yet either, so characters may not look as they did.

What helps: load the updated save with the same portrait mods the old save used, since portraits need them. And a save stores faces only for some characters, so not every face can be carried over from it.

## The Way of Scarcity, or another custom faith, is missing

A custom faith is carried by R10, which needs the religion rules and so a reference save (`--reference`); without one, R8 to R12 do nothing and say so. With a reference, the custom faith is carried in the shape `--wos-shape` chooses: as a faith of its own (`faith`), or as a rite of the faith its template now belongs to (`rite`). The default, `both`, writes two outputs, `<name>__wos-faith.migrated.ck3` and `<name>__wos-rite.migrated.ck3`; load the one you want. In the `rite` shape you find the custom faith as a rite, under the faith its template now belongs to. See [Rules](rules.md).

## R15 "needs --old-game-dir"

```
R15 dead-titles  matched 0  edited 0  (needs --old-game-dir (the save's own version's game folder) and --game-dir)
```

R15 finds what the 1.20 map calls the land of your save's removed or moved titles by reading two maps: the current game's and the one of the version your save was made with. Pass `--old-game-dir` with the `game` folder of that older version (and `--game-dir` if the current game is not found by itself). The rest of the update still runs without it. See [New-map regions](new-map-regions.md).

## The reference save is from a different date

The new-map rules copy the new regions' world from the reference as it is on the reference's date. A reference from another date brings rulers and families from the wrong moment into your campaign. Nothing refuses it, because the tool cannot tell which date you meant. Make a reference at your campaign's own date: [The reference save](reference-save.md) explains how, with `ck3update reference-mod`.
