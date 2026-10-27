# Reports

`migrate --report <file.json>` writes a JSON account of the migration: which rules ran, what each one changed, what was lost and why, and what the checks found. It is the full record; the printed output is a summary of it. The report is the same at every verbosity level.

```bash
ck3-save-migrator migrate "My_Old_Campaign.ck3" --reference "A_New_1_20_Game.ck3" --report "My_Old_Campaign.report.json"
```

When a custom faith gives two outputs, each gets its own report: `My_Old_Campaign__wos-faith.report.json` and `My_Old_Campaign__wos-rite.report.json`. With `--dry-run` the report is still written, with `output` set to `null`. When no rule changes anything, nothing is written, the report included.

## Fields

| Field | What it holds |
|---|---|
| `tool` | the tool's name and version |
| `input`, `input_sha256` | the input save and its hash |
| `output`, `output_sha256` | the written save and its hash (`output` is `null` on a dry run) |
| `dry_run` | whether this was a dry run |
| `game_dir` | the game folder used, or `null` |
| `reference` | the reference save used, or `null` |
| `wos_shape` | how a custom faith was carried in this output: `faith` or `rite` |
| `assumptions` | every assumption a rule made, gathered from all rules |
| `lost` | everything a rule could not carry, and why, gathered from all rules |
| `rules` | one entry per rule that ran, in order (below) |
| `lint` | the checks' findings for this output, or `null` with `--no-lint` (below) |

### Each rule

| Field | What it holds |
|---|---|
| `id`, `name`, `since`, `description` | as `ck3-save-migrator rules` lists them |
| `matched` | how many places the rule found to look at |
| `edited` | how many edits it made |
| `extra` | the rule's own details, when it has any. A rule that did nothing says why under `skipped` |

What `extra` holds depends on the rule. A few examples: R2 lists values it left unchanged and why; R3 names each title whose names it moved; R7 gives the version fields before and after. For the new-map rules, R14 counts the titles and provinces planned; R15 has a `table` with one row per title it settled (its key, kind, class, successors, holder, reason and outcome in words); R16 counts rulers, courtiers and relatives and lists displaced rulers; R17 lists everything written, every barony re-parented, settled or left to the game, the empty provinces filled, the expansion orders and leases added, and the links dropped. See [New-map regions](new-map-regions.md).

### The checks

`lint` holds the same findings as the `.lint.json` file written next to the output: the counts of `errors`, `warnings`, `reject` (kinds of line the game will log) and `info`, then `findings`, each with its `check`, `severity`, `count`, a plain-words `gloss`, a few `examples` and a `note`; `stats` (how many characters, titles, faiths and so on the save has); and `skipped` (checks that could not run, and why). See [Checking a save](lint.md).

## Example

Built from the project's test fixtures (a tiny synthetic 1.8.1 save, no reference save, no game folder), shortened where marked:

```json
{
  "tool": "ck3-save-migrator 0.3.4",
  "input": ".../My_Old_Campaign.ck3",
  "input_sha256": "77d22541a123ba0cb8e5ec12dd04a9f93d3900a739866a32bac01770d3630ab7",
  "output": ".../My_Old_Campaign.migrated.ck3",
  "output_sha256": "2a64545504750ad921deeba4c9c16b2fab45c4c3da66217e00ded3a49e61cea7",
  "dry_run": false,
  "game_dir": null,
  "reference": null,
  "wos_shape": "faith",
  "assumptions": [],
  "lost": [],
  "rules": [
    {
      "id": "R1",
      "name": "opinions-converging",
      "since": "1.8.1<v<=1.20.1.2",
      "description": "delete converging={} in opinions temporary_opinion blocks",
      "matched": 2,
      "edited": 2
    },
    {
      "id": "R8",
      "name": "religion-transplant",
      "since": "1.20.0 (By God Alone: faiths/rites databases)",
      "description": "replace religion with a 1.20 reference's religion/faiths/rites/organizations, ids translated",
      "matched": 0,
      "edited": 0,
      "extra": {
        "skipped": "no reference save (--reference)"
      }
    },
    {
      "id": "R7",
      "name": "version-bump",
      "since": "n/a",
      "description": "set meta_data version/save_game_version to the target",
      "matched": 2,
      "edited": 2,
      "extra": {
        "before": {"save_game_version": "8", "version": "\"1.8.1\""},
        "after": {"version": "\"1.20.1.2\"", "save_game_version": "18"}
      }
    }
  ],
  "lint": {
    "errors": 0,
    "warnings": 2,
    "reject": 0,
    "info": 0,
    "findings": [
      {
        "check": "title holders are characters in the save",
        "severity": "warn",
        "count": 1,
        "gloss": "Titles held by a number no character in the save has",
        "examples": ["title 0: holder=66845"],
        "note": ""
      }
    ],
    "stats": {"characters": 1, "living": 1, "titles": 4, "houses": 0, "rites": 0, "faiths": 0, "religions": 0, "cultures": 0, "game_data": []},
    "skipped": ["DNA length: no reference save to learn the target length from"]
  }
}
```

The real file has one entry per rule that ran (twelve here), the second warning, and every skipped check; `input` and `output` are full paths.
