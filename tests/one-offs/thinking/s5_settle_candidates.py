"""MEASURE (carried-fields S5): settle the census candidates that remain -- titles without a capital, armies without a
commander, units without an army, schemes without a type -- by what the game itself writes. Read-only.

Witnesses: the update's output (0.5.22), the game's own re-save of an update's output (the game wrote it), and the
original 1.8.1 save (the game wrote it, before any update). A shape the game writes in its own save is the game's
own; a shape only in our output is ours.

KNOWN ANSWER: the game's re-save has titles without a capital (544, S3) -- the probe must find them there too.

Run: python -I tests/one-offs/thinking/s5_settle_candidates.py <update output> <game re-save> <original 1.8 save>
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator._vendor.savediff import text as T  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402


def gamestate(path: str) -> bytes:
    data = Path(path).read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def entries(g: bytes, ix, path: str):
    b = T.locate(ix, path)
    return [] if b is None else [e for e in T.iter_entries(g, *b.body) if e.key is None or e.key.isdigit()]


def keys_of(g: bytes, e) -> dict:
    try:
        return {c.key: c for c in T.iter_children(g, *e.body) if c.key}
    except T.SaveTextError:
        return {}


def report(name: str, path: str) -> None:
    g = gamestate(path)
    ix = T.SectionIndex(g)
    print(f"== {name}")
    # titles without a capital: by rank prefix, with or without de jure land and a holder
    nocap = Counter()
    examples = []
    for e in entries(g, ix, "landed_titles/landed_titles"):
        k = keys_of(g, e)
        if b"capital" in k:
            continue
        key = g[k[b"key"].value_start:k[b"key"].value_end].strip(b'"') if b"key" in k else b"?"
        rank = key.split(b"_")[0].decode()
        land = "de jure land" if (b"de_jure_vassals" in k or rank in ("c", "b")) else "no de jure land"
        held = "held" if b"holder" in k else "unheld"
        nocap[(rank, land, held)] += 1
        if len(examples) < 6:
            examples.append(key.decode())
    print(f"  titles without a capital: {sum(nocap.values())}")
    for (rank, land, held), n in sorted(nocap.items(), key=lambda x: -x[1]):
        print(f"    {rank:<3} {land:<16} {held:<7} {n}")
    print(f"    e.g. {examples}")
    # armies without a commander; units without an army
    arm = entries(g, ix, "armies/armies")
    noc = [e.key.decode() for e in arm if b"commander" not in keys_of(g, e)]
    print(f"  armies: {len(arm)}, without a commander: {len(noc)} {noc[:6]}")
    units = entries(g, ix, "units")
    noa = [e.key.decode() for e in units if b"army" not in keys_of(g, e)]
    print(f"  units: {len(units)}, without an army: {len(noa)} {noa[:6]}")
    # schemes without a type: what they hold instead
    sch = entries(g, ix, "schemes/active")
    notype = [e for e in sch if b"type" not in keys_of(g, e)]
    shapes = Counter(tuple(sorted(x.decode() for x in keys_of(g, e))) for e in notype)
    print(f"  schemes: {len(sch)}, without a type: {len(notype)}; their field sets: {shapes.most_common(3)}")


for label, p in zip(("update output (0.5.22)", "the game's re-save of an update's output", "original 1.8.1 save"),
                    sys.argv[1:4]):
    report(label, p)
