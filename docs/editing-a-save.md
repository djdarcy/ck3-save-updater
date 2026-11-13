# Editing a save

`ck3update edit` makes one change you ask for by name. It is separate from `update`. An update carries what the game decided into the new version. An edit changes an outcome because you chose to.

**An edit never changes the save you give it.** It writes a new file beside it, named `<save name>__<edit>.ck3`. Use `--in-place` if you want the edited save to keep the original's name. Even then the original is kept as `<name>.bak.ck3`, unless you turn backups off.

## The edits

```
ck3update edit --list
```

| Edit | What it does |
|---|---|
| `set-sex` | makes a living character male or female |
| `ironman-off` | turns ironman off in a text save |
| `revert` | undoes edits this tool made |

`ck3update help <edit>` says what an edit takes and does.

## Changing a character's sex

```
ck3update edit My_Campaign.ck3 set-sex "Conchenn nic Bruide" male
```

The tool shows the character it found and the change. At a terminal it asks before writing. `--yes` skips the question, and `--dry-run` shows the change and writes nothing.

Only the character's own sex flag changes. Their face keeps its genes. The game works out heirs again by itself within a day of play.

## Naming a character

Give the character's id, or a first name followed by something that narrows it:

- a parent's first name (`Conchenn nic Bruide`);
- the house's name;
- a title the character holds (`Murchad tara`).

Words such as "nic", "mac" and "of" are skipped. Put a name of several words in quotes.

When several living characters match, nothing is written. The tool lists each one with id, sex, age, house, parents and titles. Pick the id from that list and run the edit again with it:

```
ck3update edit My_Campaign.ck3 set-sex 78307 male
```

The tool never guesses between two characters. Only living characters can be edited.

## Undoing an edit

Every edit writes a ledger beside its output, `<output name>.edits.json`. It records what was changed and where.

```
ck3update edit My_Campaign__set-sex.ck3 revert
```

`revert` undoes the last edit. `revert <n>` goes back to the state after edit n, and `revert all` goes back to the original. A revert writes a new file too, so it can itself be reverted.

A revert is refused once the game has saved over the file. Then the original save, or the backup, is the way back.

## Options

| Option | What it does |
|---|---|
| `--dry-run` | show the change, write nothing |
| `--yes` | do not ask before writing |
| `-o`, `--output` | where to write |
| `--force` | overwrite an existing output (never the save itself) |
| `--in-place` | the edited save takes the save's own name |
| `--bak`, `--no-bak` | with `--in-place`: keep the original as `<name>.bak.ck3`, or keep no backup (see [Configuration](config.md)) |
| `--list` | list the edits |

## Your own edits

You can write edits of your own and keep them in your packs folder. `ck3update edit --list` then shows them beside the built-in ones. [Writing a patch](writing-a-patch.md#writing-an-edit) explains how.

## What cannot be edited yet

A binary save cannot be read. That is what the game writes for an ironman campaign. The tool says so and stops.

`ironman-off` works on a text save that has ironman on. Whether the game then loads it as an ordinary save has not been tested yet.
