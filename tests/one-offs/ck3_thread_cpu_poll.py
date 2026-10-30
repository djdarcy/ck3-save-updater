"""ck3_thread_cpu_poll: a clock for the 2-second hitch -- per-thread CPU of a running ck3.exe, polled every few ms.
(2026-10-28)

The hitch (~200 ms every ~2 s, even paused) should show as a burst of CPU on the threads doing the work. This reads
every ck3.exe thread's cycle counter (QueryThreadCycleTime, precise, no elevation: same-user threads opened with
THREAD_QUERY_LIMITED_INFORMATION) in a tight loop, and reports per thread, per time bin, the share of one core used.
From the bursts it estimates the period and the phase, so a stack sample or a dump can be timed to land inside one.

Usage: python -I tests/one-offs/ck3_thread_cpu_poll.py [--seconds 12] [--bin-ms 50] [--csv out.csv]
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import re
import subprocess
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.OpenThread.restype = W.HANDLE
k32.QueryThreadCycleTime.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_ulonglong)]
k32.GetThreadDescription.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]


def ck3_pid() -> int:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True).stdout
    m = re.search(r'"ck3\.exe","(\d+)"', out)
    if not m:
        sys.exit("ck3.exe is not running")
    return int(m.group(1))


def threads(pid: int) -> dict[int, tuple[int, str]]:
    snap = k32.CreateToolhelp32Snapshot(4, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = {}
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            h = k32.OpenThread(0x0800, False, te.th32ThreadID)
            if h:
                p = ctypes.c_wchar_p()
                name = p.value if k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value else ""
                out[te.th32ThreadID] = (h, name)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def cycles(h) -> int:
    c = ctypes.c_ulonglong()
    k32.QueryThreadCycleTime(h, ctypes.byref(c))
    return c.value


def ghz() -> float:
    """Cycles per second of thread time, measured on this thread spinning for 0.3 s."""
    h = k32.GetCurrentThread()
    c0, t0 = cycles(h), time.perf_counter()
    while time.perf_counter() - t0 < 0.3:
        pass
    return (cycles(h) - c0) / (time.perf_counter() - t0)


def main():
    a = sys.argv[1:]
    secs = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 12
    bin_ms = float(a[a.index("--bin-ms") + 1]) if "--bin-ms" in a else 50
    csv = a[a.index("--csv") + 1] if "--csv" in a else None
    pid = ck3_pid()
    th = threads(pid)
    hz = ghz()
    nb = int(secs * 1000 / bin_ms)
    usage = {t: [0] * nb for t in th}
    last = {t: cycles(h) for t, (h, _) in th.items()}
    t0 = time.perf_counter()
    while True:
        now = time.perf_counter() - t0
        b = int(now * 1000 / bin_ms)
        if b >= nb:
            break
        for t, (h, _) in th.items():
            c = cycles(h)
            usage[t][b] += c - last[t]
            last[t] = c
        time.sleep(0.002)
    scale = hz * bin_ms / 1000
    tot = sorted(th, key=lambda t: -sum(usage[t]))[:10]
    print(f"pid {pid}, {len(th)} threads, {hz / 1e9:.2f} G cycles/s, {nb} bins of {bin_ms:.0f} ms")
    print("core-share per bin (0-9 = 0-90%+, . = <5%) for the 10 busiest threads:")
    for t in tot:
        row = "".join("." if u / scale < 0.05 else str(min(9, int(u / scale * 10))) for u in usage[t])
        print(f"{th[t][1][:20]:>20} {t:>6} {sum(usage[t]) / hz:5.2f}s |{row}|")
    if csv:
        with open(csv, "w", encoding="utf-8") as f:
            f.write("bin_ms," + ",".join(f"{th[t][1]}:{t}" for t in tot) + "\n")
            for i in range(nb):
                f.write(f"{i * bin_ms:.0f}," + ",".join(f"{usage[t][i] / scale:.3f}" for t in tot) + "\n")


if __name__ == "__main__":
    main()
