"""Which lists does a fresh game give IN FULL to every entity of a kind, and which of our entities are short of them?

The 1.20 per-entity audit (DWP 2026-11-20__15-17-51, build step 1; board U33). The innovation finding generalized:
in ref-1.20 every culture lists every innovation, and ours-1.20 lacked one (Pole Vault) on 228 cultures. This looks
for every such universal list in a database: a depth-1 field holding `{ type=X ... }` rows, where every entity of
the reference carries the same set of X. Then it counts, per field, the entities of ours that lack any of them.

Usage: python -I tests/one-offs/thinking/universal_lists_audit.py <ref.ck3> <ours.ck3> [db ...]
       dbs default: culture_manager/cultures faiths/database
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

FIELD = re.compile(rb"\n\t\t\t([a-z_]+)=\{")
ROW = re.compile(rb'type="?([a-z_0-9]+)')


def lists(g: bytes, db: str) -> list[dict[str, set]]:
    out = []
    for e in gs.iter_entries(g, *gs.locate(g, db).body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        fields = {}
        for m in FIELD.finditer(b):
            close = gs.match_brace(b, m.end() - 1)
            inner = b[m.end():close]
            rows = set(x.decode() for x in ROW.findall(inner))
            if rows:
                fields.setdefault(m.group(1).decode(), set()).update(rows)
        out.append(fields)
    return out


def main(argv):
    ref, ours = read_save(argv[0]).gamestate, read_save(argv[1]).gamestate
    for db in argv[2:] or ["culture_manager/cultures", "faiths/database"]:
        r, o = lists(ref, db), lists(ours, db)
        names = set().union(*[set(x) for x in r])
        print(f"== {db}: ref {len(r)} entities, ours {len(o)}")
        for f in sorted(names):
            holders = [x.get(f, set()) for x in r]
            if not all(holders) or len(holders) < 2:
                continue
            universal = set.intersection(*holders)
            if not universal or any(h != universal for h in holders):
                continue                                  # not the same full list on every reference entity
            short = collections.Counter(k for x in o for k in universal - x.get(f, set()))
            n = sum(1 for x in o if universal - x.get(f, set()))
            print(f"  {f}: universal list of {len(universal)}; ours short on {n} entities; {short.most_common(5)}")


if __name__ == "__main__":
    main(sys.argv[1:])
