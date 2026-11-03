# Options

The most used options of `migrate`. `ck3update migrate --help` lists every option.

| Option | What it does |
|---|---|
| `--rules` | which rules to run: `all` (the default, less the rules turned off with `disable`), a comma list of ids or names, or both; a `-` before an id or name leaves that rule out (`all,-R21`) (see [Rules](rules.md)) |
| `--reference` | a save written by the target game version; religion and the new regions are copied from it |
| `--old-game-dir` | the game folder of the version the save was made with (needed by R15) |
| `--game-dir` | the current game's `game` folder (found automatically when installed through Steam) |
| `-o`, `--output` | where to write the updated save (default: `<name>.migrated.ck3` beside the input) |
| `--report` | write a JSON account of every change (see [Reports](reports.md)) |
| `--dry-run` | build and verify everything, write nothing |
| `--force` | overwrite an existing output (never the input) |
| `--wos-shape` | how a custom faith is carried: `faith`, `rite` or `both` (the default, two outputs) |
| `--no-lint` | skip the checks run on each output (see [Checking a save](lint.md)) |
| `--lint-mods` | which mods the checks assume will be active: `save` (the Workshop mods the save lists, the default) or `none` |
| `--portrait-mods` | the portrait mods the faces are carried into (R19), as Workshop ids or folders, in load order; default: the gene-shipping mods the launcher enables (`dlc_load.json`); `""` for vanilla |
| `--old-portrait-mods` | the portrait mods the save was written with, as Workshop ids or folders, in load order: the save's own builds, when the installed ones have changed or gone (default: the installed build of each mod the save lists; `""` for vanilla). An entry that is neither an installed mod nor a folder is refused |
| `--no-dna` | leave every face in the save's own gene layout (R19 does not run; the same as `--rules -R19`) |
| `--pack` | a folder of `patch.toml` fixes to apply after the selected rules (see [Writing a patch](writing-a-patch.md)) |

## Custom faiths

A custom faith is written two ways by default, as its own faith and as a rite of the faith its template now belongs to, giving `My_Old_Campaign__wos-faith.migrated.ck3` and `My_Old_Campaign__wos-rite.migrated.ck3`; pass `--wos-shape faith` or `--wos-shape rite` for one. A save without a custom faith gets a single output under the plain name.

`-v`, `-q` and `--show` work on every command; see [Output and verbosity](output-and-verbosity.md).
