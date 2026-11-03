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

Two optional fields are read by `update` and `status` (`migrate` ignores them):

```toml
after = "R17"           # run right after the patch R17 of the packs before this one, not after them all

[applies]               # the saves and games this pack is for
save = ">=1.20, <1.21"
game = ">=1.21, <1.22"
```

- `[applies]`: `save` and `game` are comma-separated comparisons on dotted versions (`>=`, `>`, `<=`, `<`, `==`, `!=`; a bare version means `==`), every one of which must hold. `update` selects a pack when the save's version matches `save` and the game's matches `game`; a pack without `[applies]` matches any version, and the plan says so ("no version span declared"). A gap between the save's version and the game's that no selected pack's `[applies]` covers is reported, and `update` writes nothing. The gap is judged on major.minor: a 1.20.1.2 save against a 1.20.1.3 game is the same 1.20 line, assumed compatible, and needs no pack ("already current", with a line saying so). The built-in pack has `save = ">=1.8, <1.20"` and `game = ">=1.20, <1.21"`.
- `campaign = { name = "<label>", seed = <random_seed> }` in `[applies]`: the pack is for one save game only, the one whose gamestate's top-level `random_seed` is `seed` (a campaign keeps its seed through updates and play). On any other save its patches are skipped, "for another save game (<label>)". `status`, `packs` and `help` show the label. A pack without it is for every save.
- `after`: the pack's patches run right after that patch of another pack (for example after `R17`, so before the version bump `R7`), in the pack's own order. An id that no pack before it has is refused.

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

# The version is written quoted, the save game version as a number. portraits_version is R19's (the target's,
# with the faces it carries).
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

**Insert only keys the game itself writes.** A key the game does not define is reported when the save loads ("Unexpected token"), so it does nothing but add an error. The usual reason to insert is a field a newer game version's own saves carry and older saves lack. No shipped rule needs one yet; in this example `new_field` stands for such a field:

<!-- example: insert -->
```toml
format = 1
id = "F2"
name = "new-field-added"
title = "add new_field, which 1.21's own saves carry, to the metadata of an older save"
since = "1.21.0"
done = { path = "meta_data", key = "new_field" }

[[edit]]
path = "meta_data"
op = "insert"
position = "end"
payload = "\tnew_field=no\n"
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

The tool writes the save as it stands to `@@input@@`, runs `command` as its own program from your working directory, and reads `@@output@@` back. If the program exits with an error, or writes no output, nothing of the patch is applied, and the tool reports the exit code and the last lines the program wrote to its error output. `@@python@@` is the Python running the tool. Your own variables come from `--var name=value` (repeatable) or `--vars file.toml`; a variable that is a list, written as a whole element (`"@@files@@"`), becomes one argument per item. `needs` names the variables that must be given: a list, or a table with a line of help for each, `needs = { tools_dir = "the folder holding fix_faces.py" }`. With `migrate` a missing one is refused, naming it; `update` and `status` know before anything runs, and skip the patch, saying `needs --var tools_dir (the folder holding fix_faces.py)`. A variable can be given to one patch only, `--var F3.tools_dir=...`; a bare `--var tools_dir=...` (or a bare key in a `--vars` file) reaches every selected patch of one pack that needs it, and is refused only when patches of different packs need it, naming them; a qualified name still wins. A pack's `vars.toml` applies to its own patches only. A program still running after `timeout` seconds (`timeout = 600` unless the `[run]` table says otherwise) is stopped, and the patch fails, saying so. What the program prints is kept in files, not in memory; the last lines of its error output are reported when it fails.

A run patch runs a program with your permissions, so a pack folder with one is refused unless you pass `--allow-run`:

```bash
ck3update migrate "My_Old_Campaign.ck3" --pack "my_pack" --var tools_dir="my_tools" --allow-run
```

When the script sits in a scripts folder, `tool = "fix_faces"` with `args = ["@@input@@", "@@output@@"]` is a shorter way to write the same command; [Tools](tools.md#a-tool-in-a-run-patch) explains it.

A run patch can say how to tell it has already run, so `update` does not run it again and `check` can say "done":

- `done = { path = "...", key = "..." }`, as for an inserting patch: the place and the key whose presence means done;
- or `done_command = [...]` in the `[run]` table: a program given `@@input@@`, a temporary copy of the save; exit code 0 means already done, any other means needed. It is code, so it runs only for a trusted pack in your packs folder or with `--allow-run`, under the patch's `timeout`; otherwise the verdict is "unknown (done_command not run: not trusted)".

`ck3update help <patch id>` prints a patch's title, pack, since, default, needs (with their help) and done check.

## Running your pack

```bash
ck3update migrate "My_Old_Campaign.ck3" --pack "my_pack"
```

`--pack` is repeatable; the packs' patches run after the selected rules (so after the version bump, R7), in the order given, and appear in the output and the `--report` like any rule. Only the patches with `default = true` run; `--rules` does not select patches from a `--pack` folder. If a patch fails (an `expect` or `need_path` that does not hold, or a run patch's program that fails), the tool prints which patch and why, writes nothing, and exits with code 5. The tool's own migration runs first, as always (every default rule, unless `--rules` chooses others), and the result is written as usual to `<name>.migrated.ck3` (or `-o`), with the checks' findings beside it in `<name>.migrated.lint.json`.

## Your own packs folder

So that one `ck3update migrate <save>` runs your fixes too, put your packs in your own packs folder: `packs` beside the config file (`%APPDATA%\ck3-save-migrator\packs` on Windows, `~/.config/ck3-save-migrator/packs` elsewhere). The tool creates it the first time `migrate`, `check` or `rules` runs, with a `README.md` ("ADD RULES HERE") and `_example-pack`, a complete pack to copy; it never writes into the folder once it exists. More folders like it can be named in the config file:

```toml
pack_dirs = ["D:/my ck3 packs"]
```

- Every pack found there runs on every update, in the same call, after the tool's own rules and before any `--pack` folder: the standard folder first, then each `pack_dirs` folder, each folder's packs in name order. A subfolder whose name starts with `_` or `.` is not loaded, and a folder reached twice loads once.
- A pack of edits runs as it is. A pack that runs code (a `script =` or `[run]` patch) runs only once you trust it:

  ```bash
  ck3update packs              # each pack found: its folder, id, kind (declarative or code) and whether it runs
  ck3update trust my_fixes     # let it run, as its files are now; prints the code and programs it runs
  ck3update untrust my_fixes   # take the trust back
  ```

  Trusting records a fingerprint (a sha256 of the pack folder's files, their paths and bytes) in the config file. If any file of the pack changes, or a file is added or removed, the pack stops running until you trust it again. A pack that is not trusted, or changed since, is skipped and the tool says so: `found, not trusted: run 'ck3update trust my_fixes' to let it run`. The rest of the update goes on, and the exit code does not change. `--allow-run` lets every code pack in the folders run for that one call.
- `ck3update disable <patch id>` turns one of your patches off for every later update, as it does a built-in rule; `ck3update rules` lists your packs' patches after the built-in ones, with their pack.
- A pack may hold a `vars.toml` beside its `pack.toml`, the variables its run patches use; a `--vars` file or a `--var` on the command line wins. A recipe in the folder then needs no options at all.
- A patch id that a built-in rule has, two packs with one id, or one patch id in two of your packs are refused, naming both places.
- The `--report` lists your packs under `user_packs`: id, folder, kind, state and fingerprint.

## Checking a save

`check` reads a save and says, for each selected rule and each default patch of the packs you name, what it would do there. It changes nothing and writes no file:

```bash
ck3update check "My_Old_Campaign.ck3" --pack "my_pack"
```

```
  R1   opinions-converging  needed   2 edit(s)
  R2   relation-flags       needed   2 scripted-relation flag bitsets wider than 1.20's 1 byte (e.g. ...)
  R7   version-bump         done     nothing to edit
  F1   old-key-renamed      fails    my_pack F1-old-key-renamed/patch.toml [[edit]] #1 (...): expected 1, found 0
