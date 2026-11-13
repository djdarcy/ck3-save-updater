"""MEASURE S5 (finding F20), step 2: what the game did with a removed and a scheduled event. Read-only.

For each character id given: `sexuality` in the input, in each control re-save and in the edited run's re-save
("none" = not assigned; no line = heterosexual, shown as "he"), and the child_personality events still queued for
that character in each save. Also the count of living characters whose sexuality differs between the edited run and
control A, as the background.

Run: python -I tests/one-offs/thinking/s5_compare.py <input> <control_a> <control_b> <edited run> <id> [<id> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import events as EV  # noqa: E402
from ck3_save_migrator import translate as T  # noqa: E402
from ck3_save_migrator.savefile import parse_header, parse_save  # noqa: E402

SEX = re.compile(rb"(?m)^\tsexuality=(\w+)")
DATE = re.compile(rb"(?m)^date=([\d.]+)")


def gamestate(path: Path) -> bytes:
    data = path.read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def sexuality(g: bytes) -> dict[int, str]:
    out = {}
    for i, e in T.entries(g, "living"):
        m = SEX.search(g[e.open:e.close])
        out[i] = m.group(1).decode() if m else "he"
    return out


names = ["input", "control A", "control B", "edited run"]
saves = [gamestate(Path(p)) for p in sys.argv[1:5]]
sex = [sexuality(g) for g in saves]
queued = [EV.queued_events(g) for g in saves]
for n, g, q in zip(names, saves, queued):
    print(f"{n:<11} date {DATE.search(g).group(1).decode():<10} living {len(T and dict(T.entries(g, 'living'))):>6} "
          f"queued events {len(q)}")
for cid in (int(x) for x in sys.argv[5:]):
    print(f"character {cid}:")
    for n, s, q in zip(names, sex, queued):
        mine = [f"{e.event}@{e.date}" for e in q if e.root == cid and e.event.startswith("child_personality.")]
        print(f"  {n:<11} sexuality={s.get(cid, '(gone)'):<6} child_personality queued: {mine or '-'}")
both = [i for i in sex[1] if i in sex[3]]
diff = [i for i in both if sex[1][i] != sex[3][i]]
ab = [i for i in sex[1] if i in sex[2] and sex[1][i] != sex[2][i]]
print(f"background: living in both control A and the edited run {len(both)}; sexuality differs for {len(diff)}; "
      f"control A against control B differs for {len(ab)}")
