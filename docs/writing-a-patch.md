# Writing a patch

A patch is one fix to a save, written as a small file instead of code: "in every temporary opinion, delete `converging`", "in the game rules lists, delete the empty entries". The migrator's own simple rules are written this way, and you can write your own for a game version the tool does not know yet, keep them in a folder, and run them with `migrate --pack <folder>`.

This page is for a player who knows what a Crusader Kings III save looks like inside, but not this tool's code.

## Packs and patches

A **pack** is a folder of patch folders, with a `pack.toml` that names the pack and the order its patches run in:

```
my_pack/
  pack.toml
  F1-old-key-renamed/
    patch.toml
  F2-empty-names/
    patch.toml
```

A **patch** is a folder holding a `patch.toml`. Name the folder `<id>-<name>` (for example `F1-old-key-renamed`). A patch says what it is for and, in one of three ways, what it does:

- **edits** (`[[edit]]` tables): changes addressed by a path through the save, the usual case, and the subject of most of this page;
- **code** (`script = ...`): a Python function, for a fix that needs to look at the save as a whole;
- **a program** (`[run]`): a script kept outside the tool, run over the save as it is.

The tool's own pack, `to_1_20`, holds all 19 of its rules: R1, R4, R5, R7 and R11 as edits, the others as code. It is inside the installed package; the examples below are copied from it.

## pack.toml

```toml
format = 1
id = "my_fixes"
title = "My fixes for saves from 1.20 to 1.21"
order = ["F1", "F2"]
```

- `format`: always `1` for now. A file in another format is refused.
- `id`, `title`: the pack's name, and a line saying what it is for.
- `order`: every patch id in the pack, in the order they run. A patch folder the order leaves out, or an id with no folder, is refused.

## patch.toml

```toml
format = 1
id = "F1"
name = "old-key-renamed"
title = "rename old_key to new_key in the metadata"
since = "1.21.0"
default = true
requires = []
tested = { origin = ["1.20.1.2"], target = ["1.21.0"] }
issue = ""
```

- `id`: short and unique in the pack (`F1`). The order and other patches' `requires` use it.
- `name`: a readable name; the tool shows it in its output and accepts it in `--rules`.
- `title`: one line saying what the patch changes.
- `since`: the game version that made the patch necessary, as text (it can be a range or a note: `"1.18.0 (map rework)"`).
- `default`: whether the patch runs when its pack runs (`true` unless you say otherwise).
- `requires`: ids of patches that must run with this one; a selection without them is refused, naming them.
- `tested`: the game versions you saw it work on. This is for information only: a patch never refuses a save because of its version.
- `issue`: optional, a link to where the problem is discussed.

`format`, `id`, `name`, `title` and `since` are required; `default` (true), `requires` (none), `tested` and `issue` are optional. The folder name `<id>-<name>` is a convention for people reading the pack; the tool reads the id and name from the file.

Then come the edits (or `script =`, or `[run]`).

## Edits

Each `[[edit]]` names a `path`, an `op` (the operation), and the fields that operation needs.

### Paths

A save is a tree: `key=value`, `key={ ... }`, anonymous `{ ... }` items, and bare list values. A path walks it, segment by segment, separated by `/`:

- the first segment names top-level sections, and matches every one of that name (the game writes some sections twice);
- a later segment names child blocks, and matches every child of that key, not just the first;
- `*` matches any one child block, keyed (`12={`) or anonymous (`{`);
- `**` matches any depth, including none: `**/modifiers` is every `modifiers={ ... }` anywhere.

`path` can be a list of paths. A path that matches nothing is not an error: the patch is simply not needed there.

A path with `**` is found quickly even in a 200 MB save, by searching the raw text for the last thing the edit names (the block key, or the key or value the operation looks for) and checking each hit's place in the tree. So a `**` path must end in a named segment, or its operation must name what it looks for (a `key`, a `value`, or `where.key` / `where.field`).

Values are written as the save's own bytes: `'""'` is the two quote characters, `'"1.20.1.2"'` is a quoted string, `18` and `"18"` are the bare number.

### The six operations

`delete_key`: delete every child with `key` (and, with `where = { value = ... }`, only those with that value), tidily: a child alone on its line takes its line with it. R1 deletes `converging` from every temporary opinion:

