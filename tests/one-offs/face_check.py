"""face_check: do the faces survive the game's own save? (R19's acceptance, plan step 2b)

For each save given: portraits_version, the length histogram of the characters' stored dna= (living, dead), the
number of living characters with a face, and the DNA of the named characters (Beidh 50822, Uilleam 28792 by
default) as a short hash. With two saves, says whether the named characters' DNA is identical, and how many
characters' DNA changed, appeared or disappeared from the first save to the second.

Usage: python -I tests/one-offs/face_check.py <before.ck3> [<after.ck3>] [--ids 50822,28792]
"""
from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
DNA1 = re.compile(rb'\n\tdna="([^"]*)"')


def load(path: str) -> bytes:
    """A normal save through read_save; a plain-text save (header kind 00, written under -debug_mode) by
    dropping its header line."""
    raw = Path(path).read_bytes()
    if raw[:3] == b"SAV" and raw[5:7] == b"00":
        return raw[raw.index(b"\n") + 1:]
    return sf.read_save(path).gamestate


def faces(path: str):
    g = load(path)
    pv = re.findall(rb"portraits_version=(\d+)", g[:20000])
    out, sec_of = {}, {}
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if e.key and e.key.isdigit():
                m = DNA1.search(g, e.start, e.end)
                sec_of[e.key.decode()] = sec
                if m:
                    out[e.key.decode()] = m.group(1)
    return pv, out, sec_of


def h(d: bytes | None) -> str:
    return "-" if d is None else f"{len(d)}ch {hashlib.sha256(d).hexdigest()[:12]}"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = (sys.argv[sys.argv.index("--ids") + 1].split(",") if "--ids" in sys.argv else ["50822", "28792"])
    data = []
    for p in args:
        pv, f, sec = faces(p)
        lens = Counter(len(v) for v in f.values())
        living = sum(1 for k in f if sec.get(k) == "living")
        print(f"== {Path(p).name}\n  portraits_version {[x.decode() for x in pv]}; characters with a face {len(f)} "
              f"(living {living}); lengths {dict(sorted(lens.items()))}")
        for i in ids:
            print(f"  {i}: {h(f.get(i))} ({sec.get(i, 'absent')})")
        data.append(f)
    if len(data) == 2:
        a, b = data
        same = sum(1 for k in a if k in b and a[k] == b[k])
        changed = sum(1 for k in a if k in b and a[k] != b[k])
        gone, new = len(set(a) - set(b)), len(set(b) - set(a))
        print(f"== before -> after: identical {same}, changed {changed}, face gone {gone}, face new {new}")
        for i in ids:
            print(f"  {i}: {'IDENTICAL' if a.get(i) is not None and a.get(i) == b.get(i) else 'DIFFERENT'}")


if __name__ == "__main__":
    main()
