# patches

This folder is the engine that reads packs and turns them into rules the migrator can run.

The idea is that a rule is a file a player can read and write, not only Python code. A patch is declared in a `patch.toml` in one of three ways. It can list declarative edits, name a script function, or name a program to run over the save. This folder loads and checks those files, plans the edits, applies them, and wraps each patch as a `Rule` object. The data it runs is in `packs/`. The functions that code patches name are in `rules/` and `builtin_edits.py`.

- `model.py` loads and checks `pack.toml` and `patch.toml` (formats 1 and 2). Each error names its file and field.
- `pack.py` turns a pack into `Rule` objects (`rules_from_pack`). It decides whether a patch is needed or already done (`verdict`, `status`). It also names the shipped packs (`SHIPPED`, `SHIPPED_AFTER`).
- `engine.py` plans a declarative patch's edits and applies them in one splice, so the bytes it does not touch stay identical.
- `paths.py` resolves paths such as `a/*/**/b` over a large gamestate.
- `blockindex.py` indexes every block of a gamestate in one pass, so `paths.py` can find ancestors quickly. It caches the index on disk.
- `run.py` runs a patch that is a separate program, and fails closed.

## Who reads it

`rules/__init__.py`, `cli.py`, `plan.py`, `edit.py`, `userpacks.py`, `config.py`, `dna.py` and `detect.py` import from it. Several of them import only `patches.model.tomllib`, as a shared TOML reader.

## How it ships

It is ordinary package code.

## Oddities

`pack.py` imports from `rule_types.py` rather than from `rules/`. That avoids a circular import, because `rules/` builds its registry from this folder. Modules such as `config.py` take their TOML reader from `patches.model`, which suggests the reader belongs in a shared module.
