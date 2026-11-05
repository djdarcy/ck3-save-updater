# Contributing to ck3-save-updater

Thank you for helping. This tool changes other players' campaigns, so every contribution is held to one standard. It must not break a save, and it must not do anything a player would not expect.

## The promises every change keeps

- **A player's own save is never changed.** The tool writes a new file beside it.
- **Only what the game defines.** A rule never writes a key the current game, or a mod the player lists, does not define.
- **Matched by what a thing is, never by its name alone.** A replacement is chosen through the game's own definitions: the same event, the same tree position, the same unit class and stats. The rule cites the files that show it.
- **The base game first.** The updater uses vanilla definitions. It does not ship or require a compatibility mod.
- **Nothing silently lost.** What cannot carry over is reported, and listed in [What doesn't carry over](docs/not-carried-over.md).

## Reporting a bug

Please include:
- the tool's version (`ck3update -V`) and the game version you play;
- your save's game version and its mod list (`ck3update status "My Save"` prints both);
- what you expected and what happened, with the exact command and its output;
- for a problem in the game, the lines from the game's `error.log` that mention it.

## Pull requests

AI-assisted contributions are welcome. The bar is the same for everyone, and so are the questions the [pull request template](.github/pull_request_template.md) asks. **A pull request that does not answer them will be closed unread.**

### Explain it in your own words

Write, yourself, what the change does and why. Do not paste a model's summary. If you cannot explain a line, do not submit it.

### Say which AI tools you used, and for what

Name each tool or model, and what it did: wrote code, wrote tests, suggested a design, reviewed, or nothing. "None" is a fine answer.

### Say how you vetted it

At the least:
- you read every changed line;
- the full test suite passes (`python -m pytest -q`);
- every new test fails without your change, and passes with it. Show it once, by reverting the behaviour (not the function signature) and running the test.

For a change to what the tool writes into a save, also:
- run it on a real save of your own, never your only copy;
- load the updated save in the game, play a few months, then pause and save;
- report the error-log lines for what you changed, before and after.

### What will be refused

To keep players safe, a pull request is refused if it:
- reaches the network, or adds telemetry;
- changes, moves or deletes any file other than the new save it writes, and its report;
- runs code when a module is imported, or adds obfuscated or encoded code, or a binary;
- adds a dependency, or changes the CI workflows or the release process, without discussing it in an issue first;
- writes keys the game does not define, or drops data without reporting it.

### Before you start

For anything larger than a small fix, open an issue first. Say what you want to change and how you will test it. Most work happens in the rules (`ck3_save_migrator/rules/`) and the shipped patch packs (`ck3_save_migrator/packs/`). [Writing a patch](docs/writing-a-patch.md) shows the declarative `patch.toml` form, which is preferred over code.

Each change also updates [the rules reference](docs/rules.md) where it adds or changes a rule, and the [CHANGELOG](CHANGELOG.md) in plain language a player can follow.

## Working with an AI agent

[AGENTS.md](AGENTS.md) is written for AI coding agents working in this repository. Point your agent at it.

## Code of Conduct

Be kind, and assume good faith. Maintainers may close pull requests that ignore the questions above, or that cannot be verified.
