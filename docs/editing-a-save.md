# Editing a save

`ck3update edit` makes one change you ask for by name. It is separate from `update`. An update carries what the game decided into the new version. An edit changes an outcome because you chose to.

**An edit never changes the save you give it.** It writes a new file beside it, named `<save name>__<edit>.ck3`. Use `--in-place` if you want the edited save to keep the original's name. Even then the original is kept as `<name>.bak.ck3`, unless you turn backups off.

You do not need to know how a save is built. You name the edit and what it applies to. The tool finds the place, shows you the change, and writes it only when you agree.

## Before you start

- **Close the game first**, or at least do not edit the save the game has loaded. Edit a save, then load the edited file.
- **The save must be a text save.** That is what the game writes for an ordinary campaign. An ironman save is in another format, and the tool says so and stops. A save the game wrote uncompressed is read the same way, and the edited copy is written compressed, as the game normally writes it.
- **A large save takes a few seconds.** The first time an edit looks up a character, the tool reads every character in the save. On a 240 MB campaign that is about ten seconds.
- **Try `--dry-run` first.** It shows the exact change and writes nothing.

## One edit, start to finish

```
ck3update edit My_Campaign.ck3 set-sex "Conchenn nic Bruide" male
```

```
EDIT   set-sex: make a living character male or female
  save   : My_Campaign.ck3
  target : 78307 Conchenn (F, age 7, born 980.8.16) house 5483 father 64975 Bruide mother 65171 E_lfweard titles -
  change at 133,532,726: b'\tfemale=yes\n' -> b''
  output : My_Campaign__set-sex.ck3
Write My_Campaign__set-sex.ck3? [y/N]
```

Read the `target` line. It names the one character the edit found, with enough to be sure it is the right one. The `change` line shows the bytes that will go and the bytes that will take their place. Answer `y`, and the new file is written beside your save. Load that file in the game.

## The edits

```
ck3update edit --list
```

| Edit | What it does |
|---|---|
| `set-sex` | makes a living character male or female |
| `acknowledge-child` | makes a child born outside the marriage the legitimate child of the mother's husband |
| `events` | lists the events queued for a character (writes nothing) |
| `event-show` | shows one queued event (writes nothing) |
| `event-remove` | removes one queued event, so it never fires |
| `event-reroll` | gives one queued event a new seed, so it rolls again |
| `event-schedule` | queues an event for a character on a date |
| `artifacts` | lists the artifacts a character holds (writes nothing) |
| `give-artifact` | gives a character a copy of an artifact in the save |
| `set-faith` | changes the faith or rite a character follows |
| `set-eminent-holy-sites` | chooses which of a faith's holy sites are eminent |
| `set-doctrines` | changes a faith's tenets and doctrines |
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

- a parent's first name (`Conchenn nic Bruide`, `Gabran Aelfweard`);
- the house's name (`Gabran Ui Neill`);
- a title the character holds (`Murchad tara`).

Type names as the game shows them. Accents do not matter, so `Gabran` finds Gabrán and `Aelfweard` finds Ælfweard. A name may be more than one word, like a house called "Uí Néill". The save stores names as the game's internal keys (Gabrán is `GabrA_n`), and those work too. The names the game shows need the game folder, which the tool finds through Steam or `CK3_GAME_DIR`. Without it, the internal keys still match, typed plainly. Words such as "nic", "mac" and "of" are skipped. Put the whole query in quotes.

This works the same way for every edit that takes a character.

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

Some lines read `on_action <name>` in place of an event's name. Those are not events but the game's own scheduled pulses and effects, such as a yearly pulse. They can be shown, rerolled and removed like events. Leave them alone unless you know what one does: the game relies on many of them.

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

## A child taken as a husband's own

```
ck3update edit My_Campaign.ck3 acknowledge-child "Gabran" "Bruide" honest
```

`acknowledge-child` makes a child born outside the marriage the legitimate child of the mother's husband, or of a former husband. The child joins his children and loses the bastard and wild oat traits. Nothing is forgotten: the save keeps the real father, the way the game does for any child whose father in law is not the father in blood.

The last value says what happens to the truth:

