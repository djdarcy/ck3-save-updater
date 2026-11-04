# Checking a save before you load it

`lint` reads a save and reports, without changing it:

- **errors**: broken links the game reads by number, such as a faith or rite that points nowhere or a character without a rite;
- **warnings**: links that point at nothing but that the update does not write, which old saves often carry already;
- **what the game will log**: each kind of complaint the current game writes to its error log when it reads this save, with a predicted count and examples;
- **unknown names**: setting names neither the game nor the mods know.

`migrate` runs the same checks on every output by default, prints them, and writes them next to the output as `<name>.lint.json` (`--no-lint` skips them). The predictions depend on which mods will be active: by default the checks assume the Workshop mods the save itself lists (those installed); `--mods none` on `lint`, or `--lint-mods none` on `migrate`, predicts a load with no mods. Pointing the checks at the game folder (found automatically, or `--game-dir`) and a save from the current version (`--reference`) makes them more complete.

```bash
ck3update lint "My_Old_Campaign.migrated.ck3" --json "My_Old_Campaign.lint.json"
```

## Options

| Option | What it does |
|---|---|
| `--reference` | a save written by the target game version, for the key-name check and the portrait data length; `none` to skip |
| `--game-dir` | the game's `game` folder (default: `$CK3_GAME_DIR` or the usual Steam paths) |
| `--no-keys` | skip the checks that need game data: key names and what 1.20 will log |
| `--mods save` / `--mods none` | assume the save's own Workshop mods are active (the default, those installed), or none |
| `--json` | write the findings to this JSON file |

A check that cannot run, because there is no game folder or reference save to compare against, is listed as skipped rather than passed.

## The checks

Each finding is described in plain words first. For what the game will log, the game's own log wording is the check's name, so it can be found in the game's error log.

### Errors

- braces balance;
- entry ids are unique in each id space, and so are their slots (two objects of the same kind sharing a number, which the game cannot load);
- title keys are unique;
- title lieges point at titles that exist;
- a barony's de facto liege is its de jure county;
- capital baronies have a county;
- held counties have a county record (without it a county has no culture, faith or development, and scripts that ask for them fail);
- vassal contracts name both parties;
- every character has a rite, and character rite ids exist;
- characters with a rite have a rites database (people copied in without the religion rules);
- title names only inside `title_name_data` (also a title with inline names and no `title_name_data`, the older layout R3 moves);
- every county has an existing rite;
- rites point at faiths, characters and rites that exist;
- faiths point at religions, rites, organizations, holy sites and titles that exist;
- religions, holy sites, organizations and holy orders point at faiths, rites and titles that exist;
- script variables point at faiths and religions that exist;
- a ruler's primary title is their highest title;
- title liege chains end (no title is its own liege, directly or through others);
- vassal contracts bind living characters;
- a vassal ruler has a contract with their liege;
- nothing lives on a province the new map made impassable;
- `meta_data` entries all have a key;
- a title made while the game runs is registered in `dynamic_templates`;
- a mercenary company's title exists, and names the company back;
- army links resolve both ways;
- AI war coordinators have been run, and AI war plans and strategies point at things that exist;
- the titles a fresh game has exist in the save.

### Warnings

- held baronies have a county (the game logs only capital baronies, but every orphan is land no county holds);
- template cultures are registered on the game's list of cultures made from its definitions;
- character culture ids exist;
- character house ids exist;
- family links (spouses, children, real fathers) point at characters in the save;
- title holders are characters in the save;
- `title_name_data` follows `coat_of_arms_id` (a placement detail; the game logged nothing for it);
- county culture ids exist;
- a courtier's employer is alive;
- a baron has a contract with their county's holder;
- a ruler's domain lists only titles they hold;
- stored script scopes point at things that exist;
- armies have soldiers;
- a mercenary company's title key is `x_mc_<company id>` (a candidate check: a title keyed for another company; no rule fixes it yet).

### Information

- titles a fresh game has that the save lacks, but that the game creates by itself.

### What the game will log

Each of these is a kind of line the current game writes to its error log, with the predicted number of lines:

- `Unexpected DNA string length`: portrait data in an older format (needs a reference save);
- `Unexpected token`: fields the current game no longer has. Four of them are listed as info, not as lines the game will log as losses: the game converts them on load (measured on 1.20.1.2's re-save of an updated save, 2026-10-31, which carries none of them): `owner_influence` and `ready` in schemes, `localization_key` and `renamed` in landed_titles. `exposure_marker` and `exposure_type` in culture_manager are rejects: the re-save carries neither because the game drops them, and with them the innovation each culture was learning. The R26 rule carries that innovation into the field the current game reads, and the lint line says so;
- `Failed to read key reference`: names of modifiers, perks, innovations, artifact looks and the like that the game and the active mods no longer define;
- `Unknown on action`: queued events waiting on trigger points the game or the active mods no longer have;
- `is not a valid title template`: titles the current game no longer defines, which load without a name;
- `Duplicate landed title name`: follows from the nameless titles above;
- `Unknown dynasty template`: dynasties whose template the game no longer has;
- `Failed to fetch a valid culture`: cultures the game's own scripts use that the save does not have (names only).

Everything but the first two needs the game folder.

### Unknown names

- key names the game and the mods do not know, compared against the reference save, the game itself, its script files and the active mods.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | done, with no error from the updater itself. The save can still carry thousands of predicted log lines; that is reported, not an error |
| 1 | bad input (a missing file, a save the tool cannot read, an unknown or refused rule selection) |
| 2 | refused: the output exists, or would overwrite the input |
| 3 | the written file failed verification; nothing was written |
| 4 | the checks found an error. `migrate` still writes the output so it can be inspected |
| 5 | a patch failed: `migrate` prints why and writes nothing; `check` exits 5 when a patch would fail |

`soak` has exit codes of its own; see [soak](soak.md).
