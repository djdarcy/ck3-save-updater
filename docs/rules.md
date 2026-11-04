# Rules

An update is a list of rules. Each rule is one named, numbered change to the save, made because a newer game version reads the save differently from the version that wrote it. `ck3update rules` lists them all, in the order they run, with the game versions each applies to. This page explains each one. The rules ship as a pack of `patch.toml` files inside the package; [Writing a patch](writing-a-patch.md) explains the format.

## Choosing rules

`migrate` takes `--rules`:

- `--rules all` runs every default rule (all but the new-map rules R14 to R17), less any turned off with `ck3update disable`. This is also what runs when `--rules` is not given.
- `--rules R1,title-names` runs only the rules named, by id or by name, in any order. They always run in the order `ck3update rules` lists.
- `--rules all,R15,R14,R16` combines the two: every default rule, plus the ones named. This is how the opt-in rules for the new-map regions are added.
- `--rules all,-R21`, or `--rules -R21` alone, runs every default rule but R21. [Turning rules off](writing-a-patch.md#turning-rules-off) has the details, and how to turn a rule off for every later run.
- An empty `--rules ""` is refused.

`ck3update check <save>` says, for each rule, whether a save still needs it, without changing anything.

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

A rule that cannot run (no reference save given, no game folder found, a prerequisite that did nothing) does nothing and says why in the rule's line of output and in the report. When no selected rule changes anything, for example because the save is already updated, nothing is written and the tool says so; `--force` does not change that. Updating an updated save is therefore safe.

## The rules

The "Since" column is the game version whose loader made the rule necessary. Where the exact version is not known it is a range: `1.8.1<v<=1.20.1.2` means 1.8.1 wrote the save this way and 1.20.1.2 no longer accepts it.

### Format rules (default)

These remove what 1.20 rejects when it loads an older save, or move data to where 1.20 reads it. All but R6 and R22 need nothing but the save.

| Rule | Name | Since | What it changes |
|---|---|---|---|
| R1 | opinions-converging | 1.8.1<v<=1.20.1.2 | deletes the `converging={}` blocks inside temporary opinions |
| R2 | relation-flags | 1.8.1<v<=1.20.1.2 | re-encodes the flags of scripted relationships to the 1-byte width 1.20 expects; a value that does not fit is left unchanged and listed in the report |
| R3 | title-names | 1.8.1<v<=1.20.1.2 | moves each title's name, adjective, prefix and article into the block where 1.20 reads them (`title_name_data`) |
| R4 | game-rule-blanks | 1.8.1<v<=1.20.1.2 | deletes empty `""` entries from the game-rule settings lists |
| R5 | empty-keys | 1.8.1<v<=1.20.1.2 | deletes entries with an empty key (written as `=-5000.1.1`) |
| R21 | dead-liege-cycles | 1.8.1<v<=1.20.1.2 | drops the recorded liege of dead characters whose liege chain loops (two rulers recorded as each other's liege); a ruler who died independent, recorded as their own liege, is left as the game writes them |
| R20 | unrun-war-coordinators | 1.8.1<v<=1.20.1.2 | removes AI war coordinators that were never run (no stance, a supply limit of 0), the war plans that name them, and their entries in the characters' AI strategies; the game builds fresh ones. Left in, the AI can split an army forever to fit a supply limit of 0 |
| R22 | impassable-provinces | 1.18.0 (map rework; exact major unverified) | clears what stands on provinces the current map makes impassable: the holding becomes the empty one a new game has, its soldiers and any siege go, armies step back to where they came from, and council tasks aim at a province of their ruler's own. Needs the game folder |
| R6 | dead-titles-report | 1.18.0 (map rework; exact major unverified) | changes nothing; reports titles the current game no longer defines. Needs the game folder (`--game-dir`, or found automatically) |
| R11 | empty-modifiers | 1.8.1<v<=1.20.1.2 | deletes modifiers with an empty name (`modifier=""`, `""` in modifier lists, `type=""`) |
| R23 | nickname-text | 1.8.1<v<=1.20.1.2 | writes the nickname's text (`nickname_text`) after every nickname that lacks it, the way 1.20 stores a nickname: its key and its rendered text. Without it, nicknames show as raw keys or garbled in game |
| R19 | dna-layout | 1.8.1<v<=1.20.1.2 | rewrites every face (`dna=`) from the gene layout it was written in to the layout you will load with (the game's genes plus the portrait mods `dlc_load.json` enables, or `--portrait-mods`), gene by gene and template by template by name, and sets `portraits_version` to the target's. A character the transplant added is read in the reference save's layout. Runs after R17; `--no-dna` turns it off. See [Faces](#faces-r19) |
| R7 | version-bump | n/a | sets the save's version fields to the target version; runs last |

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

The rules run in this order, which is the order `ck3update rules` lists: R1, R2, R3, R4, R5, R21, R20, R22, R6, R11, R8, R10, R9, R12, R23, R15, R14, R16, R17, R19, R7. R11 runs before R8 because it reads the old religion layout; R10, R9 and R12 run after R8 because they read what it built; the new-map rules run after religion; the faces (R19) after them, so the people the transplant added are in the output, and before any pack of yours; the version bump runs last.

## Faces (R19)

A character's face is its `dna="..."` string: one 4-byte place per gene, in the order the game's `common/genes` files define (the gene layout: file-name order across the gene folders, then declaration order in each file; a mod's file of the same name replaces the game's whole, and special genes are not stored). A new game version or a different set of portrait mods changes the layout, and the game makes up a new face for a string in another layout ("Unexpected DNA string length").

R19 reads each face in the layout it was written in: the save's own (its game version's genes, from `--old-game-dir` when given, else the installed game's, plus the portrait mods its mods list names, as installed today), or the reference save's for a character the transplant added; `--old-portrait-mods` replaces the save's listed mods with the builds you give (the save's own, when the installed ones changed or are gone). A template index the source gene does not define is counted apart. When at least 0.1% of the template indexes read are such, `status` says the source layout is probably not the save's. A handful below that is reported without that warning: it is usually one mod build's extra template. It writes it in the target layout: the installed game's genes plus the gene-shipping mods the launcher enables (`dlc_load.json`, in load order), or `--portrait-mods <id-or-folder>,...` (`--portrait-mods ""` for vanilla).

- A gene in both: its place is copied, its templates renumbered by name, its values kept; colour genes are copied whole.
- A template the target gene lacks falls to 0 (counted). A gene the target lacks is dropped (named); a gene the source lacks is set to the middle (template 0, value 128).
- A face already in the target layout is left as it is. One longer than its layout loses the places past it (counted, and the plan says so); one shorter is left as it is (counted).
- `portraits_version` is set to the target's: the reference save's own, else the built-in table by the game's version line (1.20: 5).

`--face-changes NAME,...` (on `update`, `status`, `migrate` and `check`) turns on changes beyond the rules above. Each is off by default, and the choice is kept in the update's record:

- `renames`: a gene a portrait mod renamed between builds is carried under its new name, instead of being dropped while the new gene is set to the middle. The known rename: Ethnicities & Portraits Expanded's head-roundness gene, today in its head-shape gene.
- `merges`: a gene a portrait mod folded into another is carried as that gene's new template. It applies only where the face's own value of that gene draws nothing, so nothing the face has is replaced. The known merge: Ethnicities & Portraits Expanded's second eye-fold gene, today a template of its eye-fold gene.
- `fallback`: a template the target gene lacks goes to the closest-named template instead of 0. It never goes to a template that draws nothing (`no_...`) unless the lost one was one too. With no close name, it leaves 0 unless 0 draws nothing.
- `known-genes`: genes a later build of a portrait mod appended to every face, read from a small table shipped with the tool, so the old build is not needed. The table holds names only (gene names, template names, index numbers), none of the mod's own work. It applies to a face exactly that many places longer than the save's layout. Other faces are read as before. The known table: Ethnicities & Portraits Expanded's three late-2022 genes after its 1.6.0 build (the lower-lid size and eye shape genes, which today's build still draws, and a hair-aging gene it no longer has).
- `none` (the default) keeps the rules above as they are.

The report lists, per plan, the genes renamed, merged and dropped, and each template moved by `fallback`.

`status` shows the layouts in its FACES block, and the report lists every character under its outcome.
