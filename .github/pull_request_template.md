## In your own words

<!-- What does this change do, and why? Write it yourself; do not paste an AI summary. If you cannot explain a line, do not submit it. -->

## AI tools used

<!-- Name each tool or model and what it did (wrote code, wrote tests, suggested a design, reviewed). "None" is a fine answer. -->

## How you vetted it

- [ ] I read every changed line
- [ ] `python -m pytest -q` passes (paste the last line):
- [ ] Each new test fails without the change and passes with it (say how you checked):
- [ ] For a change to what is written into a save: I ran it on a real save (not my only copy), loaded it in the game, played a few months, paused and saved
- [ ] Error-log lines for what I changed, before and after:

## Type of change

- [ ] Bug fix
- [ ] New or changed rule
- [ ] Documentation
- [ ] Other (say what):

## Checklist

- [ ] No network access, telemetry, code run at import, obfuscated code or binaries
- [ ] Only the new save and its report are written; no other file is changed, moved or deleted
- [ ] No key the game or a listed mod does not define is written
- [ ] What cannot carry over is reported (and listed in `docs/not-carried-over.md`)
- [ ] `docs/rules.md` and `CHANGELOG.md` updated in plain language, if players will see the change
