# Output and verbosity

## How much it says

Every command takes `-v` and `-q`, and they can be repeated:

- `-v` adds each rule's time and a one-line summary of the new-map transplant;
- `-vv` adds how long reading and writing the save took;
- `-q` leaves only the results: what was written, and the checks' verdict;
- `-qqq` leaves only errors;
- `-qqqq` prints nothing, so only the exit code tells.

`--show CHANNEL:LEVEL` raises a single part of the output, e.g. `--show transplant:1`. The parts are `rules`, `transplant`, `lint`, `io` and `timing`. Where there is no command line to add flags to (a script, a scheduler), the environment does the same: `CK3SM_VERBOSITY` (a number, or a level name such as `extra`) and `CK3SM_SHOW` (e.g. `transplant:1,timing:1`).

Results go to standard output; warnings, errors and the extra detail go to standard error. The `--report` JSON is the same at every level.

`-v` and `-q` count the same whether they come before or after the command: `-v migrate`, `migrate -v` and `-v migrate -v` (which is `-vv`) all work.

## The parts of the output

| Part | What it carries | Where it goes |
|---|---|---|
| `rules` | the rules applied and their counts; the `rules` listing | standard output |
| `transplant` | the new-map transplant's plan and write counts (R14 to R17) | standard error |
| `lint` | the checks' verdict and findings | standard output |
| `io` | reading and writing saves: what was written, sizes, hashes | standard output |
| `timing` | time taken per rule | standard error |

Warnings and errors go to standard error whatever part they belong to.

## Where results go

- **The migrated save**: `-o`, or `<name>.migrated.ck3` beside the input. With two custom-faith shapes, two files: `<name>__wos-faith.migrated.ck3` and `<name>__wos-rite.migrated.ck3`. `--dry-run` writes nothing.
- **The checks**: printed, and written next to each output with the output's `.ck3` replaced by `.lint.json` (`My_Old_Campaign.migrated.lint.json`). `lint` itself writes them only with `--json`.
- **The report**: only with `--report`. With two outputs, one report per output, named the same way (`My_Old_Campaign__wos-faith.report.json`). See [Reports](reports.md).
- **The exit code**: see [Checking a save](lint.md#exit-codes).
