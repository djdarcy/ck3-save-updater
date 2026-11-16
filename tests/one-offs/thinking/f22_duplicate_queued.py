"""MEASURE (finding F22): where do the duplicate queued events of an updated save come from? Read-only.

On the updated campaign (play14), 1,631 groups of `triggered_event` blocks share their name, root and seed. Either
the 1.8.1 original already holds them (then they are the old game's), or the reference does (then the update carries
them in), or neither does and the update makes them (a fault in `update`).

For each save given: the number of queued blocks, the groups sharing (kind, name, root, seed), the extra blocks, and
how many groups also share the date. Then, for the LAST save against each earlier one: how many of its duplicate
groups exist as a duplicate group there, exist there once, or are not there at all.

PREDICTION, written before the run: the original already holds most of them (the game queues the same on_action
or event for a character more than once, e.g. a pulse per title or a re-queued personality event), so the update
only carries them. What would refute it: the original and the reference each hold few or none, and the output many.

Run: python -I tests/one-offs/thinking/f22_duplicate_queued.py <original.ck3> <reference.ck3> <updated.ck3>
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import events as EV  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402


def gamestate(path: Path) -> bytes:
    data = path.read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def groups(path: Path):
    ev = EV.queued_events(gamestate(path))
    by = Counter((e.kind, e.event, e.root, e.seed) for e in ev)
    dated = Counter((e.kind, e.event, e.root, e.seed, e.date) for e in ev)
    dup = {k: n for k, n in by.items() if n > 1}
    print(f"{path.name[:60]:<60} blocks {len(ev):>6}  duplicate groups {len(dup):>5}  extra blocks "
          f"{sum(n - 1 for n in dup.values()):>5}  groups sharing the date too "
          f"{sum(1 for n in dated.values() if n > 1):>4}")
    top = Counter(k[1] for k in dup).most_common(4)
    print(f"{'':<60} most duplicated: {top}")
    return by, dup


saves = [Path(p) for p in sys.argv[1:]]
found = [groups(p) for p in saves]
last_by, last_dup = found[-1]
for p, (by, dup) in zip(saves[:-1], found[:-1]):
    also_dup = sum(1 for k in last_dup if k in dup)
    once = sum(1 for k in last_dup if by.get(k, 0) == 1)
    absent = sum(1 for k in last_dup if k not in by)
    print(f"of the last save's {len(last_dup)} duplicate groups, in {p.name[:40]}: a duplicate there too {also_dup}; "
          f"there once {once}; not there {absent}")
