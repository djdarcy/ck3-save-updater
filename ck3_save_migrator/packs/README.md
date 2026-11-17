# packs

This folder holds the shipped patch packs. They are the migrator's rules, written as data files.

A pack is a folder with a `pack.toml` and one subfolder per patch. Each patch folder has a `patch.toml`, and sometimes a small data file or script beside it. The engine in `patches/` reads these files and runs them. Nothing here is imported as a module. The empty `__init__.py` files only let the package read the folders as package data.

- `to_1_20/` brings a 1.8 to 1.19 save to 1.20. It holds the numbered rules R1 to R32 (R13, R18 and R24 are not used). Its `pack.toml` gives the run order and the save and game versions it applies to.
- `to_1_21/` is a frame for the 1.20 to 1.21 step. It declares the versions it spans and has no patches yet. A frame never counts as covering a version gap, so the plan does not treat it as an update.
- `edits/` holds the built-in edits that `ck3update edit` runs, E1 to E13. They use patch format 2, and each is marked `kind = "edit"` or `kind = "view"`. `update` never runs them.

## Who reads it

- `patches/pack.py` finds the folders through `importlib.resources`.
- `rules/__init__.py` builds the rule `REGISTRY` from `to_1_20`.
- `plan.py` lists `to_1_21` among the plan's packs.
- `edit.py` loads `edits`.
- `dna.py` reads one data file directly, `to_1_20/R19-dna-layout/portraits_version.toml`.

## How it ships

`pyproject.toml` lists the package data: `*/pack.toml` and the patch files under `*/*/` (`.toml`, `.py` and `.json`). A new kind of data file in a patch folder needs a new pattern there.

## Oddities

A code patch only names a function elsewhere, for example `ck3_save_migrator.rules.religion_1_20:r8_religion_transplant`. So much of the real rule logic still lives in `rules/` and `builtin_edits.py`, and the pack holds the metadata. The folder name `to_1_20` matches a module name in `rules/` (`to_1_20.py`), but the two are different things.
