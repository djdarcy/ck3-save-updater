# Configuration

What you can set once, so every run uses it: a small settings file the tool owns, and a few environment variables. Everything here has a working default; a missing file means all defaults.

## The settings file

`%APPDATA%\ck3-save-migrator\config.toml` on Windows, `~/.config/ck3-save-migrator/config.toml` elsewhere (under `XDG_CONFIG_HOME` when that is set). The folder keeps the project's old name, so a file made before the rename still works. The environment variable `CK3SM_CONFIG` names another file instead.

The same folder holds your packs folder (`packs`) and the record of each save game you have updated (`games/<random_seed>.toml`, see [Updating a save](updating-a-save.md)).

A complete example, every setting shown:

```toml
disabled = ["R21"]
pack_dirs = ["D:/my ck3 packs"]
transplant = "auto"

[display]
gap = 2
spacing = "compact"
align = "flow"

[trusted]
"my_fixes" = "<sha256 of the pack folder's files>"
```

A setting that is not valid (a word that is not one of its choices, a number out of range) stops the command with a message that names the file and the setting; nothing runs until it is fixed.

| Setting | What it does | Values | Default | Changed by |
|---|---|---|---|---|
| `disabled` | rules turned off for every later run; naming one in `--rules` still runs it | rule ids, e.g. `["R21"]` | none | `ck3update disable <id>`, `ck3update enable <id>` ([Turning rules off](writing-a-patch.md#turning-rules-off)) |
| `pack_dirs` | more folders of your own packs, besides the standard `packs` folder | folders | none | editing the file ([Your own packs folder](writing-a-patch.md#your-own-packs-folder)) |
| `transplant` | `update` selects the new-map rules (R14-R17) by itself when a save from before the 1.13 map rework needs them and a reference save is found; `"off"` leaves them to `--rules` | `"auto"` or `"off"` | `"auto"` | editing the file; `--transplant` overrides it for one run |
| `[trusted]` | the packs that run code which you have trusted, each with the fingerprint of its files when trusted | pack id = fingerprint | none | `ck3update trust <pack id>`, `ck3update untrust <pack id>` (never by hand) |
| `[display]` | how `status` and `update` lay out their plan | below | below | editing the file |
| `[cache] index` | keep each save's block index (what the `**` patches search with) in a temp folder, so a second command on the same unchanged save skips building it again (about 10 s on a large save); only the newest 2 saves' entries are kept and none for more than a day, `ck3update cache clear` removes them all (`ck3update cache where` shows the folder), and the plan's DETECTORS block says when it wrote or read one; about 140 MB per large save, so set it to `false` where temp disk is short | `true` or `false` | `true` | editing the file |

The commands that change the file (`disable`, `enable`, `trust`, `untrust`) keep every setting above as you wrote it, `[display]` included.

## `[display]`: how the plan is laid out

`status` and `update` print the plan as blocks: a header in capitals (`SAVE`, `GAME`, `REFERENCE`, ...), then one fact per line as `field: value`. Three settings shape it.

**`gap`**: the spaces between a header and its field names, a whole number from 1 to 8. Default `2`.

**`spacing`**: whether a blank line separates the blocks.

- `"compact"` (the default): no blank lines at all; the most lines on one screen.
- `"blank"`: a blank line between blocks, and around the verdict and the refusals.

**`align`**: how the blocks' columns line up. A block's natural column is where its values would start if it stood alone: its header, the gap, its longest field name and `: `.

- `"flow"` (the default): each block is as tight as the gap allows. A block of several rows uses its own natural column; a block of one row uses its own column or the column of the block above, whichever is larger, so a short one-line block never shrinks back under a block that was pushed out.
- `"global"`: every block uses the largest natural column, so every colon in the output lines up and every value starts in one column.
- `"blocks"`: every header is padded to the longest header in the output, then the gap, then each block's own field names. The headers form one column; each block's colons line up within it.

With none of these set you get `gap = 2`, `spacing = "compact"`, `align = "flow"`. The same plan in each alignment:

```
align = "blocks"                    align = "global"                  align = "flow"
SAVE          file: Old.ck3         SAVE         file: Old.ck3        SAVE     file: Old.ck3
           version: 1.8.1                     version: 1.8.1                version: 1.8.1
RECORD     status: none yet         RECORD     status: none yet       RECORD  status: none yet
GAP        versions: 1.8.1 -> ...   GAP      versions: 1.8.1 -> ...   GAP   versions: 1.8.1 -> ...
REFERENCE  status: none chosen      REFERENCE  status: none chosen    REFERENCE  status: none chosen
            skips: R8, R10                      skips: R8, R10                    skips: R8, R10
PACKS      to_1_20: selected        PACKS     to_1_20: selected       PACKS     to_1_20: selected
```

In `flow`, `GAP` keeps the column `RECORD` was pushed out to, and `PACKS` keeps `REFERENCE`'s, because each is one line.

The patches table keeps its own columns in every layout. The width of the lines follows your terminal, between 60 and 120 characters; a value too long for the line continues on the next line under its own column.

## Environment variables

| Variable | What it does |
|---|---|
| `CK3SM_CONFIG` | the settings file to use instead of the standard one (its folder also holds the packs folder and the records) |
| `CK3_GAME_DIR` | the game's `game` folder, when the tool does not find it through Steam |
| `CK3_REFERENCE_SAVE` | the reference save to use, as `--reference`; `none` for none |
| `NO_COLOR` | any value: no colour, and no progress spinner ([no-color.org](https://no-color.org/)) |
| `CK3UPDATE_COLOR` | `always` keeps colour even when the output is piped; `never` turns it off |
| `FORCE_COLOR` | any value: colour even when piped (`NO_COLOR` still wins) |
| `CK3SM_VERBOSITY`, `CK3SM_SHOW` | the same as `-v`/`-q` and `--show`, where there is no command line to add them to ([Output and verbosity](output-and-verbosity.md)) |
| `COLUMNS` | the line width for the plan, instead of the terminal's (still between 60 and 120) |

`--plain` on `status` and `update` does for one run what `NO_COLOR` does: plain text, no colour and no spinner, for pasting the output somewhere.
