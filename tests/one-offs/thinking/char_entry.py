"""Print one character's entry from a save's living / dead_unprunable section. Usage: char_entry.py <save> <id> [...]"""
import re, sys
sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs
try:
    d = sf.read_save(sys.argv[1]).gamestate
except sf.UnsupportedKindError:          # a plain-text save (kind 00): drop the header line
    raw = open(sys.argv[1], "rb").read()
    d = raw[raw.index(b"\n") + 1:]
for cid in sys.argv[2:]:
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        m = re.compile(rb"\n" + cid.encode() + rb"=\{").search(d, b.start, b.end)
        if m:
            e = d.find(b"\n}", m.end())
            print(f"== {cid} in {sec}\n" + d[m.start() + 1:e + 2].decode("utf-8", "replace"))
            break
