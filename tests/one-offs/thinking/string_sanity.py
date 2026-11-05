"""S5 (djdarcy 2026-11-04: "perhaps we should look at character 50822 and the other characters ... to see if one of
their strings isn't null terminated properly"): scan a save's quoted strings for anything a parser could mis-size --
a quote left open to the end of the line, control characters, invalid UTF-8, extreme lengths -- over the named
characters' entries and over the whole gamestate.
Usage: python -I string_sanity.py <save> [character id ...]"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = sf.read_save(sys.argv[1]).gamestate
QUOTED = re.compile(rb'"((?:[^"\\\n]|\\.)*)"')


def check(lo, hi, label, show=5):
    bad = Counter()
    examples = []
    for ln_start in [m.start() for m in re.finditer(rb"(?m)^", d[lo:hi])][:None]:
        pass
    seg = d[lo:hi]
    for line in seg.split(b"\n"):
        if line.count(b'"') % 2:
            bad["odd quotes on a line"] += 1
            examples.append(line[:120])
        for m in QUOTED.finditer(line):
            s = m.group(1)
            if re.search(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", s):
                bad["control character"] += 1
                examples.append(s[:120])
            try:
                s.decode("utf-8")
            except UnicodeDecodeError:
                bad["invalid UTF-8"] += 1
                examples.append(s[:120])
            if len(s) > 2000:
                bad["longer than 2000 bytes"] += 1
                examples.append(s[:60] + b"...")
    print(f"{label}: {dict(bad) or 'clean'}")
    for e in examples[:show]:
        print("   ", e)


for cid in sys.argv[2:]:
    found = False
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        m = re.compile(rb"\n" + cid.encode() + rb"=\{").search(d, b.start, b.end)
        if m:
            check(m.start(), gs.match_brace(d, m.end() - 1) + 1, f"character {cid} ({sec})")
            found = True
            break
    if not found:
        print(f"character {cid}: not in living or dead_unprunable")
check(0, len(d), "whole gamestate", show=10)
