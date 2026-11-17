# _vendor

This folder holds code copied in from the author's other projects, so the package runs without installing them.

The underscore marks it as not part of the public interface. Each piece records where it came from, and whether it has changed since.

- `colors.py` is the color helper from dazzlecmd-lib. Its header gives the commit it was copied at. It matches upstream apart from two changes it lists: a `BLUE` constant, and the `CK3UPDATE_COLOR` environment variable.
- `savediff/` compares saves by entity rather than by line (`text`, `shape`, `keys`, `ids`, `schema`, `graph`). It lives here until it becomes its own repository. It must not import the host package, and a test enforces that. `savediff/_VENDORED.md` names every file and where each part came from.

## Who reads it

`cli.py` and `plan.py` import `colors`. `baselines.py`, `lint.py` and `scripts/conversion_scorecard.py` use `savediff.keys` and `savediff.text`. Tests use more of `savediff`.

## How it ships

It is ordinary package code.

## Oddities

`savediff` was lifted out of this package's own `gamestate.py` and `idschema.py`, so the same logic exists in two places. The copy is deliberate, to keep `savediff` free of host imports. Both copies have to be kept in step until one of them goes.
