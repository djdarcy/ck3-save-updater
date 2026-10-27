# Options

The most used options of `migrate`. `ck3-save-migrator migrate --help` lists every option.

| Option | What it does |
|---|---|
| `--rules` | which rules to run: `all` (the default), a comma list of ids or names, or both (see [Rules](rules.md)) |
| `--reference` | a save written by the target game version; religion and the new regions are copied from it |
| `--old-game-dir` | the game folder of the version the save was made with (needed by R15) |
| `--game-dir` | the current game's `game` folder (found automatically when installed through Steam) |
| `-o`, `--output` | where to write the migrated save (default: `<name>.migrated.ck3` beside the input) |
| `--report` | write a JSON account of every change (see [Reports](reports.md)) |
| `--dry-run` | build and verify everything, write nothing |
| `--force` | overwrite an existing output (never the input) |
| `--wos-shape` | how a custom faith is carried: `faith`, `rite` or `both` (the default, two outputs) |
| `--no-lint` | skip the checks run on each output (see [Checking a save](lint.md)) |

`-v`, `-q` and `--show` work on every command; see [Output and verbosity](output-and-verbosity.md).
