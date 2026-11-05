"""Compare two game error.logs by family (the line with timestamps, numbers and quoted names folded), and print the
families that grew or shrank most. Usage: python -I error_family_diff.py <before error.log> <after error.log> [n]"""
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def families(p):
    c = Counter()
    for line in open(p, encoding="utf-8", errors="replace"):
        line = re.sub(r"^\[[^\]]*\]\[[^\]]*\]", "", line.strip())          # [time][file:line]
        line = re.sub(r"'[^']*'|\"[^\"]*\"", "'_'", line)
        line = re.sub(r"\d+(\.\d+)?", "N", line)
        c[line[:140]] += 1
    return c


a, b = families(sys.argv[1]), families(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
print(f"before {sum(a.values())} lines, {len(a)} families; after {sum(b.values())} lines, {len(b)} families")
delta = Counter({k: b[k] - a[k] for k in set(a) | set(b)})
print("-- grew most:")
for k, d in delta.most_common(n):
    if d > 0:
        print(f"  +{d:>6} ({a[k]} -> {b[k]})  {k}")
print("-- shrank most:")
for k, d in sorted(delta.items(), key=lambda x: x[1])[:n]:
    if d < 0:
        print(f"  {d:>7} ({a[k]} -> {b[k]})  {k}")
print("-- new families:", sum(1 for k in b if k not in a), " gone:", sum(1 for k in a if k not in b))
if len(sys.argv) > 4:                                  # new families matching a word
    for k in sorted(k for k in b if k not in a and re.search(sys.argv[4], k, re.I)):
        print(f"  new {b[k]:>5}  {k}")
