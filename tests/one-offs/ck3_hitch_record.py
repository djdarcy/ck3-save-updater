"""ck3_hitch_record: name the important action the hitch is evaluating. (2026-10-28)

FUN_142acc7b0 (ck3 1.20.1.2) fetches the action record for the round-robin index and passes record+0x48 (the
check_create_action block) to the interpreter (FUN_143778010). So a qword equal to record+0x48 should sit in the job's
entry frames. During a burst this copies those frames (ck3_hitch_strings' window: between the return-address slots
for ck3+0x3778097 and ck3+0x2acbaa8), and for every qword q reads 0x80 bytes at q-0x48 looking for an "action_" key,
inline or one pointer away. Candidates are counted per burst: the action present in every burst is the job.

Usage: python -I tests/one-offs/ck3_hitch_record.py [--bursts 5]
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

KEY = re.compile(rb"action_[a-z0-9_]{3,}")


def keys_at(hp, rec: int) -> set[str]:
    blob = rpm(hp, rec, 0x80)
    out = {m.group().decode() for m in KEY.finditer(blob)}
    for i in range(0, len(blob) - 7, 8):
        p = int.from_bytes(blob[i:i + 8], "little")
        if 0x10000 < p < 0x7FFFFFFFFFFF:
            m = KEY.match(rpm(hp, p, 96))
            if m:
                out.add(f"{m.group().decode()} (via +0x{i:x})")
    return out


def main():
    a = sys.argv[1:]
    bursts = int(a[a.index("--bursts") + 1]) if "--bursts" in a else 5
    pid = ck3_pid()
    hz = ghz()
    th = threads(pid)
    by = {}
    for t, (_, nm) in th.items():
        by.setdefault(nm, t)
    main_t, render = by["Main Thread"], by["Render Thread"]
    workers = [t for t, (_, nm) in th.items() if nm.startswith("Primary Task")]
    watch = [main_t, render, *workers]
    w = Walker(pid)
    ck3 = next(lo for lo, _, nm in w.mods if nm.lower() == "ck3")

    def binshare():
        c0 = {t: cycles(th[t][0]) for t in watch}
        t0 = time.perf_counter()
        time.sleep(0.05)
        dt = time.perf_counter() - t0
        return {t: (cycles(th[t][0]) - c0[t]) / hz / dt for t in watch}

    found, run, t0 = [], 0, time.perf_counter()
    while len(found) < bursts and time.perf_counter() - t0 < 120:
        s = binshare()
        run = run + 1 if (s[main_t] > 0.85 and s[render] < 0.03) else 0
        if run < 3:
            continue
        wk = next((t for t in sorted(workers, key=lambda t: -s[t])
                   if any("ck3+0x2acc" in f for f in w.walk(t, 120))), None)
        if wk is None:
            continue
        stack = snapshot_stack(w, wk)
        slots = {}
        for i in range(0, len(stack) - 7, 8):
            q = int.from_bytes(stack[i:i + 8], "little")
            for off in (0x3778097, 0x2acbaa8):
                if q == ck3 + off and off not in slots:
                    slots[off] = i
        if len(slots) < 2:
            continue
        win = stack[slots[0x3778097]:slots[0x2acbaa8] + 0x200]
        cands = {}
        for i in range(0, len(win) - 7, 8):
            q = int.from_bytes(win[i:i + 8], "little")
            if 0x10000 < q < 0x7FFFFFFFFFFF:
                ks = keys_at(w.hp, q - 0x48)
                if ks:
                    cands[f"slot+0x{i:x} q=0x{q:x}"] = sorted(ks)
        found.append(cands)
        print(f"burst {len(found)} ({th[wk][1]}):")
        for k, v in cands.items():
            print(f"   {k}: {v}")
        run = 0
        time.sleep(0.8)
    c = Counter(x.split(" ")[0] for b in found for x in {y for v in b.values() for y in v})
    print("\naction keys by number of bursts they appeared in:")
    for k, n in c.most_common(15):
        print(f"   {n}/{len(found)}  {k}")


if __name__ == "__main__":
    main()
