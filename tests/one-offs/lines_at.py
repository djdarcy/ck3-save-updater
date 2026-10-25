"""Classify the gamestate lines an error.log points at ("near line: N"), for one error pattern.

Usage: python tests/one-offs/lines_at.py <save.ck3> <error.log> "<regex on the error line>" [context]
Inflates the save in memory, collects every "near line: N" from matching error lines,
and prints: a histogram of the key on each line (+ its value shape), and the first few
lines with `context` lines around them (default 4). Read-only.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

save, log, pattern = sys.argv[1], sys.argv[2], re.compile(sys.argv[3])
ctx = int(sys.argv[4]) if len(sys.argv) > 4 else 4
data = sf.read_save(save).gamestate
nums = sorted({int(m.group(1)) for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines()
               if pattern.search(line) for m in [re.search(r"near line: (\d+)", line)] if m})
print(f"{len(nums)} distinct lines")
lines = data.split(b"\n")                       # line N is lines[N-1]
keys = Counter()
parents = Counter()
for n in nums:
    text = lines[n - 1].strip()
    m = re.match(rb'([^=\s]*)=(.*)', text)
    keys[(m.group(1).decode(errors="replace"), m.group(2)[:20].decode(errors="replace")) if m else ("?", text[:30].decode(errors="replace"))] += 1
offsets = []
pos = 0
want = set(nums)
for i, l in enumerate(lines, 1):
    if i in want:
        offsets.append(pos + len(l) - len(l.lstrip()))
    pos += len(l) + 1
for parent, child in gs.child_at(data, offsets).values():
    parents[(parent.key or b"{}").decode(errors="replace")] += 1
print("key / value on the line:")
for k, c in keys.most_common(15):
    print(f"  {c:>6}  {k}")
print("parent block:", dict(parents.most_common(10)))
for n in nums[:3]:
    print(f"--- line {n}")
    for i in range(max(1, n - ctx), n + ctx + 1):
        print(f"{'>>' if i == n else '  '}{i:>9}: {lines[i - 1].decode(errors='replace')[:160]}")
