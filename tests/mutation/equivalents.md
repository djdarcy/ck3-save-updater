# Mutation survivors triaged as equivalent or don't-care

Guarded authority, not an allowlist (see the test-mutation skill): entries are grouped under the target file and its `git hash-object` (first 12). When the file's hash no longer matches its heading, every entry under it is stale: re-triage before reuse, and never feed stale entries to a generator. Only separated-generation runs (a fresh agent with the source and nothing else) write here.

## ck3_save_migrator/baselines.py @ f33d1246dbae

- `if not n:` -> `if n is None:` -- **don't-care** -- differs only when every entry of a database fails to parse: the database is then recorded with 0 entries and no fields, which every reader (`as_coverage`, `coverage_gaps`) already treats as "nothing to compare with". 2026-11-16, generation mode 1.
- `continue` -> `break` (the zero-entry skip in `build_baseline`) -- **don't-care** -- the same case as `if not n`: reached only when every entry of a database fails to parse. 2026-11-16, generation mode 1, round 2.
- `save_versions(g[:65536])` -> `save_versions(g[:256])` -- **don't-care** -- the game writes `version=` among the first fields of `meta_data` (byte 40 or so in the 1.20.1.2 reference save); the wide window is a margin, not a behaviour a save exercises. 2026-11-16, generation mode 1, round 2.
- `_ROUND = 4` -> `_ROUND = 3` -- **don't-care** -- the shares' fourth decimal place feeds no decision: the check's thresholds are 0.9 and 0.97, and a 1.20.1.2 share sits at most 0.0005 from its four-place value. 2026-11-16, generation mode 1.
