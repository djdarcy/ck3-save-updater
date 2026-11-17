# known_titles

This folder holds a names-only copy of an old game version's map of titles.

A 1.8 save refers to titles that 1.20 removed or moved. Deciding what to do with each one needs the old map, which a player has only if they still have the old game installed. So this folder ships the old map as title keys, their nesting, and each barony's province, with no other values. The dead-title rule uses it when the player gives no `--old-game-dir`.

- `vanilla_1.8.2/` holds `common/landed_titles/*.txt` from 1.8.2 and a `table.toml`. The table names the game line the folder covers, 1.8.

`scripts/title_table.py` writes it.

## Who reads it

`deadtitles.py` defines `KNOWN_TITLES` and picks the table whose game line matches the save's version.

## How it ships

The package-data patterns `known_titles/*/common/landed_titles/*.txt` and `known_titles/*/table.toml` in `pyproject.toml`.

## Oddities

It has the same shape as `known_genes/`, and `deadtitles.py` borrows `load_tables` from `dna.py` to read it. Only the 1.8 line has a built-in map today. A save from another old line needs `--old-game-dir`.