<!-- shipped: R1-opinions-converging -->
```toml
format = 1
id = "R1"
name = "opinions-converging"
title = "delete converging={} in opinions temporary_opinion blocks"
since = "1.8.1<v<=1.20.1.2"
default = true
requires = []
tested = { origin = ["1.8.1"], target = ["1.20.1.2"] }
# The report counts the temporary opinions that held a converging, as the rule always has.
matched = "blocks-hit"

# 1.8.1 writes converging={...} inside temporary opinions; 1.20 rejects each ("Unexpected token: converging").
[[edit]]
path = "opinions/active_opinions/*/temporary_opinion"
op = "delete_key"
key = "converging"
```

R5 deletes entries with an empty key wherever they are. `at = "line-start"` keeps only those whose `=` begins its line, which is how the rule has always found them:

<!-- shipped: R5-empty-keys -->
```toml
format = 1
id = "R5"
name = "empty-keys"
title = "delete map entries with an empty key (=-5000.1.1)"
since = "1.8.1<v<=1.20.1.2"
default = true
requires = []
tested = { origin = ["1.8.1"], target = ["1.20.1.2"] }

# An entry with an empty key ("=-5000.1.1"), at any depth; 1.20 rejects each ("Invalid date string ... empty").
# Only an entry whose "=" begins its line is taken, as the rule always has.
[[edit]]
path = "**"
op = "delete_key"
key = ""
at = "line-start"
```

`delete_value`: delete every bare list value equal to `value`. R4 deletes the empty entries from the game rules lists, under both names the game uses, in both places:

<!-- shipped: R4-game-rule-blanks -->
```toml
format = 1
id = "R4"
name = "game-rule-blanks"
title = 'delete empty "" entries from game_rules settings lists'
since = "1.8.1<v<=1.20.1.2"
default = true
requires = []
tested = { origin = ["1.8.1"], target = ["1.20.1.2"] }
# The report counts the settings lists looked at, as the rule always has, not the blanks found.
matched = "blocks"

# 1.8.1 leaves empty "" entries in the game rules lists, both in meta_data and in the top-level section, under
# both names the game uses ("settings" and "setting"); 1.20 has none.
[[edit]]
path = ["meta_data/game_rules/settings", "meta_data/game_rules/setting", "game_rules/settings", "game_rules/setting"]
op = "delete_value"
value = '""'
```

`delete_entry`: delete every child entry whose `where` holds. `where = { key = ... }` compares the entry's own key; `where = { field = { name = value } }` compares one field directly inside the entry. A list means "any of these". R11 uses all three of its edits on one problem, modifiers whose name is empty:

<!-- shipped: R11-empty-modifiers -->
```toml
format = 1
id = "R11"
name = "empty-modifiers"
title = 'delete modifiers with an empty name (modifier="", "" in modifiers lists, type="")'
since = "1.8.1<v<=1.20.1.2"
default = true
requires = []
tested = { origin = ["1.8.1"], target = ["1.20.1.2"] }

# 1.8.1 writes modifiers whose definition is gone with an empty name; 1.20 rejects each
# ("Failed to read key reference: :").

# A modifier={ ... } or timed_modifier={ ... } block whose modifier="" begins its line: the whole block goes.
[[edit]]
path = "**"
op = "delete_entry"
where = { key = ["modifier", "timed_modifier"], field = { modifier = '""' } }
at = "line-start"

# "" inside any modifiers={ ... } list.
[[edit]]
path = "**/modifiers"
op = "delete_value"
value = '""'

# type="" beginning its line, anywhere.
[[edit]]
path = "**"
op = "delete_key"
key = "type"
where = { value = '""' }
at = "line-start"
```

`where` compares by equality only. Anything more (a pattern, a number range, a comparison between two fields) is a job for `script =`.

`set`: replace the value of every child with `key`. When the value already equals, nothing changes. R7 sets the version fields, using templates (below):

