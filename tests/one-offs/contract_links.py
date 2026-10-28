"""contract_links: are a save's vassal contracts reachable the way the game reaches them? (crash on exit, 2026-10-28)

The crash on Exit to Desktop is in CSubjectContract's destructor (ck3+0x24ca0bb), which reads a character already
freed. Ruled out by exit tests on the game's own reference save: a missing contract_group, and 1.8's whole layout
(`active`, no liege_dynasty_date). Left: which contracts the save holds. A liege lists its vassals' contracts
(`vassal_contracts={ ids }` in its landed data); a contract no liege lists, or one listed by a character who is not
its liege, is a candidate for being left to the final teardown, after the characters.

For each contract in vassal_contracts (`active` or `database`):
  orphan        no living character lists it
  wrong_lister  listed, but by a character other than its `liege`
  multi_listed  listed by more than one character
  dup_vassal    its vassal has another contract too
  vassal_dead / liege_dead / vassal_missing / liege_missing   by the living and dead sections
and list ids no contract has (dangling). Known answer: the game's own save should show 0 orphans and 0 wrong.

Usage: python -I tests/one-offs/contract_links.py <save.ck3> [<save.ck3> ...] [--examples N]
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

LIST = re.compile(rb"\bvassal_contracts=\{([^{}]*)\}")
FIELD = re.compile(rb"(?m)^\s*(vassal|liege)=(\d+)")


def load(p):
    try:
        return sf.read_save(p).gamestate
    except Exception:                       # a plain-text save (the crash reporter's copy): drop the header line
        raw = Path(p).read_bytes()
        return raw[raw.index(b"\n") + 1:]


def ids_in(d, path):
    try:
        sec = gs.locate(d, path)
    except gs.GamestateError:
        return set()
    return {int(e.key) for e in gs.iter_entries(d, *sec.body) if e.key and e.key.isdigit()}


def census(p, examples=5):
    d = load(p)
    vc = gs.find_section(d, "vassal_contracts")
    contracts = {}
    for sub in gs.iter_children(d, *vc.body):
        if sub.block is None:
            continue
        for e in gs.iter_entries(d, *sub.block.body):
            if e.key and e.key.isdigit():
                f = {k.decode(): int(v) for k, v in FIELD.findall(d[e.open:e.close])}
                contracts[int(e.key)] = f
    living = gs.locate(d, "living")
    listers = defaultdict(list)
    for e in gs.iter_entries(d, *living.body):
        if not (e.key and e.key.isdigit()):
            continue
        for m in LIST.finditer(d, e.open, e.close):
            for cid in m.group(1).split():
                listers[int(cid)].append(int(e.key))
    alive = {int(e.key) for e in gs.iter_entries(d, *living.body) if e.key and e.key.isdigit()}
    dead = ids_in(d, "dead_unprunable") | ids_in(d, "characters/dead_prunable")
    by_vassal = Counter(c.get("vassal") for c in contracts.values())
    flags = defaultdict(list)
    for cid, c in contracts.items():
        ls = listers.get(cid, [])
        if not ls:
            flags["orphan"].append(cid)
        elif c.get("liege") not in ls:
            flags["wrong_lister"].append(cid)
        if len(ls) > 1:
            flags["multi_listed"].append(cid)
        if by_vassal[c.get("vassal")] > 1:
            flags["dup_vassal"].append(cid)
        for role in ("vassal", "liege"):
            who = c.get(role)
            if who in dead:
                flags[f"{role}_dead"].append(cid)
            elif who not in alive:
                flags[f"{role}_missing"].append(cid)
    dangling = sorted(set(listers) - set(contracts))
    print(f"\n{p}\n  contracts {len(contracts)}, listed ids {len(listers)}, dangling list ids {len(dangling)} {dangling[:examples]}")
    for k in ("orphan", "wrong_lister", "multi_listed", "dup_vassal", "vassal_dead", "vassal_missing",
              "liege_dead", "liege_missing"):
        v = flags.get(k, [])
        ex = [(cid, contracts[cid].get("vassal"), contracts[cid].get("liege"), listers.get(cid)) for cid in v[:examples]]
        print(f"  {k:14} {len(v):6}  e.g. (id, vassal, liege, listed by) {ex}")
    return contracts, listers, flags


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = next((int(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--examples=")), 5)
    for p in args:
        census(p, n)


if __name__ == "__main__":
    main()
