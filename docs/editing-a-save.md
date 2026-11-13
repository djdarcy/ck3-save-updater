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
| `events` | lists the events queued for a character (writes nothing) |
| `event-show` | shows one queued event (writes nothing) |
| `event-remove` | removes one queued event, so it never fires |
| `event-reroll` | gives one queued event a new seed, so it rolls again |
| `event-schedule` | queues an event for a character on a date |
| `artifacts` | lists the artifacts a character holds (writes nothing) |
| `give-artifact` | gives a character a copy of an artifact in the save |
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

## Events that have not happened yet

A save holds a queue of events the game will fire later: a child's personality event, a title changing hands, and thousands more. You can look at the ones about a character, remove one, or make one roll again.

```
ck3update edit My_Campaign.ck3 events "Murchad mac Brian"
```

```
1234 Murchad (M, age 10, born 977.9.30) house 77 dynn_Example father 1200 Brian mother 1201 Sadb titles -
  #52     987.10.28   child_personality.4000                       seed 2087479515  (root)
  #9424   989.3.3     child_personality.4015                       seed 904695798  (root)
  2 of the save's 12825 queued events
```

Each line gives the event's number, the date it fires, its name and its seed. `(root)` means the event is about that character. `(as <name>)` means another character's event names them.

`event-show <number>` prints one event as the save holds it. Neither command writes anything.

```
ck3update edit My_Campaign.ck3 event-reroll 52
ck3update edit My_Campaign.ck3 event-remove 52
```

`event-reroll` changes the event's seed. The seed decides what the event rolls when it fires, so a new seed can give another outcome. It can also give the same one. You cannot choose the outcome: the save does not store one before the event fires.

`event-remove` takes the event out, so it does not fire. It does not undo what earlier events already did. The game can queue the same event again later by its own rules. In a test, a child whose event was removed had a new one queued by the game some months on.

```
ck3update edit My_Campaign.ck3 event-schedule "Murchad mac Brian" child_personality.4015 987.11.5
```

`event-schedule` adds an event to the queue: the character it is about, the event's name, and the date it fires. The event must be one the game defines, in its own files or in a Workshop mod the save lists. For an event of a mod kept somewhere else, `--dangerous` skips that check. The date cannot be before the save's own date.

What happens when the event fires is up to the event. Each one checks its own conditions and does nothing if they do not hold. A scheduled event is given the character only. An event that expects more, such as a second character, may not work as it does in play.

An event's number belongs to one file. After a removal the later events move up by one, so list them again before the next edit. Event names are the game's own, such as `child_personality.4000`. The game's event files say what each one does.

## Artifacts

```
ck3update edit My_Campaign.ck3 artifacts "Murchad mac Brian"
```

```
1234 Murchad (M, age 40, born 947.8.7) house 77 dynn_Example father 1200 Brian mother 1201 Sadb titles k_munster
  20         wall_big               Example House Banner
  72         pedestal               Alms-bowl of the Buddha
  181        wall_shield            Fine Shield
  3 artifacts, of the save's 4702
```

Each line gives an artifact's id, its type and its name. A `-` means the save names no type for it.

```
ck3update edit My_Campaign.ck3 give-artifact "Sadb ingen Brian" 72
```

`give-artifact` gives a character a copy of an artifact that is already in the save. Take the id from the `artifacts` list of whoever holds it. The copy has the same name, type, bonuses and history, under a new id. The original stays with its owner. The copy goes into the receiver's inventory, not onto a wall or a pedestal.

The receiver must already hold at least one artifact. The tool cannot yet give one to a character who has never held any. It also cannot make a new artifact from nothing.

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
