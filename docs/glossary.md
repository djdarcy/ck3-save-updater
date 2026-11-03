# Glossary

The words this tool uses that a Crusader Kings III player may not know, or that mean something narrower here than they do elsewhere. Each entry says where you meet the word. Words in capitals are what `ck3update status` and `ck3update update` print: the verdict on the first line, then one block per header.

## Saves and versions

### reference save

A save written by the game you have now, used as a source: the religion rules (R8 to R12) rebuild religion from it, and the new-map rules (R14 to R17) copy the regions the new map added from it. For the new regions it should be a new game started on your campaign's own date. You meet it in the REFERENCE block of `status`, which says which save was chosen, or which rules skip without one and how to make one ([The reference save](reference-save.md)).

### map rework

The game's map was redrawn between 1.12 and 1.13: lands moved, provinces were added and some became impassable. A save from before it needs [the transplant](#transplant) to load in a 1.20 game. `status` names it in NOTES: "this save crosses the 1.13-1.20 map rework".

### transplant

The new-map rules (R14 to R17), which bring the regions the [map rework](#map-rework) added into an older save, with their rulers, courts and families copied from the [reference save](#reference-save). They are opt-in: name them with `--rules all,R14,R15,R16`, or give `--transplant auto` (or `transplant = "auto"` in the config) and `update` selects them when a save crosses the rework and a reference is present. In PATCHES they show as `opt-in: not in --rules` until selected ([New-map regions](new-map-regions.md)).

### seed

The `random_seed` a game writes into every save. A campaign keeps it from its first save to its last, and this tool keeps it, so it ties together all the saves of one campaign. SAVE shows it as `seed`; [the record](#record) is kept by it, and a [pack's campaign scope](#campaign-scope) names it.

### descends from

A save descends from another when it was made from it: this tool's output, or a save you made by playing an updated save. Such a save has the same [seed](#seed). The tool never picks one as the [reference save](#reference-save), since it would be a copy of the campaign itself rather than a fresh game.

### zz_ref bookmark mod

The small local mod `ck3update reference-mod` writes, named `zz_ref_<date>`, which adds a bookmark on your campaign's date so the game can start a new game there. When two saves could each be the reference, one whose mods name a `zz_ref` mod for the save's date is preferred ([The reference save](reference-save.md)).

### version line

A game version's first two numbers: 1.20.1.2 is on the 1.20 line. A save and a game on the same line are treated as compatible.

### hotfix

A release that changes only the numbers after the [version line](#version-line), such as 1.20.1.2 to 1.20.1.3. A save one hotfix behind the game is ALREADY CURRENT: no update is needed.

### gap

The step from the save's version to the game's, shown in GAP as `versions: 1.8.1 -> 1.20.1.2`. Packs are chosen by it.

### covered and NOT COVERED

A gap is covered when a selected [pack](#pack) declares that it brings saves of the save's version to the game's version. When none does, GAP says `NOT COVERED`, the plan is REFUSED, and nothing is written: nothing would bring the save to the game's version.

## Fixes: packs, patches and rules

### pack

A folder of [patches](#patch) with a `pack.toml` that says which saves and games it is for. The built-in pack, `to_1_20`, is for saves from 1.8 up to 1.20 going to a 1.20 game. PACKS lists every pack found and whether it was selected for this save and game.

### patch

One fix in a [pack](#pack): a folder with a `patch.toml`. Each row of PATCHES is one patch, with whether it runs and why ([Writing a patch](writing-a-patch.md)).

### rule

A patch of the built-in pack, named by an id and a name (`R23 nickname-text`). `ck3update rules` lists them, `--rules` chooses them, and `ck3update disable <id>` turns one off ([Rules](rules.md)).

### declarative patch

A [patch](#patch) made only of edits written in its `patch.toml` (rename this, delete that, at these paths). It runs no code, so it runs without being trusted, and the tool can tell beforehand exactly what it would change.

### run patch

A [patch](#patch) that runs a program or a Python script of its own on a copy of the save. It is code, so it runs only from a [trusted pack](#trusted-pack) (or with `--allow-run`). A run patch can name the inputs it needs (`needs --var tools_dir`), and PATCHES says when one is missing.

### packs folder

The folder for your own packs: `packs` beside the config file (`%APPDATA%\ck3-save-migrator\packs` on Windows, `~/.config/ck3-save-migrator/packs` elsewhere). The tool creates it the first time a command that loads rules runs, with a README and `_example-pack`, a complete pack to copy; folders starting with `_` are not loaded, so the example never runs. Every pack in it is considered on every update ([Your own packs folder](writing-a-patch.md#your-own-packs-folder)).

### trusted pack

A pack in your [packs folder](#packs-folder) that runs code, which you have allowed with `ck3update trust <pack id>`. Trust records a fingerprint of the pack's files: if a file changes, the pack stops running until you trust it again. PACKS shows `not trusted` or `changed since trusted`.

### campaign scope

A pack can be for one campaign only: `campaign` in its `[applies]` names a [seed](#seed). It is then selected only for saves of that campaign, and PACKS says so.

## The plan

### plan

What `status` prints and `update` runs: the save, the game, the gap, every pack and patch with whether it runs and why, the reference save and the output, all decided before anything runs. `status` and `update` make the same plan, so what `status` shows is what `update` does.

### READY

The verdict when the plan will run: `READY  1.8.1 -> 1.20.1.2: 12 patch(es) run, 8 skipped`. `update` writes the output.

### ALREADY CURRENT

The verdict when the save is at the game's version (or on its [version line](#version-line)) and nothing needs to run. `update` writes nothing.

### NOTHING TO DO

The verdict when a pack is selected but none of its patches will run, for instance because `--rules` named only rules that skip. `update` writes nothing.

### REFUSED

The verdict when something stops the plan: no game found, a save newer than the game, a gap [NOT COVERED](#covered-and-not-covered), two saves that could each be the reference. Each reason is printed at the end as `REFUSED: ...`, followed by a `fix:` line saying what to do. Nothing is written.

### fail early

A plan already REFUSED stops there: the tool does not read the whole save or run the [detectors](#detector), since nothing would be written. Fix the refusal and run `status` again. DETECTORS then says `not run: the plan is refused (fail early)`.

### detector

A read-only check of whether a rule is needed on this save: the rule's own matching run without editing anything, or the lint check that sees what the rule fixes. The detectors read the whole save once; DETECTORS says how long that took, and `--no-detect` skips them.

### needed

What a [detector](#detector) says when the save has what a rule fixes, with how many: `needed: 851 nicknames without text`. Shown on the rule's row in PATCHES.

### done

What a [detector](#detector) says when the save has nothing for that rule to fix: `done: none found`. On an up-to-date save such a rule is skipped.

### unknown

What a [detector](#detector) says when it cannot tell: it needs something that is not there (the game folder, a reference save), or the rule has none. On an up-to-date save an unknown rule never runs unless you name it with `--rules`.

### re-check

What happens to a save already on the game's [version line](#version-line) that you updated before and then played: each rule is judged again. One [the record](#record) shows applied, or that is [done](#done), is skipped; one that is [needed](#needed) runs; one that is [unknown](#unknown) does not run unless named. DETECTORS says `re-checked the save on the game's version line`. It is skipped when the record says this tool version already updated the save.

### record

What the tool remembers about each campaign it has updated, kept by its [seed](#seed) in `games/<seed>.toml` beside the config file: when each update ran, from which file, with which tool version and which patches, and the inputs used. RECORD shows it; `--no-record` neither reads nor writes it.

### pre-filled

An input you did not give this time, taken from [the record](#record)'s latest update (a `--var`, `--old-game-dir`, `--transplant` and the like). RECORD lists each as `pre-filled`. Anything you give on the command line wins.

### gene layout

Which gene sits at which place in a face's `dna=` string: the order the game's `common/genes` files (and any portrait mod's) define. A new game version or other portrait mods change it. R19 carries every face from the layout it was written in to the one you will load with; the FACES block of `status` shows both.

## Checking a save

### lint

The checks run on every output before you load it, and by `ck3update lint <save>`: things the game is known to crash or refuse on (errors), things old campaigns carry (warnings), and the lines the game will write to its error log. An error makes `update` exit with code 4 ([Checking a save](lint.md)).

### converted on load

A field the current game reads from an old save and converts by itself the first time it loads it. `lint` lists such fields as info, not as problems: the game's own re-save carries none of them.

## What status prints

### SAVE

The save you gave: its file and folder, the game version that wrote it, its format numbers, its in-game date, how many mods it lists, and its [seed](#seed).

### GAME

The game the save will be brought to: its version, its `game` folder, and how it was found (Steam's records, `--game-dir`, `CK3_GAME_DIR`). When several installs are found, the newest is used.

### ALSO

Another game install that was found and not used, one block each.

### RECORD

[The record](#record) of this campaign: when it was last updated and from which file, `none yet` for a campaign updated for the first time, and the [pre-filled](#pre-filled) inputs.

### GAP

The [gap](#gap) between the save's version and the game's, and whether it is [covered](#covered-and-not-covered).

### REFERENCE

The [reference save](#reference-save): the one chosen and why, `not needed` when no rule that will run needs one, or which rules skip without one and the steps to make one.

### PACKS

Every [pack](#pack) found, whether it was selected for this save and game and why, and for your own packs whether they are trusted.

### PATCHES

Every [patch](#patch), in the order they run: its id and name, `runs` or `skipped`, its pack, and the reason: what its [detector](#detector) found, or why it is skipped.

### FACES

The [gene layouts](#gene-layout) R19 carries the faces between: the save's own (source), the reference save's for characters the transplant adds, and the target's (the game's genes plus the portrait mods you load with, and where those came from: `dlc_load.json` or `--portrait-mods`), each with its gene count and string length, and the portraits_version R19 sets.

### DETECTORS

What the [detectors](#detector) did: judged each step, [re-checked](#re-check) an up-to-date save, or did not run (and why), how much of the save they read and how long they took.

### OUTPUT

The file `update` will write: `<name>__updated__<game version>.ck3` beside the save, or the save's own name with `--in-place`.

### NOTES

Anything else worth knowing before you run it: a save that crosses the [map rework](#map-rework), an output that already exists, an input from the record that no longer exists.

### SAVES

What `ck3update status` prints with no save named: the save folder it found and how many saves are in it. Name one of them to see its plan.