- **`honest`** keeps it as the game's "disputed heritage" secret. Other characters can find it out in play. If it is exposed, the child takes the Disputed Heritage trait, which costs opinion and legitimacy but does not stop him inheriting.
- **`clean`** removes the secret, so nobody in the game can find it out. The real father is still recorded in the save.

Some things to know:

- **A legitimate son may come first in the line of succession.** He may now inherit ahead of younger brothers and sisters. The game works out heirs again by itself within a day of play.
- **The child's house is not changed.**
- **Only a father can be set.** A save records a child's real mother only, so a wife cannot take her husband's child as hers.
- **The father must be the mother's husband or former husband.** `--dangerous` allows another man.
- **A child who already has a father in law is refused.** This edit does not move a child from one father to another.

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

## Faith

Three edits change faith, each the way the game would allow it in play. Each one refuses what the game refuses. The refusal names the game file and line that holds the rule. `--dangerous` writes the change anyway, and the report says what was forced.

### A character's faith

```
ck3update edit My_Campaign.ck3 set-faith "Gabran Aelfweard" "Shafi'i"
```

`set-faith` changes the faith a character follows. Name a rite to choose it exactly, as the game shows it. Accents and punctuation do not matter, so `Shafi'i` and `shafii` are the same rite, and so are `Ásatrú` and `asatru`. A rite's number works too. Name a faith instead, such as `Sunni`, and the character gets that faith's main rite.

Only the character's faith changes. Their titles, holy orders and faith heads stay as they are. The report says when the faith itself changes. Under a same-faith succession law, that can change who inherits from them. A dead character is changed only with `--dangerous`.

### A faith's eminent holy sites

```
ck3update edit My_Campaign.ck3 set-eminent-holy-sites "Way of Scarcity" "Bodh Gaya, Jerusalem, Iona"
```

`set-eminent-holy-sites` chooses which of a faith's holy sites are eminent. Name one to three sites, as the game shows them or by number. Separate them with commas. A name of one word each also works with spaces alone, as in `"jerusalem rome iona"`. Each must already be one of the faith's holy sites. The game refuses any other, and so does this edit. When two holy sites share a name (there are two Carthages), the faith's own sites settle which one is meant. Only the faith's list of eminent sites changes.

### A faith's tenets and doctrines

```
ck3update edit My_Campaign.ck3 set-doctrines "Way of Scarcity" "+Pilgrimage Attitude: Encouraged"
```

`set-doctrines` changes a faith's tenets and doctrines, named as the game shows them. Write `+` before one to add it and `-` before one to remove it. A doctrine is written with its group, as in `Pilgrimage Attitude: Encouraged`, because several groups share names like "Encouraged"; a shared name on its own is refused with each one listed. A doctrine you add replaces the one the faith holds in the same group. If the faith holds none in that group, the new one fills it. To swap a tenet, remove one and add another in the same call:

```
ck3update edit My_Campaign.ck3 set-doctrines "Way of Scarcity" "-Jewish Syncretism, +Christian Syncretism"
```

The game's keys (`+doctrine_pilgrimage_encouraged`, `-tenet_gnosticism`) work as well.

The faith and its main rite change together. Other rites of the same faith keep their own.

The rules come from the game's own files, so the edit needs to find the game. It looks through Steam, or reads `CK3_GAME_DIR` if you set it to the game's `game` folder. These are the rules it checks:

- A faith holds three tenets.
- A faith holds only one syncretism tenet.
- A tenet closed to the faith's religion cannot be chosen. Christian Syncretism is closed to a Christian faith.
- A doctrine that every faith of the religion carries cannot be dropped. Teachings of Jesus is one.
- A doctrine cannot be removed from a group the faith must fill, unless another takes its place.

The game checks more than these when a faith reforms in play. The edit does not check the rest.

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

An uncompressed save is what the game writes when its saves are not compressed, for example when you save from the console with debug mode on. The tool reads it like any other. `edit` and `update` write their new copy compressed; the save you gave them is left as it was.

`ironman-off` works on a text save that has ironman on. Whether the game then loads it as an ordinary save has not been tested yet.
