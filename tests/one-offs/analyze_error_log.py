"""Summarize a CK3 error.log / debug.log from a load attempt: group messages by pattern, count, show examples.

Usage: python -I analyze_error_log.py <run-folder>
Reads <run>/logs/error.log, debug.log, game.log. Numbers and quoted ids are normalised to '#' so the
same complaint about 10,000 characters becomes one row. Prints the top patterns, the first
occurrence of each, and the last 40 distinct debug.log "phases" before the end.
"""
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path

LINE = re.compile(r"^\[(\d\d:\d\d:\d\d)\]\[(\w)\]\[([\w.]+):(\d+)\]: ?(.*)$")
NUM = re.compile(r"\d+")


def normalise(msg: str) -> str:
    # pdx_persistent_reader wraps the real complaint in quotes: keep its first clause, drop the location
    m = re.match(r'Error: "(.*?)(?:, near line: \d+)?"', msg)
    if m:
        inner = m.group(1)
        if inner.startswith("Unexpected decoded length for bitset") or inner.startswith("Unknown event"):
            inner = re.sub(r": [A-Za-z0-9+/=]{4,}$", ": <base64>", inner)   # bitset / event payloads
        msg = "Error: " + inner
    else:
        msg = re.sub(r'"[^"]*"', '"…"', msg)
    msg = re.sub(r"near line: \d+", "near line: #", msg)
    msg = re.sub(r"(?<![A-Za-z_])\d+(?![A-Za-z_])", "#", msg)
    return msg[:160]


def main(run: str) -> None:
    run_p = Path(run)
    err = run_p / "logs" / "error.log"
    counts: Counter = Counter()
    first: "OrderedDict[str, str]" = OrderedDict()
    sources: Counter = Counter()
    n = 0
    cont = 0
    with err.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            m = LINE.match(raw)
            if not m:
                cont += 1
                continue
            n += 1
            _, lvl, src, _, msg = m.groups()
            key = f"{src}: {normalise(msg)}"
            counts[key] += 1
            sources[src] += 1
            first.setdefault(key, raw[:400])
    print(f"error.log: {n:,} tagged lines, {cont:,} continuation lines, {len(counts)} distinct patterns\n")
    print("== by source file ==")
    for src, c in sources.most_common():
        print(f"{c:>8,}  {src}")
    print("\n== top patterns (count, pattern) ==")
    for key, c in counts.most_common(80):
        print(f"{c:>8,}  {key}")
    print("\n== first occurrence of each pattern, in log order ==")
    for key, example in first.items():
        print(f"[{counts[key]:,}] {example}")

    dbg = run_p / "logs" / "debug.log"
    if dbg.exists():
        lines = dbg.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n== debug.log: {len(lines):,} lines; distinct source tags in order of last appearance (last 60) ==")
        last_seen: "OrderedDict[str, str]" = OrderedDict()
        for raw in lines:
            m = LINE.match(raw)
            if m:
                src = m.group(3)
                last_seen.pop(src, None)
                last_seen[src] = raw[:200]
        for src, raw in list(last_seen.items())[-60:]:
            print(f"  {raw}")
        print("\n== debug.log: last 15 lines that are not scheme_manager noise ==")
        tail = [l for l in lines if "scheme_manager.cpp" not in l][-15:]
        for l in tail:
            print("  " + l[:220])

    game = run_p / "logs" / "game.log"
    if game.exists():
        txt = game.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"\n== game.log: {len(txt)} lines; last 25 ==")
        for l in txt[-25:]:
            print("  " + l[:220])


if __name__ == "__main__":
    main(sys.argv[1])
