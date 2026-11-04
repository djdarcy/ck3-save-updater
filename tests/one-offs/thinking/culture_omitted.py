"""Does the game write characters without `culture=` on its own? In a save, count living / dead_unprunable characters
with and without a culture line, split by whether they have a dynasty_house, an employer, and family_data.
Usage: culture_omitted.py <save> [...]"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

ENTRY = re.compile(rb"(?m)^(\d+)=\{\n")
for path in sys.argv[1:]:
    try:
        d = sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        d = raw[raw.index(b"\n") + 1:]
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        n = Counter()
        for m in ENTRY.finditer(d, b.start, b.end):
            body = d[m.end():d.find(b"\n}", m.end())]
            has = re.search(rb"(?m)^\tculture=", body) is not None
            house = b"\tdynasty_house=" in body
            court = b"\temployer=" in body or b"\thost=" in body
            n[("culture" if has else "NO culture", "house" if house else "no house",
               "court" if court else "no court")] += 1
        print(f"== {path.split(chr(92))[-1].split('/')[-1]} {sec}")
        for k, v in sorted(n.items()):
            print(f"   {v:7,}  {' / '.join(k)}")
