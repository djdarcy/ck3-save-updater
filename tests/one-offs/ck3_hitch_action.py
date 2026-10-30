"""ck3_hitch_action: name the important action each hitch is evaluating, from the game's own memory. (2026-10-28)

Ghidra on ck3 1.20.1.2: FUN_142acb7e0 (the player's important-action manager, `mgr`) evaluates one action per call,
round-robin: index = [mgr+200] % [mgr+0xcc], then FUN_142acc7b0(mgr, index, db) runs the record's check block
(record = [[db+0x50] + index*8], db = [ck3+0x5c7c0d8], count [db+0x5c]); the record's key string is at
[record+0x18]. During a burst this finds the busy worker inside the job, copies its stack, takes every qword p with
[p+0xcc] == count and 0 <= [p+200] < count as the manager, and reads the index and the key. It also prints every
action's key with its index once, so an override list can be built.

Usage: python -I tests/one-offs/ck3_hitch_action.py [--bursts 6] [--list]
"""
from __future__ import annotations

import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_hitch_strings import rpm, snapshot_stack  # noqa: E402
from ck3_hitch_walk import Walker  # noqa: E402
from ck3_thread_cpu_poll import ck3_pid, cycles, ghz, threads  # noqa: E402


def main():
    a = sys.argv[1:]
    bursts = int(a[a.index("--bursts") + 1]) if "--bursts" in a else 6
    pid = ck3_pid()
    w = Walker(pid)
    ck3 = next(lo for lo, _, nm in w.mods if nm.lower() == "ck3")

    def q(addr):
        return int.from_bytes(rpm(w.hp, addr, 8), "little")

    def d(addr):
        return int.from_bytes(rpm(w.hp, addr, 4), "little", signed=True)

    db = q(ck3 + 0x5c7c0d8)
    arr, count = q(db + 0x50), d(db + 0x5c)

    def key(i):
        m = re.match(rb"[\x20-\x7e]+", rpm(w.hp, q(q(arr + 8 * i) + 0x18), 96))
        return m.group().decode() if m else "?"

    print(f"{count} important actions")
    if "--list" in a:
        for i in range(count):
            print(f"   {i:3d} {key(i)}")
    hz = ghz()
    th = threads(pid)
    by = {}
    for t, (_, nm) in th.items():
        by.setdefault(nm, t)
    main_t, render = by["Main Thread"], by["Render Thread"]
    workers = [t for t, (_, nm) in th.items() if nm.startswith("Primary Task")]
    watch = [main_t, render, *workers]

    def binshare():
        c0 = {t: cycles(th[t][0]) for t in watch}
        t0 = time.perf_counter()
        time.sleep(0.05)
        dt = time.perf_counter() - t0
        return {t: (cycles(th[t][0]) - c0[t]) / hz / dt for t in watch}

    seen, run, t0 = Counter(), 0, time.perf_counter()
    n = 0
    while n < bursts and time.perf_counter() - t0 < 120:
        s = binshare()
        run = run + 1 if (s[main_t] > 0.85 and s[render] < 0.03) else 0
        if run < 3:
            continue
        wk = next((t for t in sorted(workers, key=lambda t: -s[t])
                   if any("ck3+0x2acc" in f for f in w.walk(t, 120))), None)
        if wk is None:
            continue
        stack = snapshot_stack(w, wk)
        mgrs = set()
        for i in range(0, len(stack) - 7, 8):
            p = int.from_bytes(stack[i:i + 8], "little")
            if 0x10000 < p < 0x7FFFFFFFFFFF and d(p + 0xCC) == count and 0 <= d(p + 200) < count:
                mgrs.add(p)
        n += 1
        for p in mgrs:
            idx = d(p + 200)
            seen[(idx, key(idx))] += 1
            print(f"burst {n} ({th[wk][1]}): manager 0x{p:x}, player id {d(p + 0x28)}, index {idx} -> {key(idx)}",
                  flush=True)
        if not mgrs:
            print(f"burst {n}: no manager found on the stack", flush=True)
        run = 0
        time.sleep(0.8)
    print("\nactions running during hitches:")
    for (i, k), c in seen.most_common():
        print(f"   {c}x  index {i}: {k}")


if __name__ == "__main__":
    main()
