"""realm_consistency: do a save's titles, domains, vassal contracts and lieges agree with each other?

2026-10-27: play5 (R15's held titles handed back to their campaign holders) crashes at 989.1.1 inside a script
effect that appends an id to a list on an object (ck3+0xb064e8); play5a, the same build without the hand-back, runs
to 994. The hand-back moves titles between characters and re-points de facto lieges, so this probe checks the
bookkeeping those moves must keep consistent, and prints each finding class with counts and examples so two saves
can be compared:

  A  a title's holder lists it in his domain
  B  a domain entry's title names that character as holder
  C  a ruler whose primary has a de facto liege has an active contract with that liege's holder
  D  a de facto liege title is held
  E  an active contract's liege lists it in his vassal_contracts, and its vassal's primary points at him
  F  a ruler's realm_capital is a barony or county he holds
  G  no character is his own liege; no one is a vassal of a landless or dead character

Usage: python -I tests/one-offs/realm_consistency.py <save.ck3> [<save.ck3> ...]
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402
from ck3_save_migrator.lint import SectionIndex, _ENTRY_COL0, _T_FIELD  # noqa: E402

_LIST = lambda k: re.compile(rb"\n\t\t" + k + rb"=\{([^}]*)\}")  # noqa: E731
DOMAIN, VCS = _LIST(b"domain"), _LIST(b"vassal_contracts")
CAPITAL = re.compile(rb"\n\t\trealm_capital=(\d+)")


def bodies(g: bytes, block) -> dict[bytes, bytes]:
    out = {}
    for m in _ENTRY_COL0.finditer(g, block.open, block.close):
        end = g.find(b"\n}", m.end(), block.close)
        out[m.group(1)] = g[m.end():end if end > 0 else block.close]
    return out


def probe(path: str) -> dict[str, list[str]]:
    g = sf.read_save(path).gamestate
    idx = SectionIndex(g)
    titles = {}
    for i, b in bodies(g, idx.block("landed_titles/landed_titles")).items():
        f = {k: (m.group(1) if (m := _T_FIELD[k].search(b[:4096])) else None)
             for k in (b"key", b"holder", b"de_facto_liege")}
        titles[i] = f
    key = lambda t: (titles.get(t, {}).get(b"key") or t).decode()   # noqa: E731
    living = bodies(g, idx.block("living"))
    dom = {c: (m.group(1).split() if (m := DOMAIN.search(b)) else []) for c, b in living.items()}
    vcs = {c: (m.group(1).split() if (m := VCS.search(b)) else []) for c, b in living.items()}
    cap = {c: m.group(1) for c, b in living.items() if (m := CAPITAL.search(b))}
    contracts = {}
    for sec in ("vassal_contracts/active", "vassal_contracts/database"):      # 1.20 itself writes database
        act = idx.block(sec)
        for e in gs.iter_entries(g, *act.body) if act is not None else []:
            if e.key and e.key.isdigit():
                body = g[e.open:e.close]
                v, lg = re.search(rb"[\n\t ]vassal=(\d+)", body), re.search(rb"[\n\t ]liege=(\d+)", body)
                contracts.setdefault(e.key, (v.group(1) if v else None, lg.group(1) if lg else None))
    by_vassal = defaultdict(list)
    for cid, (v, lg) in contracts.items():
        by_vassal[v].append((cid, lg))
    f = defaultdict(list)
    for t, x in titles.items():
        h = x[b"holder"]
        if h is not None and h in living and t not in dom[h]:
            f["A holder does not list the title in his domain"].append(f"{key(t)} holder {h.decode()}")
        lg = x[b"de_facto_liege"]
        if lg is not None and lg in titles and titles[lg][b"holder"] is None:
            f["D de facto liege title is unheld"].append(f"{key(t)} -> {key(lg)}")
    for c, ts in dom.items():
        for t in ts:
            h = titles.get(t, {}).get(b"holder")
            if h != c:
                f["B domain entry names another holder"].append(
                    f"{c.decode()} lists {key(t)}, holder {h.decode() if h else None}")
        if not ts:
            if by_vassal.get(c):
                f["G landless character is a vassal in an active contract"].append(c.decode())
            continue
        lg = titles.get(ts[0], {}).get(b"de_facto_liege")
        lh = titles.get(lg, {}).get(b"holder") if lg else None
        if lh == c:
            f["G ruler's primary has his own title as liege"].append(f"{c.decode()} {key(ts[0])} -> {key(lg)}")
        elif lh is not None:
            if lh not in living:
                f["G liege holder is not living"].append(f"{c.decode()} -> {lh.decode()}")
            if not any(l2 == lh for _, l2 in by_vassal.get(c, [])):
                f["C ruler has no active contract with his liege"].append(
                    f"{c.decode()} ({key(ts[0])}) liege {lh.decode()} ({key(lg)}); contracts "
                    f"{[(k.decode(), (l2 or b'-').decode()) for k, l2 in by_vassal.get(c, [])]}")
        elif by_vassal.get(c):
            f["C independent ruler still has an active contract"].append(
                f"{c.decode()} ({key(ts[0])}): {[(k.decode(), (l2 or b'-').decode()) for k, l2 in by_vassal[c]]}")
        if c in cap and cap[c] not in ts:
            f["F realm_capital not in his domain"].append(f"{c.decode()} capital {key(cap[c])}")
    for cid, (v, lg) in contracts.items():
        if lg is not None and lg in living and cid not in vcs[lg]:
            f["E liege does not list the contract"].append(f"{cid.decode()} liege {lg.decode()} vassal "
                                                           f"{(v or b'-').decode()}")
    for c, ids in vcs.items():
        for cid in ids:
            v, lg = contracts.get(cid, (None, None))
            if lg != c:
                f["E listed contract names another liege"].append(f"{c.decode()} lists {cid.decode()} "
                                                                   f"(liege {(lg or b'-').decode()})")
    return f


def main():
    for p in sys.argv[1:]:
        f = probe(p)
        print(f"== {p}")
        for k in sorted(f):
            print(f"  {len(f[k]):6,}  {k}")
            for x in f[k][:4]:
                print(f"            {x}")
        if not f:
            print("  consistent")


if __name__ == "__main__":
    main()