<!-- shipped: R7-version-bump -->
```toml
format = 1
id = "R7"
name = "version-bump"
title = "set meta_data version/save_game_version to the target"
since = "n/a"
default = true
requires = []
tested = { origin = ["1.8.1"], target = ["1.20.1.2"] }

# The version is written quoted, the save game version as a number. portraits_version is set only when a value is
# given (an edit whose template has no value is skipped).
[[edit]]
path = "meta_data"
op = "set"
key = "version"
value = '"@@target_version@@"'
need_path = true        # a save without meta_data is not one this patch can bump: fail, saying so

[[edit]]
path = "meta_data"
op = "set"
key = "save_game_version"
value = "@@target_save_game_version@@"

[[edit]]
path = "meta_data"
op = "set"
key = "portraits_version"
value = "@@portraits_version@@"
```

`rename_key`: rename every child key `key` to `to`. No shipped rule needs it; this one renames a key in the metadata:

<!-- example: rename -->
```toml
format = 1
id = "F1"
name = "old-key-renamed"
title = "rename old_key to new_key in the metadata"
since = "1.21.0"

[[edit]]
path = "meta_data"
op = "rename_key"
key = "old_key"
to = "new_key"
```

`insert`: insert text just inside a block, at its `start` (after `{`) or `end` (before `}`). An insert is not undone by running it again, so an inserting patch must say how to tell it has been applied: `done = { path = ..., key = ... }`, the place and the key whose presence means "already done". Without it the patch is refused.

<!-- example: insert -->
```toml
format = 1
id = "F2"
name = "add-a-flag"
title = "add migrated_by=yes to the metadata"
since = "1.21.0"
done = { path = "meta_data", key = "migrated_by" }

[[edit]]
path = "meta_data"
op = "insert"
position = "end"
payload = "\tmigrated_by=yes\n"
```

### Templates

`@@name@@` in a value is replaced when the patch runs: `@@target_version@@` (for example `1.20.1.2`), `@@target_save_game_version@@` (`18`), `@@portraits_version@@` (given with `--portraits-version`), and the tool's other settings by their names (`game_dir`, `old_game_dir`, `reference`). An edit whose template has no value is skipped, which is how R7 sets `portraits_version` only when you ask.

### expect

By default a path that matches nothing just means the patch is not needed there: every player's save is different. When an edit must find something, say so with `expect = { min = 1 }`, or an exact count `expect = 3` (rarely right: counts differ between saves). When an `expect` fails, the whole patch fails closed: none of its edits is applied, and the tool says which edit, which path and the count it found.

`need_path = true` on an edit fails the patch the same way when its path addresses no block at all (R7 uses it: a save without `meta_data` is not one it can update). It is for paths without `**`.

### What the report counts

The report gives each patch a `matched` and an `edited` count. `edited` is the number of changes made. `matched` is, by default, the number of things the edits found (`matched = "found"`); a patch can set `matched = "blocks"` (before its `[[edit]]` tables) to count the blocks its paths address instead, as R4 does to count the settings lists it looked at, or `matched = "blocks-hit"` to count only the blocks where an edit found something, as R1 does to count the temporary opinions that held a `converging`. Both are for paths without `**`. Each edit's own counts are in the report under `edits`.

### Needed and done

The tool works out whether a patch of edits is needed (some edit would change the save) or done (none would). Deletes, renames and sets are safe to run twice by nature; an insert is made safe by its `done`. Running a pack on a save it has already fixed changes nothing.

## When to write code instead: script =

When the fix depends on more than one place at once (re-encoding a value, moving data between sections, anything that reads one thing to decide another), write a Python function and point at it:

```toml
format = 1
id = "R2"
name = "relation-flags"
title = "re-encode scripted_relations flags bitsets to 1.20's 1-byte width"
since = "1.8.1<v<=1.20.1.2"
script = "ck3_save_migrator.rules.to_1_20:r2_relation_flags"
```

In the tool's own pack, `script = "<module>:<function>"` names a function inside the tool's Python modules. In a pack folder of your own, `script = "<file>.py:<function>"` names a file inside the patch folder: a path with `..`, or one that starts with `/`, is refused, and so is the `<module>:<function>` form (it could import any module Python can find, the current folder included). The function takes `(save, ctx, rule)` and returns `rule.result(matched=..., edited=...)`, like the tool's own rules in `ck3_save_migrator/rules/`. A code patch runs whenever it is selected.

A code patch runs Python with your permissions, so, like a run patch below, a pack folder with one is refused unless you pass `--allow-run`. The check comes before any file of the pack is imported.

## When to run a program instead: [run]

When you already have a script that fixes saves on its own, run it as it is:

