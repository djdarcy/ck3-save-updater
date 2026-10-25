"""Compare the error families of two CK3 error.log files (a baseline run and a test run).

A family is an error line with its timestamp dropped and every number, quoted string and hex value replaced by a
placeholder, so "Unexpected token: foo" and "Unexpected token: bar" stay separate only by the token's place in
the message, not its value. Prints families that are new in the test run, gone from it, and those whose count
changed by more than 5%.

Usage: python -I tests/one-offs/errorlog_families.py <baseline error.log> <test error.log> [--until HH:MM:SS]
"""
import re
import sys
from collections import Counter
from pathlib import Path

STAMP = re.compile(r"^\[\d\d:\d\d:\d\d\]")
NUM = re.compile(r"\b0x[0-9a-fA-F]+\b|-?\d+(?:\.\d+)?")
QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
WORD_AFTER = re.compile(r"(Unexpected token: |key reference |on action |template |culture )[\w.:\-]+")


def families(path: Path, until: str | None = None) -> Counter:
    """``until`` (HH:MM:SS) keeps only lines stamped at or before it: a load compared with a load, before the
    test run was unpaused and gameplay began logging."""
    c = Counter()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not STAMP.match(line):
            continue
        if until and line[1:9] > until:
            break
        s = STAMP.sub("", line)
        s = re.sub(r"\[[\w./\\]+\.cpp:\d+\]", "[src]", s)
        s = QUOTED.sub("'X'", s)
        s = WORD_AFTER.sub(lambda m: m.group(1) + "W", s)
        s = NUM.sub("N", s)
        c[s.strip()[:160]] += 1
    return c


def main():
    until = sys.argv[sys.argv.index("--until") + 1] if "--until" in sys.argv else None
    a, b = families(Path(sys.argv[1])), families(Path(sys.argv[2]), until)
    print(f"baseline {sum(a.values()):,} lines in {len(a)} families; test {sum(b.values()):,} lines in {len(b)} families")
    new = [(k, n) for k, n in b.items() if k not in a]
    gone = [(k, n) for k, n in a.items() if k not in b]
    changed = [(k, a[k], b[k]) for k in a.keys() & b.keys() if abs(b[k] - a[k]) > max(2, a[k] * 0.05)]
    print(f"\nNEW in test ({len(new)}):")
    for k, n in sorted(new, key=lambda x: -x[1])[:30]:
        print(f"  {n:>6}  {k}")
    print(f"\ngone from test ({len(gone)}):")
    for k, n in sorted(gone, key=lambda x: -x[1])[:15]:
        print(f"  {n:>6}  {k}")
    print(f"\ncount changed > 5% ({len(changed)}):")
    for k, x, y in sorted(changed, key=lambda x: -abs(x[2] - x[1]))[:20]:
        print(f"  {x:>6} -> {y:<6} {k}")


if __name__ == "__main__":
    main()
