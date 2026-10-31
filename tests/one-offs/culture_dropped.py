"""culture_dropped: which characters lose `culture=` when the game loads play7 and saves it, and why? (2026-10-31, U-b / F12)

The C2 diff (play7 vs the game's re-save, nothing played): `culture` dropped from 17 living and 3 dead_unprunable
characters. Predictions, written before running: (a) their culture ids do not exist in play7's culture_manager, or
(b) name cultures the re-save marks `invalid`; (c) otherwise the engine drops a culture that repeats an inherited
default.

For each such character: section, id, culture id, whether that id exists in play7's and the re-save's cultures, the
culture's template (name), its `invalid=` value in the re-save, the character's house, and the character's other
fields beside culture in play7 (the first lines), to see whether they are carried (1.8.1) or transplanted.

Usage: python -I tests/one-offs/culture_dropped.py <play7.ck3> <resave.ck3>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

CULT = re.compile(rb"\n\tculture=(\d+)")
SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")


def cultures(g: bytes) -> dict[int, bytes]:
    return {i: g[e.open:e.close] for i, e in T.entries(g, "culture_manager/cultures")}


def field(body: bytes, key: bytes) -> str | None:
    m = re.search(rb"\n\t+" + key + rb'="?([^"\s}]+)"?', body)
    return m.group(1).decode() if m else None


def main() -> None:
    a, b = read_save(sys.argv[1]).gamestate, read_save(sys.argv[2]).gamestate
    ca, cb = cultures(a), cultures(b)
    print(f"cultures: play7 {len(ca)}, re-save {len(cb)}; marked invalid=yes in the re-save: "
          f"{sum(1 for v in cb.values() if field(v, b'invalid') == 'yes')}")
    for path in SECTIONS:
        ea = {i: a[e.open:e.close] for i, e in T.entries(a, path)}
        eb = {i: b[e.open:e.close] for i, e in T.entries(b, path)}
        lost = [i for i, body in ea.items() if CULT.search(body) and i in eb and not CULT.search(eb[i])]
        print(f"\n{path}: {len(lost)} characters lose culture=")
        for i in lost:
            c = int(CULT.search(ea[i]).group(1))
            tmpl = field(ca.get(c, b""), b"culture_template")
            print(f"  {i}: culture {c} ({tmpl}); in play7 cultures {c in ca}, in re-save {c in cb}, "
                  f"invalid in re-save {field(cb.get(c, b''), b'invalid')}; house {field(ea[i], b'dynasty_house')}; "
                  f"name {field(ea[i], b'first_name')}; birth {field(ea[i], b'birth')}")


if __name__ == "__main__":
    main()