```toml
format = 1
id = "F3"
name = "fix-faces"
title = "repair portrait data with my own script"
since = "1.21.0"

[run]
command = ["@@python@@", "-I", "@@tools_dir@@/fix_faces.py", "@@input@@", "@@output@@"]
needs = ["tools_dir"]
```

The tool writes the save as it stands to `@@input@@`, runs `command` as its own program from your working directory, and reads `@@output@@` back. If the program exits with an error, or writes no output, nothing of the patch is applied, and the tool reports the exit code and the last lines the program wrote to its error output. `@@python@@` is the Python running the tool. Your own variables come from `--var name=value` (repeatable) or `--vars file.toml`; a variable that is a list, written as a whole element (`"@@files@@"`), becomes one argument per item. `needs` names the variables that must be given; a missing one is refused, naming it. A program still running after `timeout` seconds (`timeout = 600` unless the `[run]` table says otherwise) is stopped, and the patch fails, saying so. What the program prints is kept in files, not in memory; the last lines of its error output are reported when it fails.

A run patch runs a program with your permissions, so a pack folder with one is refused unless you pass `--allow-run`:

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --pack "my_pack" --var tools_dir="my_tools" --allow-run
```

When the script sits in a scripts folder, `tool = "fix_faces"` with `args = ["@@input@@", "@@output@@"]` is a shorter way to write the same command; [Tools](tools.md#a-tool-in-a-run-patch) explains it.

## Running your pack

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --pack "my_pack"
```

`--pack` is repeatable; the packs' patches run after the selected rules (so after the version bump, R7), in the order given, and appear in the output and the `--report` like any rule. Only the patches with `default = true` run; `--rules` does not select patches from a `--pack` folder. If a patch fails (an `expect` or `need_path` that does not hold, or a run patch's program that fails), the tool prints which patch and why, writes nothing, and exits with code 5. The tool's own migration runs first, as always (every default rule, unless `--rules` chooses others), and the result is written as usual to `<name>.migrated.ck3` (or `-o`), with the checks' findings beside it in `<name>.migrated.lint.json`.

## Testing a patch

Test a patch the way the tool tests its own: build a small synthetic save that has every shape the patch should change and a few near misses it must leave alone, apply the patch, and compare the result with what you expect, byte for byte. Then break the patch on purpose (point it at the wrong key, drop a path) and check the test fails: a test that cannot fail proves nothing.

```python
from pathlib import Path
from ck3_save_migrator import savefile as sf
from ck3_save_migrator.patches import apply_patch, load_patch
from ck3_save_migrator.patches.pack import CONTEXT_FIELDS
from tests.fixtures.make_ck3 import build_ck3

HERE = Path(__file__).parent
META = b'meta_data={\n\told_key=1\n\tother=2\n}\n'


def test_old_key_is_renamed():
    patch = load_patch(HERE / "my_pack" / "F1-old-key-renamed", from_disk=True, context_fields=CONTEXT_FIELDS)
    save = sf.parse_save(build_ck3(meta=META, body=b"x={\n\told_key=3\n}\n"))
    apply_patch(save, patch, {})
    assert save.gamestate == b'meta_data={\n\tnew_key=1\n\tother=2\n}\nx={\n\told_key=3\n}\n'   # x is a near miss
```

What the pieces are: `build_ck3(meta=..., body=...)` (from the tool's test fixtures, so run the test from a checkout of the repository) builds a small save file whose gamestate is `meta` followed by `body`; `load_patch` reads one patch folder (`from_disk=True` for a folder of your own, `context_fields` the template names a patch may use); `apply_patch(save, patch, values)` applies it, `values` being the template values (`{}` when the patch uses none, or for example `{"target_version": "1.21.0"}`), and returns what it found and did. Build paths from the test file's own folder, as `HERE` does, so the test runs from anywhere.

The tool's own tests of this kind are in `tests/test_patches_equivalence.py` (each shipped patch against the Python rule it replaces) and `tests/test_patches_ops.py` (each operation).

## Game versions inform, never gate

`since` and `tested` record what you know: which version made the patch necessary, and which versions you saw it work on. The tool never refuses a save because its version is not listed. Whether a patch applies is decided by the save itself: if what the patch looks for is there, it is needed; if not, it is not.
