"""variant_drop_contracts: a diagnostic copy of a save with named vassal contracts removed (the contract entry and
its id in every `vassal_contracts={ ... }` list of a character), for an exit test. Never a migration.

2026-10-28, the crash on exit: contract_links.py found one contract in play5 the game's own save has no
counterpart for, 8774, whose vassal (3224) is dead; the hypothesis is that nothing tears such a contract down with
its characters, so the final teardown reads its freed vassal (ck3+0x24ca0bb).

Usage: python -I tests/one-offs/variant_drop_contracts.py <in.ck3> <out.ck3> <contract id> [<contract id> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

LIST = re.compile(rb"\bvassal_contracts=\{([^{}]*)\}")


def main():
    src, out, *ids = sys.argv[1:]
    drop = {i.encode() for i in ids}
    save = sf.read_save(src)
    d = save.gamestate
    p = gs.EditPass()
    entries = refs = 0
    vc = gs.find_section(d, "vassal_contracts")
    for sub in gs.iter_children(d, *vc.body):
        if sub.block is not None:
            for e in gs.iter_entries(d, *sub.block.body):
                if e.key in drop:
                    p.delete_block(d, e, "variant")
                    entries += 1
    living = gs.locate(d, "living")
    for m in LIST.finditer(d, living.open, living.close):
        toks = m.group(1).split()
        if any(t in drop for t in toks):
            kept = b" ".join(t for t in toks if t not in drop)
            p.add(gs.Edit(m.start(1), m.end(1), b" " + kept + b" " if kept else b" ", "variant"))
            refs += sum(t in drop for t in toks)
    p.apply_to(save)
    sf.write_save(save, out, force=True)
    print(f"wrote {out}: {entries} contract entries and {refs} list references removed for {sorted(ids)}")


if __name__ == "__main__":
    main()
