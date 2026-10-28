"""variant_contract_groups: diagnostic copies of a save for the crash on exit (2026-10-27/28), never a migration.

The crash: on Exit to Desktop the game destroys its subject contracts after its characters, and a contract whose
cleanup flag is unset reads its freed character (ck3+0x24ca0bb, CSubjectContract's destructor; with or without
mods; play5 crashes, the game's own reference save does not). The migrated saves still carry 1.8's
`vassal_contracts={ active={...} }` with no `contract_group` and no `liege_dynasty_date`; the game's own saves write
`vassal_contracts={ database={...} }` with both, and when the game re-saves a migrated save, about 60% of its
contracts still have no group.

Modes:
  strip   delete `contract_group` from every vassal contract (the falsifier: run on the game's own save, it
          should then crash on exit if the missing group is the cause)
  legacy  strip, also drop `liege_dynasty_date`, and rename `database` to `active` (the 1.8 shape in full)

Usage: python -I tests/one-offs/variant_contract_groups.py <strip|legacy> <in.ck3> <out.ck3>
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def main():
    mode, src, out = sys.argv[1:4]
    save = sf.read_save(src)
    d = save.gamestate
    vc = gs.find_section(d, "vassal_contracts")
    p = gs.EditPass()
    counts = {"contract_group": 0, "liege_dynasty_date": 0, "renamed": 0, "entries": 0}
    for sub in gs.iter_children(d, *vc.body):
        if sub.block is None:
            continue
        for e in gs.iter_entries(d, *sub.block.body):
            if not (e.key and e.key.isdigit()):
                continue
            counts["entries"] += 1
            keys = ["contract_group"] + (["liege_dynasty_date"] if mode == "legacy" else [])
            for k in keys:
                if p.delete_key(d, e, k, "variant"):
                    counts[k] += 1
        if mode == "legacy" and sub.key == b"database":
            p.rename_key(d, vc, "database", "active", "variant")
            counts["renamed"] = 1
    p.apply_to(save)
    sf.write_save(save, out, force=True)
    print(f"wrote {out} ({mode}): {counts}")


if __name__ == "__main__":
    main()
