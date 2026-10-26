"""Compare soak runs' error.log by family: script errors (the 'Error:' line after each 'Script system error!'),
plus the top-level [E] messages, each counted once per occurrence; numbers folded to N.

Usage: python -I tests/one-offs/soak_families.py <run-folder> [<run-folder> ...]
"""
import re
import sys
from collections import Counter
from pathlib import Path

NUM = re.compile(r"\d+")


def families(log: Path) -> tuple[int, int, Counter, Counter]:
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    script, top = Counter(), Counter()
    n_script = 0
    for i, ln in enumerate(lines):
        if "Script system error!" in ln:
            n_script += 1
            nxt = next((x.strip() for x in lines[i + 1:i + 4] if x.strip().startswith("Error:")), "?")
            nxt = re.sub(r"\(\(no character\).*", "(no character)", nxt)
            script[NUM.sub("N", nxt)[:100]] += 1
        elif "[E]" in ln:
            msg = re.sub(r"^\[[\d:]+\]\[E\]\[[\w.]+:\d+\]: ", "", ln)
            top[NUM.sub("N", msg)[:90]] += 1
    return len(lines), n_script, script, top


runs = [Path(a) for a in sys.argv[1:]]
data = {r.name: families(r / "logs" / "error.log") for r in runs}
for name, (n, ns, sc, tp) in data.items():
    print(f"{name}: {n} lines, {ns} script errors, {sum(tp.values())} other [E]")
keys = Counter()
for _, (_, _, sc, _) in data.items():
    keys.update(sc)
print("\nscript-error families (count per run):")
for k, _ in keys.most_common(25):
    print("  " + " | ".join(f"{data[r][2][k]:>6}" for r in data) + "  " + k)
tk = Counter()
for _, (_, _, _, tp) in data.items():
    tk.update(tp)
print("\nother [E] families:")
for k, _ in tk.most_common(15):
    print("  " + " | ".join(f"{data[r][3][k]:>6}" for r in data) + "  " + k)
