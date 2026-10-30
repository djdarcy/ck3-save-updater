"""ck3_hitch_strings: which script is the hitch running? Text reachable from the busy worker's stack. (2026-10-28)

ck3_hitch_walk.py + Ghidra: the hitch is FUN_142acb7e0 evaluating, round-robin, one item of a per-player list
(FUN_142acc7b0 runs the item's script block through the interpreter, FUN_143778010). The decompile names nothing,
but Paradox script nodes carry their source text and file location in memory. This waits for a burst, suspends the
busy worker, copies its stack (RSP upward until unreadable, cap 256 KiB), resumes it, then follows every qword that
looks like a pointer one and two levels, collects printable ASCII runs, and counts in how many bursts each string
was reachable. Strings present in every burst -- file paths, script keys -- name the job.

Usage: python -I tests/one-offs/ck3_hitch_strings.py <out.json> [--bursts 5]
"""
from __future__ import annotations

import ctypes
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_hitch_walk import CONTEXT_FULL, CTX_FLAGS_OFF, CTX_SIZE, RSP, Walker, k32  # noqa: E402
from ck3_thread_cpu_poll import ck3_pid, cycles, ghz, threads  # noqa: E402

k32.ReadProcessMemory.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
TEXT = re.compile(rb"[\x20-\x7e]{6,}")
MAXLEVEL = 3 if "--window" in sys.argv else 2


def rpm(hp, addr: int, n: int) -> bytes:
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return b""
    return buf.raw[:got.value]


def snapshot_stack(w: Walker, tid: int) -> bytes:
    h = w.handles.get(tid) or k32.OpenThread(0x0002 | 0x0008 | 0x0040, False, tid)
    w.handles[tid] = h
    if k32.SuspendThread(h) == 0xFFFFFFFF:
        return b""
    try:
        ctypes.memset(w.ctx, 0, CTX_SIZE)
        ctypes.c_uint32.from_address(w.ctx + CTX_FLAGS_OFF).value = CONTEXT_FULL
        if not k32.GetThreadContext(h, w.ctx):
            return b""
        rsp = ctypes.c_uint64.from_address(w.ctx + RSP).value
        out, a = [], rsp
        while a - rsp < 256 * 1024:
            page = rpm(w.hp, a, 4096 - (a % 4096))
            if not page:
                break
            out.append(page)
            a += len(page)
        return b"".join(out)
    finally:
        k32.ResumeThread(h)


def strings_from(hp, stack: bytes, mods) -> set[str]:
    lo_mod = [(lo, hi) for lo, hi, _ in mods]
    found: set[str] = set()
    seen: set[int] = set()

    def plausible(p):
        return 0x10000 < p < 0x7FFFFFFFFFFF and not any(lo <= p < hi for lo, hi in lo_mod)

    def harvest(p, level):
        if p in seen or len(seen) > 40000:
            return
        seen.add(p)
        blob = rpm(hp, p, 256)
        if not blob:
            return
        for m in TEXT.finditer(blob[:160]):
            found.add(m.group().decode())
        if level < MAXLEVEL:
            for i in range(0, len(blob) - 7, 8):
                q = int.from_bytes(blob[i:i + 8], "little")
                if plausible(q):
                    harvest(q, level + 1)

    for i in range(0, len(stack) - 7, 8):
        q = int.from_bytes(stack[i:i + 8], "little")
        if plausible(q):
            harvest(q, 1)
    return found


def main():
    a = sys.argv[1:]
    out = Path(a[0])
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

    def binshare():
        c0 = {t: cycles(th[t][0]) for t in watch}
        t0 = time.perf_counter()
        time.sleep(0.05)
        dt = time.perf_counter() - t0
        return {t: (cycles(th[t][0]) - c0[t]) / hz / dt for t in watch}

    per_burst, run, t_start = [], 0, time.perf_counter()
    while len(per_burst) < bursts and time.perf_counter() - t_start < 90:
        s = binshare()
        run = run + 1 if (s[main_t] > 0.85 and s[render] < 0.03) else 0
        if run < 3:
            continue
        wk = next((t for t in sorted(workers, key=lambda t: -s[t])
                   if any("ck3+0x2acc" in f for f in w.walk(t, 120))), None)
        if wk is None:
            continue  # no worker is inside the job at this instant; try the next bin
        stack = snapshot_stack(w, wk)
        if "--window" in a:
            # only the frames of the job's entry (FUN_142acb7e0 / FUN_142acc7b0 / FUN_143778010): between the slot
            # holding return address ck3+0x3778097 and the one holding ck3+0x2acbaa8, plus 0x200 bytes beyond
            ck3 = next(lo for lo, _, nm in w.mods if nm.lower() == "ck3")
            slots = {}
            for i in range(0, len(stack) - 7, 8):
                q = int.from_bytes(stack[i:i + 8], "little")
                for off in (0x3778097, 0x2acbaa8):
                    if q == ck3 + off and off not in slots:
                        slots[off] = i
            if len(slots) < 2:
                continue
            stack = stack[slots[0x3778097]:slots[0x2acbaa8] + 0x200]
        strs = strings_from(w.hp, stack, w.mods)
        per_burst.append(sorted(strs))
        print(f"burst {len(per_burst)}: worker {th[wk][1]}, stack {len(stack)} bytes, {len(strs)} strings", flush=True)
        run = 0
        time.sleep(0.8)
    c = Counter(x for b in per_burst for x in b)
    out.write_text(json.dumps({"bursts": per_burst}, indent=0), encoding="utf-8")
    n = len(per_burst)
    hits = [x for x, k in c.items() if k == n]
    keyish = sorted(x for x in hits if ("/" in x or "_" in x) and " " not in x.strip())
    print(f"\n{len(hits)} strings reachable in all {n} bursts; path- or key-like ones:")
    for x in keyish[:200]:
        print("  ", x[:150])


if __name__ == "__main__":
    main()
