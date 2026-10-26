"""Print one entry of a save's database (first N bytes). Usage: python -I show_entry.py <save.ck3> <path> <id> [n]"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs, savefile as sf  # noqa: E402

g = sf.read_save(sys.argv[1]).gamestate
b = gs.locate(g, sys.argv[2])
m = re.search(rb"\n\t*" + sys.argv[3].encode() + rb"=\{", g[b.open:b.close])
if not m:
    print("absent")
    sys.exit()
s = b.open + m.start() + 1
e = gs.match_brace(g, b.open + m.end() - 1)
n = int(sys.argv[4]) if len(sys.argv) > 4 else 2500
print(g[s:min(e + 1, s + n)].decode("utf-8", "replace"))
