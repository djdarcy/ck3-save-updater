# Thinning a save's population (a diagnostic)

`tests/one-offs/thin_population.py` writes a copy of a save with fewer characters. **It is a diagnostic, not an update rule:** the copy is for testing, not for playing. It answers questions like "does this hitch, or this slowdown, get smaller when the save has fewer people?". It is not part of `migrate`, and it never changes the save you give it.

```bash
python -I tests/one-offs/thin_population.py "Campaign.ck3" "Campaign__no-prunable.ck3" --mode prunable
python -I tests/one-offs/thin_population.py "Campaign.ck3" "Campaign__few-dead.ck3" --mode dead
python -I tests/one-offs/thin_population.py "Campaign.ck3" "Campaign__half-commoners.ck3" --mode living-half --seed 1
```

With the optional [tools add-on](tools.md), `ck3update tools run thin_population "Campaign.ck3" "Campaign__no-prunable.ck3" --mode prunable` runs the same script.

## The modes

- **`prunable`**: removes every character in `characters/dead_prunable`, the dead the game itself may forget.
- **`dead`**: removes those, plus every `dead_unprunable` character that nothing still needs. A dead character is kept when any of these mentions them: a living character (as a parent, a killer, ...), a title (a holder in its history), or a house or dynasty (a head, past or present).
- **`living-half`**: removes half of the living characters who play no part. It never removes:
  - a title holder;
  - a house or dynasty head;
  - the player or the player's family (their house, spouses, children, parents);
  - anyone's spouse, betrothed, concubine, liege, host, employer or imprisoner.

  Which half is chosen depends only on `--seed`: the same seed on the same save removes the same people.

In `dead` and `living-half`, a character is also kept when a section of the save mentions them whose references this tool does not know how to remove, such as secrets, schemes or wars. Each run lists how many were kept, and why.

## What goes with a removed character

Every reference to them goes too, so the copy has no links to people who are not in it:
- opinions and relations involving them are deleted whole, as are their AI strategy and their `character_lookup` line;
- every other place the project's id table (`ck3_save_migrator/idschema.py`) knows a character id sits loses the reference: an item in a list (children, knights, kills), a `key=value` line (a dead character's liege), or a typed reference.

The tool prints the counts: characters removed per section, characters kept per reason, records deleted, and references dropped per field. It then runs the lint's checks on the copy and prints the number of errors, which should be 0.

## Limits

- A save's memories stay in its memory database even when the character who had them is removed; only the reference to that character is dropped.
- A number that happens to equal a character's id somewhere else in the save keeps that character. This can only keep a few too many, never remove one who is needed.
- **It is built for a full-size save:** one scan per section, and all edits applied in one pass. On a 120 MB synthetic gamestate with 83,000 characters each mode took 35 to 45 seconds, so a 230 MB save should take about a minute and a half.
