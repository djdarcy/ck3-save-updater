# Tools

The project keeps a folder of standalone Python scripts, `tests/one-offs`: small checks and fixes written while working on a save, such as counting the characters of a faith or comparing two saves. The `tools` command makes them easy to find and run: `tools list` shows them with a one-line description, `tools run` runs one, and `tools path` prints where one is. Nothing extra needs installing.

The command never changes a script, and writes nothing anywhere. Each script runs exactly as it would if you ran `python <script> ...` yourself: as its own process, run as a file (never as a module, whatever else its folder holds), from your current folder, with your terminal's input and output and the arguments you give, and `tools run` exits with the script's own exit code.

## Using it

```bash
ck3update tools list
ck3update tools run diff_saves "Old.ck3" "New.ck3"
ck3update tools path diff_saves
```

- `tools list` prints one line per script: its name and the first line of its docstring (empty when it has none). A script is never run or imported to list it; its docstring is read from the file.
- `tools run <name> [args...]` runs the script `<name>.py` with every argument after the name passed on unchanged, options such as `-h` included.
- `tools path <name>` prints the script's full path, for opening it or running it yourself.

Every `*.py` file directly in the scripts folder is a tool, named by its file name without `.py`. Other files and subfolders are not tools. An unknown name is refused, naming it, with exit code 2.

## Where the scripts are found

The first of these that is set:

1. `--scripts-dir <folder>`, written after `tools` and before `list`, `run` or `path`: `ck3update tools --scripts-dir my_scripts list`;
2. the environment variable `CK3SM_SCRIPTS_DIR`;
3. the `tests/one-offs` folder of the source checkout the tool is running from. An installed package has no such folder.

When none is set, the command says so and exits with code 2.

## A tool in a run patch

A [run patch](writing-a-patch.md#when-to-run-a-program-instead-run) can name a script from the scripts folder instead of spelling out its command:

```toml
[run]
tool = "edit_save"
args = ["@@input@@", "@@output@@"]
```

This runs `<scripts folder>/edit_save.py` with the Python running the tool, followed by `args`, which take the same `@@name@@` variables as `command`: the same command `tools run` builds. It is the same as `command = ["@@python@@", "<scripts folder>/edit_save.py", "@@input@@", "@@output@@"]`. The scripts folder is the variable `scripts_dir` when given (`--var scripts_dir=<folder>`), else found as above; when there is none, or the script is not in it, the patch is refused, naming the folder. Like any run patch in a pack folder, it needs `--allow-run`, or a trusted pack in your packs folder.
