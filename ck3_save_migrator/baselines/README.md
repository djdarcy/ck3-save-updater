# baselines

This folder holds one file per game version, recording the shape of a save that version wrote.

For each kind of database in a save, such as `faiths/database` or `living`, the file records how many entries there are. For each field it records the share of entries that carry it, and the share that leave it empty. It records names and shares, never values. Which fields exist is stable for a game version, while values belong to one moment. This lets lint's field check work for a player who has no reference save.

- `1.20.1.2/fields.json` is the record for 1.20.1.2.
- `1.21.0/fields.json` is the record for 1.21.0.

## Who reads it

`baselines.py` loads the files through `importlib.resources` (`load_baseline`, and `shipped_versions` for the list). `lint.py` uses it when there is no reference save of the save's own version. `scripts/make_field_baseline.py` writes a record from any save the game wrote itself; a fresh game, saved once, is best.

## How it ships

`pyproject.toml` lists `baselines/*/fields.json` as package data.

## Oddities

This folder, `known_genes/` and `known_titles/` are all built-in facts about game versions, each written by a script in `scripts/`. They differ in format (JSON here, TOML and game files there). They also differ in how they are found: `baselines.py` uses `importlib.resources`, while `dna.py` and `deadtitles.py` build paths from `__file__`.
