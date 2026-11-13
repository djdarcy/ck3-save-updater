"""MEASURE S5 (event-remove, event-schedule), step 0: pick the subjects, read-only.

The game check for the two event edits that were never loaded: a save with one queued event REMOVED, and one with
an event SCHEDULED by hand. The event used is child_personality.4015 (game/events/education_and_childhood/
child_personality_events.txt:9130): its trigger is `has_sexuality = none` and it sets the child heterosexual, so its
effect is one field, `sexuality=`, on its root.

This lists, from <input> and the two control re-saves of F16 (the game's own saves of <input>, about ten months
later, nothing edited):
  REMOVE candidates: a queued child_personality.4012-4015 in <input>, dated inside the controls' window, whose root
    has no sexuality in <input> and HAS one in both controls. Removing it should leave the root without one.
  SCHEDULE candidates: living children with no sexuality in <input> and none in both controls, and no queued
    child_personality event. Scheduling 4015 for one should give that child a sexuality.

Reads kind 02 saves and kind 00 ones (a console save in debug mode). Run:
  python -I tests/one-offs/thinking/s5_pick_subjects.py <input.ck3> <control_a.ck3> <control_b.ck3>
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
BIRTH = re.compile(rb"(?m)^\tbirth=(\d+)\.")
DATE = re.compile(rb"(?m)^date=(\d+)\.(\d+)\.(\d+)")


def gamestate(path: Path) -> bytes:
    data = path.read_bytes()
    h = parse_header(data[:64])
    return data[len(h.raw):] if h.kind == 0 else parse_save(data).gamestate


def sexuality(g: bytes) -> dict[int, str]:
    """Each living character's sexuality as the save writes it: "none" is not assigned yet; heterosexual is the
    default and is not written, so absence reads as "he" here (measured: 6,675 none, 4,063 bi, 3,935 ho, 808 as,
    and no line at all for the other 29,072 of play14's 44,553 living)."""
    out = {}
    for i, e in T.entries(g, "living"):
        m = SEX.search(g[e.open:e.close])
        out[i] = m.group(1).decode() if m else "he"
    return out


g = gamestate(Path(sys.argv[1]))
a, b = gamestate(Path(sys.argv[2])), gamestate(Path(sys.argv[3]))
s0, sa, sb = sexuality(g), sexuality(a), sexuality(b)
window = min(tuple(int(x) for x in DATE.search(x).groups()) for x in (a, b))
year = int(DATE.search(g).group(1))
print(f"input date {DATE.search(g).group(0).decode()}; controls reach {window}; living {len(s0)}")
events = EV.queued_events(g)
queued_child = {e.root for e in events if e.event.startswith("child_personality.")}

print("REMOVE candidates (event number, event, date, root, control A, control B):")
n = 0
for e in events:
    if e.event in ("child_personality.4012", "child_personality.4013", "child_personality.4014",
                   "child_personality.4015") and EV.date_key(e.date) < window and e.root in s0:
        if s0[e.root] == "none" and sa.get(e.root, "none") != "none" and sb.get(e.root, "none") != "none":
            only = sum(1 for x in events if x.root == e.root and x.event.startswith("child_personality."))
            print(f"  #{e.number} {e.event} {e.date} root {e.root}  A={sa[e.root]} B={sb[e.root]}  "
                  f"(child_personality events queued for this root: {only})")
            n += 1
            if n >= 8:
                break
print("SCHEDULE candidates (id, age, in A, in B):")
n = 0
for i, e in T.entries(g, "living"):
    m = BIRTH.search(g[e.open:e.close])
    age = year - int(m.group(1)) if m else None
    if age is not None and 4 <= age <= 9 and s0[i] == "none" and sa.get(i) == "none" and sb.get(i) == "none" \
            and i not in queued_child:
        print(f"  {i} age {age}  A={sa[i]!r} B={sb[i]!r}")
        n += 1
        if n >= 8:
            break
