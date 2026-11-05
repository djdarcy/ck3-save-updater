# AGENTS.md

Guidance for AI coding agents working in this repository. Read [CONTRIBUTING.md](CONTRIBUTING.md) as well: everything there applies to you.

## What this project is

`ck3update` (package `ck3_save_migrator`, published as `ck3-save-updater`) brings an old Crusader Kings III save forward to the installed game version. Players run it on campaigns they care about. A mistake here can ruin a campaign that took years to play.

## Commands

```bash
python -m pytest -q                       # the full suite; it must pass before you finish
python -m ck3_save_migrator --version     # the CLI without installing
pip install -e ".[dev]"                   # an editable install with the test tools
```

## Where things are

- `ck3_save_migrator/rules/to_1_20.py`: the rules, with each rule's reasoning in its docstring.
- `ck3_save_migrator/packs/to_1_20/`: one folder per rule (`patch.toml`), plus `pack.toml` for the order.
- `ck3_save_migrator/detect.py`: what `status` reports for each rule.
- `docs/rules.md`: one row per rule, for players. `CHANGELOG.md`: plain language.
- `tests/`: one test file per rule (`test_r<N>_*.py`), on small made-up saves.

## Rules you must follow

1. **Never change the input save.** The tool writes a new file.
2. **Never write a key the game does not define.** Check the game's and the listed mods' `common/` folders, the way R25 and R30 do.
3. **Match by lineage, not by name.** Find the replacement through the game's own definitions (the same event, the same tree position, the same class and stats), and cite the files in the rule.
4. **Report what you cannot carry.** Count it in the rule's result, and list it in `docs/not-carried-over.md`.
5. **No network access, no telemetry, no code that runs at import, no new dependencies** without an issue first.
6. **Tests must be able to fail.** Each new test must fail when the change is reverted. Revert the behaviour, never the API, and say which tests failed and which passed either way.
7. **A rule that changes save content needs a game load** by the human you work for: a real save, a few months of play, a paused save, and the error-log lines before and after. Say plainly if this was not done.

## When you open a pull request

The human you work for must write the summary in their own words, and fill in the template's AI-tools and vetting sections truthfully. Do not write those sections for them, but you can help them edit if they're having difficulties expressing themselves or if there are language-barriers (but say you did edits -- the human is responsible for what is written and I as the maintainer want to know what they are trying to do in their own words). List what you changed and what you ran, so they can check it.
