# Glossary

The words this tool uses that a Crusader Kings III player may not know, or that mean something narrower here than they do elsewhere. Each entry says where you meet the word. Words in capitals are what `ck3update status` and `ck3update update` print: the verdict on the first line, then one block per header.

## Saves and versions

### reference save

A save written by the game you have now, used as a source: the religion rules (R8 to R12) rebuild religion from it, and the new-map rules (R14 to R17) copy the regions the new map added from it. For the new regions it should be a new game started on your campaign's own date. You meet it in the REFERENCE block of `status`, which says which save was chosen, or which rules skip without one and how to make one ([The reference save](reference-save.md)).

### map rework

The game's map was redrawn between 1.12 and 1.13: lands moved, provinces were added and some became impassable. A save from before it needs [the transplant](#transplant) to load in a 1.20 game. `status` names it in NOTES: "this save crosses the 1.13-1.20 map rework".

### transplant

The new-map rules (R14 to R17), which bring the regions the [map rework](#map-rework) added into an older save, with their rulers, courts and families copied from the [reference save](#reference-save). `update` selects them by itself when a save crosses the rework and a reference is present (`--transplant auto`, the default); `--transplant off` leaves them out, and `--rules all,R14,R15,R16` names them by hand. When they are not selected, PATCHES shows them as `opt-in: not in --rules` ([New-map regions](new-map-regions.md)).

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

### game folder

The folder that holds the installed Crusader Kings III, the `game` folder inside it. The tool reads the game's own files there: what the current version defines, so it knows what a save may still name. It finds the folder by itself, through Steam's records and the usual install places. `--game-dir` chooses one when there are several. `status` shows the one it used under GAME.

### save games folder

The folder where the game keeps your saves: `save games`, under `Documents\Paradox Interactive\Crusader Kings III` on Windows. Give the tool a save's name and it looks there. Updated saves are written beside the save you gave. Copy one into this folder to load it in the game.

### playset

The list of mods the game's launcher has turned on. The tool reads it from the launcher's own file, `dlc_load.json`, in the game's documents folder. It matters for faces: they are carried into the gene layout of the mods you will play with. So set the launcher's playset before you run `update`.

### re-save

A save the game wrote after loading an older save. When a new version loads an old save, it converts it, and the re-save is the converted result. The tool reads re-saves to see what the game kept and what it dropped.

### witness

Your last save from before a version change, given with `--witness`. After the game has converted your campaign and you have saved it, the witness is the only place where what the conversion dropped still exists: your buildings, tiers and wonders, for example. `update --witness` reads them from it and writes them back. You never need to name it if you run the update on the save itself before your first load in the new version.

### same-date rule

`update --witness` writes nothing unless the witness has the same in-game date as the save it repairs. A witness from a later date would be fine. A witness from an earlier date means you played on since, and writing its buildings back would undo that play. So the tool refuses, and says so.

### phase one and phase two

The two passes of an update to 1.21, around the game's own conversion. **Phase one** runs on your 1.20 save, before you load it in 1.21: it writes what the conversion would otherwise lose. **Phase two** runs on the game's own 1.21 re-save, with your last 1.20 save as the [witness](#witness): it repairs what the conversion got wrong. [Updating a save](updating-a-save.md) shows both.

### uncompressed save

A save the game wrote with save compression turned off, or from its debug console. The tool reads it and updates it like any other. The updated file is written compressed, as the game writes saves by default.

### ironman save

A save from an ironman campaign. It is in a binary format the tool cannot read, so the tool says so and stops. [Editing a save](editing-a-save.md) covers `ironman-off`, which works on an ordinary save that has ironman turned on.

### golden

A save we keep as a known-good result: a real campaign, updated by a given version of the tool, then loaded in the game. A later version must reproduce it, or explain each difference. You meet the word in the changelog.

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

Which gene sits at which place in a face's `dna=` string: the order the game's `common/genes` files (and any portrait mod's) define. A new game version or other portrait mods change it. R19 carries every face from the layout it was written in to the one you will load with: the launcher's current playset (set it to the mods you will play with before `update`), or `--portrait-mods`. The source is the save's own portrait mods as installed now, or the builds you give with `--old-portrait-mods` when they have changed or gone. The FACES block of `status` shows both, with where each mod came from.

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

## The save names used when comparing routes

Some pages compare what the game does alone with what the tool does. They name the saves this way:

- **original-1.8**: the campaign as the 1.8 game saved it, untouched.
- **chain-1.20**: the game alone, stepping that save through 1.18.4 and 1.19.0 to 1.20, each version saving the last one's save. Opening the original directly in 1.19 or 1.20 crashes, so these stepping stones are the only way without the tool.
- **ref-1.20**: a new 1.20 game, started on the campaign's date. It is the [reference save](#reference-save) for 1.20.
- **ours-1.20**: the tool's update of the original to 1.20.
- **conv-1.21**: 1.21's own conversion of ours-1.20, as the game saved it after its first load.
- **ref-1.21**: a new 1.21 game on the campaign's date, the reference for 1.21.
- **ours-1.21**: the tool's update to 1.21 (phase one, the game's load, then phase two).

## 1.21's economy, in brief

### district

In 1.21, a holding is built from districts, and buildings sit inside them. A district is the long-term choice; its buildings are cheaper to change. The game's own conversion of an older save leaves them empty, and the tool fills them from your old buildings where 1.21 allows it.

### holding district

The district that is the holding itself: its castle, city or temple line. Its main building sets the holding's type and tier.

### regular district

The districts a holding builds by choice: villages, markets, guilds, walls and others. How many fit depends on the province's [settlement size](#settlement-size): two at the smallest, six at the largest.

### resource district

The one district in a county's capital that makes the county's trade good: stone, timber, fruit, ivory and others. A county can only build one for a good it has the potential for, and the patch notes put that at 3 to 5 goods per county.

### duchy-capital district

A district only the capital barony of a duchy may build, and only while the county's holder holds that duchy. It replaced 1.20's duchy-capital buildings: marches, jousting lists, blacksmiths, royal forests and the like.

### settlement size

How many people live in a barony, from 1 to 10. It decides how many districts fit, and big settlements need more food and are harder to control. The game's conversion sets every province to size 1. The tool raises each one to the size a new game gives it.

### prosperity

How rich a county is. It took over the economic part of 1.20's development: it raises taxes, supply, innovation and prices. An updated save's development becomes its prosperity exactly.

### trade good

One of 44 goods 1.21 trades through markets, 16 of them basic (cereals and meat among them). Buildings may need goods, and when a need isn't met, the building's bonus doesn't apply.

### successor

The 1.21 building or district that took an old one's place. The tool keeps a table of them. Where an old building has no chosen successor yet, it is not carried, and [what is not carried over](not-carried-over.md) names it.

### innovation

An advance a culture researches, which unlocks buildings, districts and units. A culture can only research the innovations it lists. When the game converts an older save, it doesn't add the innovations new in that version, so the tool adds them.

## Questions during an update

### the resources question

What to do where your old save had a quarry, logging camp, orchard or elephant pen, and the game already placed a different resource district in that province. The answers are `m`, `k` and `r` ([Updating a save](updating-a-save.md#questions-during-the-update-and---auto)).

### the duchies question

Asked once per update, when your save has counties in an old duchy that a newer game moved into a duchy of its own (going to 1.20, or the duchies 1.21 added, going to 1.21). `f` moves them into the new duchy, unheld, as a new game has it (the default). `l` leaves them where the campaign had them, as the game itself would, and the new duchy stays empty.

### --auto

Answers an update's questions in advance, so it can run without asking. `all=mygame` prefers your old save everywhere; `all=newgame` prefers what the new game placed. The report records every answer and how it was reached.

## Game words the docs use

### rite

Since 1.20, each faith is divided into rites, and every character and county follows one. Older saves have no rites, so the update gives each character the rite their faith now belongs to.

### custom faith

A faith a player founded or reformed in their own campaign, such as one made from a mod. The update carries it with its doctrines and holy sites, as its own faith or as a rite.

### men-at-arms

A ruler's professional troops, as opposed to levies. Some rules rename regiment types the current game no longer has.

### soak

Letting the game run an updated save for a while, unattended, to see whether it stays stable. `ck3update soak` is the one command that starts the game ([Soak](soak.md)).
