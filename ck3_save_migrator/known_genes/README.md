# known_genes

This folder holds names-only copies of the face gene definitions of old game builds and old portrait-mod builds.

A face in a save is a string of gene values, and reading it needs the list of genes the save's builds had. A player usually no longer has those old builds. So the tool ships their gene files, stripped to names (gene, template, index), and reads old faces with them. The face rule reads them when the player passes `--face-changes known-genes`.

- `vanilla_1.8.2/` holds the game's own genes from 1.8.2.
- `cfp_3.1.11/` holds Community Flavor Pack's genes.
- `epe_1.6.0/` holds Ethnicities and Portraits Expanded 1.6.0.
- `epe_2022-12_tail/` holds three genes that the December 2022 build of that mod added after 1.6.0's last gene.

Each folder has `common/genes/*.txt`, and all but the tail have a `table.toml`. The table records the name, version, Workshop id and source, and which mod files the folder stands in for. `scripts/gene_table.py` writes them.

## Who reads it

`dna.py` defines `KNOWN_GENES` and `load_tables`. The face rule in `rules/faces.py` uses them through `dna.py`.

## How it ships

The package-data patterns `known_genes/*/common/genes/*.txt` and `known_genes/*/table.toml` in `pyproject.toml`.

## Oddities

`epe_2022-12_tail/` has no `table.toml`. It is wired by a fixed `KNOWN_TAILS` list in `dna.py`, so it takes a different route from its siblings. `deadtitles.py` borrows `load_tables` and `table_label` from `dna.py`, so a loader used by two folders sits in the face module.
