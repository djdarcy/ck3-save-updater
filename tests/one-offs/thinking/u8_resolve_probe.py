"""MEASURE (U8): the character resolver on a real save, read-only.

Known answers (finding 2026-11-09__01-52-22, on play14 / the v12 golden): "Conchenn" matches 30 living characters;
78307 is Conchenn, female, born 980.8.16, father 64975 Bruide, mother 65171 E_lfweard. Prediction: "Conchenn" is
refused listing 30; "78307" and "Conchenn nic Bruide" each resolve to 78307.

Run: python -I tests/one-offs/thinking/u8_resolve_probe.py <save.ck3> ["query" ...]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator.characters import CharacterError, CharacterIndex, resolve_character  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

save = Path(sys.argv[1])
queries = sys.argv[2:] or ["Conchenn", "78307", "Conchenn nic Bruide"]
t0 = time.perf_counter()
g = read_save(save).gamestate
print(f"read {time.perf_counter() - t0:.1f}s")
ix = CharacterIndex(g)
for q in queries:
    t0 = time.perf_counter()
    try:
        c = resolve_character(g, q, ix)
        print(f"{q!r} -> {ix.describe(c)}")
    except CharacterError as exc:
        text = str(exc)
        print(f"{q!r} refused: {text.splitlines()[0]}")
        for line in text.splitlines()[1:4]:
            print("   " + line)
    print(f"   ({time.perf_counter() - t0:.1f}s)")
