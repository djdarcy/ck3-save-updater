# Rules

A migration is a list of rules. Each rule is one named, numbered change to the save, made because a newer game version reads the save differently from the version that wrote it. `ck3-save-migrator rules` lists them all, in the order they run, with the game versions each applies to. This page explains each one.

## Choosing rules

`migrate` takes `--rules`:

- `--rules all` runs every default rule (R1 to R12). This is also what runs when `--rules` is not given.
- `--rules R1,title-names` runs only the rules named, by id or by name, in any order. They always run in the order `ck3-save-migrator rules` lists.
- `--rules all,R15,R14,R16` combines the two: every default rule, plus the ones named. This is how the opt-in rules for the new-map regions are added.
- An empty `--rules ""` is refused.

Choosing R14, R15 or R16 brings R17 along by itself: those three plan what to copy, and R17 writes it.

### Prerequisites

Some rules use what an earlier rule did. A selection that includes such a rule without the rules it needs is refused before the save is even read, and the message names what is missing, for example:

```
ERROR: rule prerequisites missing: R14 needs R8 (add them, or use --rules all,R14,R15,R16 for the full migration with the transplant)
```

| Rule | Needs |
|---|---|
| R9 | R8, R10 |
| R10 | R8 |
| R12 | R8, R9 |
| R14 | R8 |
| R15 | R14, R16 |
| R16 | R8, R14 |

`all` includes every prerequisite of the default rules, so `--rules all` and `--rules all,R15,R14,R16` are never refused for this reason.

### When a rule has nothing to do

A rule that cannot run (no reference save given, no game folder found, a prerequisite that did nothing) does nothing and says why in the rule's line of output and in the report. When no selected rule changes anything, for example because the save is already migrated, nothing is written and the tool says so; `--force` does not change that. Migrating a migrated save is therefore safe.

## The rules

The "Since" column is the game version whose loader made the rule necessary. Where the exact version is not known it is a range: `1.8.1<v<=1.20.1.2` means 1.8.1 wrote the save this way and 1.20.1.2 no longer accepts it.

### Format rules (default)

These remove what 1.20 rejects when it loads an older save, or move data to where 1.20 reads it. They need nothing but the save.

| Rule | Name | Since | What it changes |
|---|---|---|---|
| R1 | opinions-converging | 1.8.1<v<=1.20.1.2 | deletes the `converging={}` blocks inside temporary opinions |
| R2 | relation-flags | 1.8.1<v<=1.20.1.2 | re-encodes the flags of scripted relationships to the 1-byte width 1.20 expects; a value that does not fit is left unchanged and listed in the report |
| R3 | title-names | 1.8.1<v<=1.20.1.2 | moves each title's name, adjective, prefix and article into the block where 1.20 reads them (`title_name_data`) |
| R4 | game-rule-blanks | 1.8.1<v<=1.20.1.2 | deletes empty `""` entries from the game-rule settings lists |
| R5 | empty-keys | 1.8.1<v<=1.20.1.2 | deletes entries with an empty key (written as `=-5000.1.1`) |
| R6 | dead-titles-report | 1.18.0 (map rework; exact major unverified) | changes nothing; reports titles the current game no longer defines. Needs the game folder (`--game-dir`, or found automatically) |
| R11 | empty-modifiers | 1.8.1<v<=1.20.1.2 | deletes modifiers with an empty name (`modifier=""`, `""` in modifier lists, `type=""`) |
| R7 | version-bump | n/a | sets the save's version fields to the target version; runs last. `--portraits-version` also sets the portraits version |

### Religion rules (default)

1.20 replaced the old faith layout with separate databases of faiths and rites, and every character and county now points at a rite. These rules rebuild religion from a save written by 1.20 (`--reference`). Without a reference they do nothing and say so.

| Rule | Name | Since | What it changes |
|---|---|---|---|
| R8 | religion-transplant | 1.20.0 (By God Alone: faiths/rites databases) | replaces the save's religion with the reference's religions, faiths, rites, holy sites and religious organizations, with titles and cultures translated by name to the save's own numbering |
| R10 | custom-faith | 1.20.0 | carries the save's own custom faiths (for example the Way of Scarcity) as a faith or as a rite, with their doctrines, fervor, religious head, holy sites, founder (when that character is still in the save) and dated history, wherever 1.20 has a place for each |
| R9 | faith-to-rite | 1.20.0 (characters and counties point at a rite) | replaces each character's and county's old faith with the matching 1.20 rite, and updates script variables that refer to a faith or religion |
| R12 | faithless-rite | 1.20.0 (rite on every character) | gives characters with no recorded faith their house head's rite, falling back to the dynasty head, then the employer, then the player; each fallback is reported |

Catholicism and Orthodoxy stay independent faiths, each with its religious head carried over. When two old faiths would give the same new faith different heads, the first is kept and the other is reported.

A custom faith can be carried in two shapes, chosen with `--wos-shape`: as a faith of its own (`faith`), or as a rite of the faith its template now belongs to (`rite`). The default, `both`, writes two outputs, `<name>__wos-faith.migrated.ck3` and `<name>__wos-rite.migrated.ck3`; a save without a custom faith gets a single output under the plain name.

### New-map rules (opt-in)

1.20's map rework added thousands of provinces and titles that an older save has never heard of, and removed or moved some it had. These rules bring the new regions in from a 1.20 save at the campaign's date. They are not part of `all`; add them with `--rules all,R15,R14,R16`. [New-map regions](new-map-regions.md) explains them in full.

| Rule | Name | Since | What it changes |
|---|---|---|---|
| R15 | dead-titles | 1.13 to 1.20 (titles the map rework removed or moved) | renames the save's titles that 1.20 removed or moved to their 1.20 successors where the match is clean, and removes the rest (split, wasteland, dropped); every case is reported. Needs `--old-game-dir` and the current game folder |
| R14 | new-titles | 1.13 to 1.20 (map rework: East Asia, Tibet, ...) | plans the titles and provinces the save does not have, from the reference save |
| R16 | people | 1.13 to 1.20 (the new regions' rulers, courts and families) | plans the holders of the planned titles, their courts and close family, from the reference save |
| R17 | transplant-write | 1.20 | writes everything R14 to R16 planned, with numbers translated, links to things not brought along dropped, and new titles joined to the campaign's existing ones |

## Order

The rules run in this order, which is the order `ck3-save-migrator rules` lists: R1, R2, R3, R4, R5, R6, R11, R8, R10, R9, R12, R15, R14, R16, R17, R7. R11 runs before R8 because it reads the old religion layout; R10, R9 and R12 run after R8 because they read what it built; the new-map rules run after religion; the version bump runs last.
