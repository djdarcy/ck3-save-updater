"""dna_to_vanilla: make a vanilla-layout 1.8.1 save for Q8 by translating every dna= into vanilla 1.8.2's layout.
(2026-10-31, the director's Q8 prep for the "A-lite plus the vanilla path" option)

No save in the campaign's lineage or the fixtures has vanilla-layout DNA at 1.8.x: the originals are 700/712
characters (CFP + EPE), and the mods-off ladder saves (1.8.1 saved by 1.14.3 / 1.16.2 / 1.18.4) keep DNA on only
99 characters, all 556 (the engine dropped the rest). So one is made: each 712/700-character string is read as
layout (a) (1.8.2 + the 2023 CFP and EPE, its 130 places) and translated BY GENE NAME into vanilla 1.8.2
(104 genes, 556 characters), as dna_translate.py does: 100 genes kept, 26 EPE genes dropped (the 2026-10-25 decode
note). The result stands in for a stranger's vanilla 1.8.1 save. Nothing else is changed (portraits_version stays as
read; migrate's --portraits-version 5 sets it).

The vanilla path's premise (decode note): vanilla 1.8.2 and vanilla 1.20 have "the same 104 genes in the same places",
556 characters both sides, so the 1.20 game reads these strings as they are.

Usage: python -I tests/one-offs/dna_to_vanilla.py <in 1.8.1.ck3> <out.ck3>
"""
from __future__ import annotations

import base64
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_layout as D  # noqa: E402
import dna_translate as X  # noqa: E402
from dna_whole_save import LAYOUT_A, PROJECT  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

LAYOUT_V182 = [("vanilla", PROJECT / "private" / "data" / "versions" / "1.8.2" / "game")]
DNA = re.compile(rb'dna="([^"]*)"')


def b64d(s: bytes) -> bytes:
    return base64.b64decode(s + b"=" * (-len(s) % 4))


def main() -> None:
    src_p, out_p = sys.argv[1:3]
    a = D.dna_order(D.load_layout(LAYOUT_A))
    v = D.dna_order(D.load_layout(LAYOUT_V182))
    plan = X.build(a, v)
    chars = lambda n: len(base64.b64encode(bytes(n)))     # noqa: E731
    target = chars(4 * len(v))
    readable = {chars(532), chars(524)}                     # 712 (1.8.1) and 700 (1.5.1.1), read as layout (a)
    print(f"layout (a) {len(a)} genes -> vanilla 1.8.2 {len(v)} genes ({target} characters); "
          f"kept {plan.kept}, remapped {plan.remapped}, dropped {plan.dropped}, defaulted {plan.defaulted}")
    save = sf.read_save(src_p)
    g = save.gamestate
    tally, parts, pos = Counter(), [], 0
    for m in DNA.finditer(g):
        s = m.group(1)
        if len(s) == target:
            tally["already vanilla length"] += 1
            continue
        if len(s) not in readable:
            tally[f"left: length {len(s)}"] += 1
            continue
        new = base64.b64encode(plan.apply(b64d(s)[:4 * len(a)]))
        parts += [g[pos:m.start(1)], new]
        pos = m.end(1)
        tally["translated"] += 1
    parts.append(g[pos:])
    save.set_gamestate(b"".join(parts))
    res = sf.write_save(save, out_p)
    after = Counter(len(m.group(1)) for m in DNA.finditer(save.gamestate))
    print(dict(tally), "lengths after:", dict(after))
    print(f"wrote {out_p} ({res.size:,} bytes)")


if __name__ == "__main__":
    main()
