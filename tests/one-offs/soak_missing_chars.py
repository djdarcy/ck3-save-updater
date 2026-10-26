"""Which characters do a soak's "(no character) weak (Character - N)" errors name, and what are they in the save?

For the most frequent ids: the count, and in the save the section the id sits in (living / dead_unprunable /
characters/dead_prunable / absent), and whether any title, company or court names it.
Usage: python -I tests/one-offs/soak_missing_chars.py <run-folder> <save.ck3> [top]
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs, savefile as sf  # noqa: E402

log = (Path(sys.argv[1]) / "logs" / "error.log").read_text(encoding="utf-8", errors="replace")
top = int(sys.argv[3]) if len(sys.argv) > 3 else 15
ids = Counter(int(m) for m in re.findall(r"\(no character\) weak \(Character - (\d+)", log))
print("distinct ids", len(ids), "errors", sum(ids.values()))
g = sf.read_save(sys.argv[2]).gamestate
blocks = {}
for name in ("living", "dead_unprunable", "characters/dead_prunable"):
    try:
        blocks[name] = gs.locate(g, name)
    except Exception:  # noqa: BLE001
        pass
for i, n in ids.most_common(top):
    where = [k for k, b in blocks.items() if re.search(rb"\n\t*" + str(i).encode() + rb"=\{", g[b.open:b.close])]
    refs = len(re.findall(rb"(?<![\d.])" + str(i).encode() + rb"(?![\d.])", g))
    print(f"{i:>10} x{n:<6} in {where or 'ABSENT'}  occurrences in save {refs}")
