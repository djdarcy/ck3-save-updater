# savediff -- vendored

savediff is a planned library that is not yet its own repository. It lives here, inside the host package, until it is; it is kept pure (no import of the host, standard library only, no mention of the host's name) so that becoming a repository is a copy of this folder. A test of the host enforces that, and checks that every `.py` file in this folder is named below.

All lifted code was copied from the host repository at commit `e0a6ab3` by line range (`sed -n 'A,Bp'`), then edited. Paths below are relative to the host repository's root.

## Files

| File | Origin |
|---|---|
| `__init__.py` | new: the module docstring (what savediff is, the survival rule, the purity rule) and the public names |
| `text.py` | lifted: the read-only part of the host's gamestate reader, and its lint module's section index (below) |
| `shape.py` | lifted: the probe `tests/one-offs/shape_diff.py` (below) |
| `ids.py` | generalised (written anew) from the same probe's id arithmetic |
| `keys.py` | generalised (written anew) from the same probe's key readers |
| `schema.py` | lifted: the host's id schema, `ck3_save_migrator/idschema.py` (below) |
| `graph.py` | new: the reference graph, its checks, joins and join diffs |
| `_VENDORED.md` | this record |

## text.py

Copied, in this order, after a new module docstring:

| From | Lines | What |
|---|---|---|
| `ck3_save_migrator/gamestate.py` | 23-36 | imports; `_BRACE_OR_STRING`, `_TOKEN`, `_VALUE_PREFIXES`, `_WS` |
| `ck3_save_migrator/gamestate.py` | 37-77 | `GamestateError`, `Block`, `Child` |
| `ck3_save_migrator/gamestate.py` | 78-137 | `match_brace`, `_key_before`, `iter_entries` |
| `ck3_save_migrator/gamestate.py` | 183-191 | `find_child` |
| `ck3_save_migrator/gamestate.py` | 201-259 | `iter_children` |
| `ck3_save_migrator/gamestate.py` | 260-261 | `_TOP_KEY` |
| `ck3_save_migrator/lint.py` | 81-107 | `SectionIndex` |

Not copied: the gamestate reader's module docstring (lines 1-21), its top-level index cache (`_TOP_INDEX`, `_top_index`, lines 139-162), `find_sections`, `find_section`, `locate` (165-199), and the edit machinery (`_SMALL_BLOCK`, `child_at`, `find_keys`, `Edit`, `RuleCount`, `removal_span`, `EditPass`, lines 263-467).

Changed after the copy:

- `GamestateError` renamed `SaveTextError`, everywhere it occurs (the class, the raises, the docstrings).
- `from dataclasses import dataclass, field` became `from dataclasses import dataclass` (`field` was used only by the edit machinery).
- `SectionIndex`: the `gs.` prefixes removed (it now lives beside `_TOP_KEY`, `match_brace` and `Block`); its docstring rewritten; the comment "index the rest" on the unclosed-section `break` corrected to say what the code does (it stops; the sections after an unclosed one are not indexed); its `block()` method now calls the new `locate()` and caches the result.
- New: `locate(index, path)`, walking `a/b/c` from the index's first block of `a` through `find_child`, returning `None` (not raising) when a step is absent or does not parse.
- New: `strip_text_header(raw)`: a `SAV` header of kind `00` (bytes 5-6) is dropped with its line; any other kind raises `SaveTextError` naming it; bytes that do not start with `SAV` are returned unchanged.

## shape.py

Copied from `tests/one-offs/shape_diff.py`, after a new module docstring:

| Lines | What |
|---|---|
| 25 | `from __future__ import annotations` |
| 28, 31-32 | `import re`; `Counter`; `dataclass, field` |
| 41-42, 46 | `TITLE_KEY`, `SCALAR_LIMIT`, `_TOP` |
| 60-137 | `Shape`, `_kind`, `_shape`, `shape` |

Changed after the copy:

- Imports: `from . import text as gs` added; the probe's `lint as L` replaced by `gs.SectionIndex`; `gs.GamestateError` became `gs.SaveTextError`.
- The probe's constants made keyword parameters of `shape()`: `scalar_limit` (default `SCALAR_LIMIT`, 32 MiB), `db_threshold` (default 50, the probe's literal `> 50`) and `child_sample` (default 60, the probe's literal `[:60]`); `_shape()` takes `scalar_limit` as an optional third argument. `shape()` gained a docstring.
- New: `shape_rows(witnesses)`.

## ids.py

Written anew, generalising the probe's `LOW, GEN, NONE` constants (line 40), its `Keys.tr_char` (lines 184-185) and the title-offset mode in `keys()` (lines 191-196). Differences from the probe: `offset_by_mode` takes any two key -> id maps, returns `(None, set())` when nothing is shared at the same generation (the probe raises `IndexError`), and breaks a tie by the smallest offset (the probe's `Counter.most_common` picks by insertion order). `generation()` returns the high byte shifted down to 0-255; `translate()` masks the shifted slot to 24 bits.

Added after the copy: `NONE64` (18446744073709551615, the same "no id" as some fields write it, 64 bits wide), `NONES` (both) and `is_none()`. A real 1.20 save showed the 64-bit form as dangling links.

## keys.py

Written anew, generalising the probe's `ids` (lines 143-148, as `entry_keys`), `title_keys` (151-163, as `field_keys`), `characters` (166-170, as `union_keys`), the `character_lookup` reader inside `keyed_gaps` (lines 265-268, as `scalar_map`, keeping its line pattern), and the per-section gap counts of `keyed_gaps` (as `key_gaps`). Differences from the probe:

- `field_keys` reads the field through `iter_children` of the whole entry body, so "depth 1" is exact. The probe reads only the first 4,096 bytes of each entry, requires `key=` at a line start after tabs, and counts braces without skipping quoted strings.
- `entry_keys`, `field_keys` and `scalar_map` return empty when the path is absent; the probe's `title_keys` and `character_lookup` reader raise.

## schema.py

Copied from `ck3_save_migrator/idschema.py` at commit `e0a6ab3`, lines 17-433 (everything after its module docstring: `PLAIN`, `TYPED`, `TRAIT`, `REVIEW`, `SPACES`, `IDENTITY`, `KIND_SPACE`, `TYPE_SPACE`, `FIELDS`, `_DATE`, `norm_key`, `classify`, `_family`, `_plain`, `PLAIN_FIELDS`), after a new module docstring.

Changed after the copy, comments only: "Unit 2's load decides." became "Not settled."; "(Unit 5b)" was dropped from the comment above the relations and opinions tables. No value changed. A host test (`tests/test_savediff_schema_mirror.py`) checks that every table here equals the host's and that `classify` gives the same answer for every listed path, so the copy cannot drift silently: when the host's table changes, that test fails until this copy is updated.

## graph.py

Written anew. It reads entries with `text.iter_children` and normalises field paths with `schema.norm_key`; the shapes of the checks follow three defects found in a migrated save (a barony listed first in a domain beside its county, mercenary company titles not keyed `x_mc_<company id>`, a company record pointing at a destroyed title).

Changed after the first run on real saves: every check treats both widths of the "no id" (`ids.NONES`) as no id; `duplicates` no longer lists an id repeated under one section name only (1.20 writes every `dead_unprunable` entry twice) and counts such repeats as `"<space> repeats"` instead.
