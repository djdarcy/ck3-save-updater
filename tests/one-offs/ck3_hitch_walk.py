"""ck3_hitch_walk: stacks of ck3.exe's main thread and busy worker, sampled INSIDE each hitch. (2026-10-28)

The hitch: ~0.55 s with the main thread and one "Primary Task" worker at 100% and the render thread idle, at an
irregular 1.7-2.9 s period. cdb takes ~0.44 s to attach, too slow to aim at an irregular target, so this walks the
stacks itself: it polls thread cycle counters (ck3_thread_cpu_poll), detects a burst after two saturated 50 ms bins,
then every 50 ms until the burst ends it suspends the main thread and the busiest Primary Task worker for a few ms
each, walks the stack with dbghelp's StackWalk64 (unwind data from the loaded modules; no PDB ships, so frames are
module+offset), and resumes. Control samples are taken 0.6 s after each burst ends. No debugger attaches, no
elevation; each thread is held for the duration of one walk (milliseconds).

Usage: python -I tests/one-offs/ck3_hitch_walk.py <out.jsonl> [--bursts 8] [--depth 120]
Then:  python -I tests/one-offs/ck3_hitch_walk.py <out.jsonl> --analyse
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_thread_cpu_poll import ck3_pid, cycles, ghz, threads  # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
dbg = ctypes.WinDLL("dbghelp", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)


class ADDRESS64(ctypes.Structure):
    _fields_ = [("Offset", ctypes.c_uint64), ("Segment", ctypes.c_uint16), ("Mode", ctypes.c_int)]


class STACKFRAME64(ctypes.Structure):
    _fields_ = [("AddrPC", ADDRESS64), ("AddrReturn", ADDRESS64), ("AddrFrame", ADDRESS64),
                ("AddrStack", ADDRESS64), ("AddrBStore", ADDRESS64), ("FuncTableEntry", ctypes.c_void_p),
                ("Params", ctypes.c_uint64 * 4), ("Far", W.BOOL), ("Virtual", W.BOOL),
                ("Reserved", ctypes.c_uint64 * 3), ("KdHelp", ctypes.c_byte * 512)]


k32.OpenProcess.restype = W.HANDLE
k32.OpenThread.restype = W.HANDLE
k32.SuspendThread.argtypes = [W.HANDLE]
k32.ResumeThread.argtypes = [W.HANDLE]
k32.GetThreadContext.argtypes = [W.HANDLE, ctypes.c_void_p]
dbg.SymInitializeW.argtypes = [W.HANDLE, W.LPCWSTR, W.BOOL]
dbg.SymFunctionTableAccess64.restype = ctypes.c_void_p
dbg.SymGetModuleBase64.restype = ctypes.c_uint64
dbg.StackWalk64.argtypes = [W.DWORD, W.HANDLE, W.HANDLE, ctypes.POINTER(STACKFRAME64), ctypes.c_void_p,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
psapi.EnumProcessModulesEx.argtypes = [W.HANDLE, ctypes.POINTER(W.HMODULE), W.DWORD, ctypes.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
psapi.GetModuleInformation.argtypes = [W.HANDLE, W.HMODULE, ctypes.c_void_p, W.DWORD]

CTX_SIZE, CTX_FLAGS_OFF, RIP, RSP, RBP = 1232, 0x30, 0xF8, 0x98, 0xA0
CONTEXT_FULL = 0x10000B


class Walker:
    def __init__(self, pid: int):
        self.hp = k32.OpenProcess(0x0410, False, pid)  # QUERY_INFORMATION | VM_READ
        if not self.hp:
            sys.exit(f"OpenProcess failed: {ctypes.get_last_error()}")
        dbg.SymSetOptions(0x00000004 | 0x00000002)  # DEFERRED_LOADS | UNDNAME
        if not dbg.SymInitializeW(self.hp, None, True):
            sys.exit(f"SymInitialize failed: {ctypes.get_last_error()}")
        self.mods = self._modules()
        self.fta = ctypes.cast(dbg.SymFunctionTableAccess64, ctypes.c_void_p)
        self.gmb = ctypes.cast(dbg.SymGetModuleBase64, ctypes.c_void_p)
        self.buf = ctypes.create_string_buffer(CTX_SIZE + 16)
        addr = ctypes.addressof(self.buf)
        self.ctx = addr + (-addr % 16)
        self.handles = {}

    def _modules(self):
        arr = (W.HMODULE * 2048)()
        need = W.DWORD()
        psapi.EnumProcessModulesEx(self.hp, arr, ctypes.sizeof(arr), ctypes.byref(need), 3)
        out = []
        for i in range(need.value // ctypes.sizeof(W.HMODULE)):
            name = ctypes.create_unicode_buffer(260)
            psapi.GetModuleBaseNameW(self.hp, arr[i], name, 260)
            info = (ctypes.c_uint64 * 3)()
            psapi.GetModuleInformation(self.hp, arr[i], info, ctypes.sizeof(info))
            out.append((info[0], info[0] + (info[1] & 0xFFFFFFFF), name.value.rsplit(".", 1)[0]))
        return sorted(out)

    def name(self, a: int) -> str:
        for lo, hi, nm in self.mods:
            if lo <= a < hi:
                return f"{nm}+0x{a - lo:x}"
        return f"0x{a:x}"

    def walk(self, tid: int, depth: int) -> list[str]:
        h = self.handles.get(tid)
        if h is None:
            h = self.handles[tid] = k32.OpenThread(0x0002 | 0x0008 | 0x0040, False, tid)
        if k32.SuspendThread(h) == 0xFFFFFFFF:
            return []
        try:
            ctypes.memset(self.ctx, 0, CTX_SIZE)
            ctypes.c_uint32.from_address(self.ctx + CTX_FLAGS_OFF).value = CONTEXT_FULL
            if not k32.GetThreadContext(h, self.ctx):
                return []
            sf = STACKFRAME64()
            for fld, off in (("AddrPC", RIP), ("AddrStack", RSP), ("AddrFrame", RBP)):
                a = getattr(sf, fld)
                a.Offset = ctypes.c_uint64.from_address(self.ctx + off).value
                a.Mode = 3  # AddrModeFlat
            pcs = []
            while len(pcs) < depth and dbg.StackWalk64(0x8664, self.hp, h, ctypes.byref(sf), self.ctx, None,
                                                       self.fta, self.gmb, None):
                if not sf.AddrPC.Offset:
                    break
                pcs.append(sf.AddrPC.Offset)
        finally:
            k32.ResumeThread(h)
        return [self.name(a) for a in pcs]


def collect(out: Path, bursts: int, depth: int):
    pid = ck3_pid()
    hz = ghz()
    th = threads(pid)
    by = {}
    for t, (_, nm) in th.items():
        by.setdefault(nm, t)
    main, render = by["Main Thread"], by["Render Thread"]
    workers = [t for t, (_, nm) in th.items() if nm.startswith("Primary Task")]
    watch = [main, render, *workers]
    w = Walker(pid)
    BIN = 0.05
    f = out.open("a", encoding="utf-8")

    def binshare():
        c0 = {t: cycles(th[t][0]) for t in watch}
        t0 = time.perf_counter()
        time.sleep(BIN)
        dt = time.perf_counter() - t0
        return {t: (cycles(th[t][0]) - c0[t]) / hz / dt for t in watch}

    def sat(s):
        return s[main] > 0.85 and s[render] < 0.03

    seen, run, burst_i = 0, 0, 0
    t_start = time.perf_counter()
    while seen < bursts and time.perf_counter() - t_start < 120:
        s = binshare()
        run = run + 1 if sat(s) else 0
        if run < 2:
            continue
        seen += 1
        k = 0
        while sat(s):
            wk = max(workers, key=lambda t: s[t])
            for tid, role in ((main, "main"), (wk, "worker")):
                rec = {"burst": seen, "k": k, "in": True, "role": role, "thread": th[tid][1],
                       "share": round(s[tid], 2), "t": round(time.perf_counter() - t_start, 3),
                       "frames": w.walk(tid, depth)}
                f.write(json.dumps(rec) + "\n")
            k += 1
            s = binshare()
        print(f"burst {seen}: {k} in-burst samples (lasted >= {(k + 2) * BIN:.2f} s)", flush=True)
        time.sleep(0.6)
        s = binshare()
        wk = max(workers, key=lambda t: s[t])
        for tid, role in ((main, "main"), (wk, "worker")):
            rec = {"burst": seen, "k": -1, "in": False, "role": role, "thread": th[tid][1],
                   "share": round(s[tid], 2), "t": round(time.perf_counter() - t_start, 3),
                   "frames": w.walk(tid, depth)}
            f.write(json.dumps(rec) + "\n")
        run = 0
    f.close()


def analyse(out: Path, top: int = 25):
    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    for role in ("main", "worker"):
        for inb in (True, False):
            rs = [r for r in recs if r["role"] == role and r["in"] == inb]
            if not rs:
                continue
            incl, leaf = Counter(), Counter()
            for r in rs:
                fr = r["frames"]
                if fr:
                    leaf[fr[0]] += 1
                for x in set(fr):
                    incl[x] += 1
            print(f"\n== {role}, {'IN burst' if inb else 'control (outside)'}: {len(rs)} samples")
            print("   leaf:", ", ".join(f"{x} x{c}" for x, c in leaf.most_common(8)))
            print("   inclusive (frames on the stack):")
            for x, c in incl.most_common(top):
                print(f"      {c:3d}/{len(rs)}  {x}")


def main():
    a = sys.argv[1:]
    out = Path(a[0])
    if "--analyse" in a:
        analyse(out)
        return
    bursts = int(a[a.index("--bursts") + 1]) if "--bursts" in a else 8
    depth = int(a[a.index("--depth") + 1]) if "--depth" in a else 120
    out.parent.mkdir(parents=True, exist_ok=True)
    collect(out, bursts, depth)
    analyse(out)


if __name__ == "__main__":
    main()
