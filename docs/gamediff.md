# gamediff: what a game update changed

When Crusader Kings III updates, a save from the old version can stop loading because something it names is gone or works differently: a trait removed, a title moved, a faith renamed, a game rule option dropped. `gamediff` compares the two versions' game files definition by definition and, given a save, says which of the removed or changed definitions that save actually uses. It is meant for writing patches: it tells you where to look.

It reads only. It never changes the game folders or the save, and writes nothing except the file you name with `--json`.

## Using it

```bash
ck3-save-migrator gamediff "old/game" "new/game"
ck3-save-migrator gamediff "old/game" "new/game" --save "My_Old_Campaign.ck3" --json "update.json"
```

Each folder is a CK3 install's `game` folder (the one holding `common`, `events`, `history` and `map_data`). To compare two versions you need both installed somewhere, for example a copy of the old `game` folder kept before updating.

The output lists, for each folder that differs, how many definitions were added, removed and changed, and their names:

```
common/traits: 1 added, 1 removed, 1 changed
  added   : new_trait
  removed : gone_trait
  changed : brave
...
total: 3 added, 5 removed, 7 changed, in 10 folder(s)
the save names 7 of the removed or changed keys (My_Old_Campaign.ck3):
  traits     removed : gone_trait
  traits     changed : brave
  titles     removed : k_old_kingdom
```

Up to 30 names are shown per line; `--json` holds every one. `-q` leaves only the counts and the save's lines.

## What is compared

- **Which files:** every `.txt` file under `common/`, `events/` and `history/`, and `map_data/definition.csv`.
- **What a definition is:** each top-level `key = value` or `key = { ... }` in a file. Definitions are grouped by the folder their file is in, such as `common/traits` or `history/characters`.
- **When a definition counts as changed:** when its text differs once comments, spacing and line breaks are ignored. Reformatting a file, or adding a comment, is not a change.
- **Moving between files:** a definition that moved to another file in the same folder is not a change either.
- **What is left out:** `@name = value` constants and `namespace = ...` lines, which are not definitions.

Some definitions sit below the top level, so they get groups of their own:

- **`common/landed_titles`**: every title (`e_`, `k_`, `d_`, `c_`, `b_`, `h_`) at any depth. A title's body is compared without the titles nested in it, so a changed barony shows as that barony only, not as its county, duchy, kingdom and empire too.
- **`common/religion/religions (faiths)`**: the faiths inside each religion.
- **`common/game_rules (options)`**: the options of each game rule.
- **`map_data/definition.csv`**: one entry per province id.

## What "the save names" means

With `--save`, the save's gamestate is read once and every name in it is collected, quoted or not. Then each removed or changed key of these kinds is looked up in that set:

| Kind | Groups |
|---|---|
| traits | `common/traits` |
| titles | `common/landed_titles` |
| faiths | `common/religion/religions (faiths)` |
| religions | `common/religion/religions` |
| cultures | `common/culture/cultures` |
| modifiers | `common/modifiers`, `common/event_modifiers` |
| buildings | `common/buildings` |
| game rules | `common/game_rules` and its options |

A key counts as used when the save contains it as a name anywhere. This is a pointer, not a proof: a short, common name can appear in a save for another reason. Check each one in the save before writing a patch for it.

## What it does not do

- It does not compare `gui/`, `localization/`, `gfx/` or the map's images; only the definition files above.
- It does not say what a change means. A changed trait might have a new modifier value or a new requirement; open both files to see which.
- It does not read mods. To see what a mod update changed, point it at the two versions of the mod's folder: a mod has the same `common/` layout.
