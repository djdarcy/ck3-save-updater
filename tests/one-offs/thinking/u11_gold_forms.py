"""MEASURE (U11, static): how a save stores a character's gold, and whether the game keeps the old form.

Found while checking the declarative set-gold edit on play14: an updated save holds gold in two layouts, the 1.8
scalar ``alive_data={ gold=18.9375 }`` on carried characters and the 1.20 block ``alive_data={ gold={ value=100 } }``
on characters from the reference. This counts both forms in <save>, and, given the game's own re-save of it,
says how many scalar-form characters still hold gold there and whether the amount is the same.

Reads kind 02 saves (the tool's reader) and kind 00 ones (plain text, what a console ``save`` writes in debug mode:
the gamestate follows the header line). Read-only.

Run: python -I tests/one-offs/thinking/u11_gold_forms.py <save.ck3> [<the game's re-save of it>]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402

SCALAR = re.compile(rb"(?m)^\t\tgold=([0-9.-]+)")
BLOCK = re.compile(rb"(?m)^\t\tgold=\{\s*value=([0-9.-]+)")


def gamestate(path: Path) -> bytes:
    data = path.read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def gold(g: bytes) -> dict[int, tuple[str, float]]:
    out = {}
    for i, e in T.entries(g, "living"):
        body = g[e.open:e.close]
        m, kind = SCALAR.search(body), "scalar"
        if not m:
            m, kind = BLOCK.search(body), "block"
        if m:
            out[i] = (kind, float(m.group(1)))
    return out


a = gold(gamestate(Path(sys.argv[1])))
print(f"{Path(sys.argv[1]).name}: {dict(Counter(k for k, _ in a.values()))}")
if len(sys.argv) > 2:
    gb = gamestate(Path(sys.argv[2]))
    b = gold(gb)
    living = {i for i, _ in T.entries(gb, "living")}
    print(f"{Path(sys.argv[2]).name}: {dict(Counter(k for k, _ in b.values()))}")
    scalar = [i for i, (k, _) in a.items() if k == "scalar"]
    alive = [i for i in scalar if i in living]
    kept = [i for i in alive if i in b]
    same = [i for i in kept if abs(b[i][1] - a[i][1]) < 0.01]
    print(f"scalar-form characters: {len(scalar)}; still living in the re-save: {len(alive)}; "
          f"hold gold there: {len(kept)}; the same amount: {len(same)}")
    rich = sorted(scalar, key=lambda i: -a[i][1])[:5]
    print("richest five (id, before, after):", [(i, a[i][1], b.get(i)) for i in rich])
    lost = [i for i in alive if i not in b][:5]
    print("first five living without gold after:", [(i, a[i][1]) for i in lost])
