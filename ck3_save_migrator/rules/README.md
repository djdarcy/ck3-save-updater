# rules

This folder holds the Python functions behind the migration rules, and the `REGISTRY` of rules the migrator runs.

Most rules edit a save through an `EditPass`, return counts, and cite the measurement they rest on. A rule's id, order, title and requirements are not declared here. They are declared in the `to_1_20` pack under `packs/`, and `rules/__init__.py` builds `REGISTRY` by calling `rules_from_pack()`. A simple rule is a declarative patch in the pack and has no function here. A complex rule is a code patch whose `script` names a function in this folder.

- `to_1_20.py` holds the rules that remove what 1.20 rejects, the detection helpers, and the version bump. It is the largest file in the package.
- `religion_1_20.py` holds the rules that bring in the 1.20 religion databases and map old faiths to rites.
- `transplant_1_20.py` holds the rules that bring 1.20's new map regions in from a reference save.
- `faces.py` holds the rule that carries every face into the target's gene layout. The logic itself is in `dna.py`.

## Who reads it

- `cli.py` imports `REGISTRY`, `select`, `run_rules` and `missing_prerequisites`.
- `detect.py` and `lint.py` import helpers from `to_1_20.py`.
- `lint.py` also imports from `transplant_1_20.py`.
- The packs call the functions by name.

## How it ships

It is ordinary package code.

## Oddities

The run order is stored twice. The pack's `order` list and the `_ORDER` list in `rules/__init__.py` must match, and the import raises an error when they do not. `detect.py` and `lint.py` import from the rule modules, while the rule modules import helpers from `lint.py`, so `lint.py` needs a late import. Those two directions suggest the shared helpers want a home of their own. The file names carry the 1.20 target, so the 1.21 rules will need a decision about where they go.