4 patch(es): 2 needed, 1 done, 0 unknown, 1 fail(s)
```

- **needed**: at least one of its edits would change the save.
- **done**: none would; the save already has this fix, or never needed it.
- **unknown**: a code or run patch, which only running would tell, or one of the tool's rules whose detector needs what is not at hand (the game folder for R6, R15 and R22, a reference save for R14, R16 and R17; `--game-dir` gives the folder). The tool's rules written in Python are judged by a detector: the rule's own matcher run without its edits (R2, R21, R23), or the lint check that sees what the rule fixes (R3, R20, R22, R6, R15, R8-R12, R14-R17). `check` never runs them, and never imports a pack's code, so it needs no `--allow-run` (it accepts the flag, so the same command line works for `migrate` and `check`).
- **fails**: an `expect` or `need_path` does not hold; the line names the edit, the path and the count. `migrate` would stop on it, so `check` exits with code 5, as `migrate` does.

`check` takes `--rules` as `migrate` does, and leaves out the rules you turned off (below). Each patch is judged on the save as it is now, not after the patches before it have run.

## Turning rules off

If one of the tool's rules does not suit your save, turn it off once instead of writing out every other rule in `--rules`:

```bash
ck3update disable R21      # or its name: disable dead-liege-cycles
ck3update disabled         # list what is off, and where the file is
ck3update enable R21       # back on
```

A rule turned off is left out of `--rules all` (and of a `migrate` or `check` with no `--rules`), and the tool says so in one line: `skipped by your config: R21`. Naming it in `--rules`, as in `--rules all,R21`, still runs it: what you type beats the setting. An id the tool does not know is refused, and the message lists the known ones. It works the same on the patches of the packs in your own packs folder (below). A patch of a `--pack` folder is turned off with `default = false` in its `patch.toml`.

To leave a rule out for one run only, put a `-` before it in `--rules`:

```bash
ck3update migrate "My_Old_Campaign.ck3" --rules all,-R21
ck3update migrate "My_Old_Campaign.ck3" --rules -R21        # the same: all but R21
ck3update check "My_Old_Campaign.ck3" --rules -R21,-empty-keys
```

A `-` takes an id or a name, in any case, and applies after everything else: after `all`, after the rules you name, and after the rules turned off with `disable`. Leaving out a rule that was not selected anyway changes nothing. An unknown id is refused, listing the known ones. So is leaving out a rule another selected rule needs: `--rules all,-R8` is refused because R10 requires R8, and the message names both, so you can leave both out (`-R8,-R10,...`) or keep R8. Naming a rule and leaving it out in the same `--rules` is refused too.

The setting is kept in a small file the tool owns: `%APPDATA%\ck3-save-migrator\config.toml` on Windows, `~/.config/ck3-save-migrator/config.toml` elsewhere (the folder keeps the project's old name, so a config made before the rename still works). The environment variable `CK3SM_CONFIG` names another file instead.

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

The tool's own tests of this kind are in `tests/test_patches_equivalence.py` (each shipped patch against the output the Python rule it replaced wrote on the same saves, kept as files in `tests/fixtures/patches/`) and `tests/test_patches_ops.py` (each operation).

## Game versions inform, never gate

`since` and `tested` record what you know: which version made the patch necessary, and which versions you saw it work on. The tool never refuses a save because its version is not listed. Whether a patch applies is decided by the save itself: if what the patch looks for is there, it is needed; if not, it is not.
