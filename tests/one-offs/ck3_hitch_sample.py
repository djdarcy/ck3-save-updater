"""ck3_hitch_sample: where does a running ck3.exe spend its time during the 2-second hitch? (2026-10-28)

djdarcy's play5/play6 saves hitch for ~200 ms every ~2 s, even while paused. A Windows Performance Recorder trace
needs an elevated prompt; this needs none. It attaches cdb non-invasively (-pv: threads are suspended for the read and
resumed on detach, the game keeps running) N times, saving each raw dump, and records per-thread user CPU time
(!runaway) and deep stacks (~*k). Then it aggregates:

  * CPU per thread between the first and last sample (which threads burn time while paused);
  * per thread, how many samples found it busy (top frame not a wait) and the most frequent ck3 frames in those
    samples, both as "top of stack" and as "anywhere on the stack" (inclusive), so the loop the hitch sits in shows
    up as a frame present in most busy samples.

Stacks are raw ck3+0xOFFSET (no PDB ships with the game); offsets map to Ghidra addresses as 0x140000000 + offset.

Usage: python -I tests/one-offs/ck3_hitch_sample.py <out folder> [--n 40] [--depth 80] [--analyse-only]
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

CDB = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"
WAIT = re.compile(r"NtWaitFor|NtDelayExecution|SleepConditionVariable|NtRemoveIoCompletion|ZwWaitFor|NtUserMsgWait"
                  r"|WaitForSingleObject|WaitForMultipleObjects|NtUserGetMessage|NtWaitForWorkViaWorkerFactory"
                  r"|ZwRemoveIoCompletion|NtSignalAndWait|RtlSleepConditionVariable")
THREAD = re.compile(r"^\s*[.#]?\s*(\d+)\s+Id: [0-9a-f]+\.([0-9a-f]+) .*?(?:\"([^\"]*)\")?\s*$")
FRAME = re.compile(r"^[0-9a-f`]+ [0-9a-f`]+\s+(\S+)")
RUNAWAY = re.compile(r"^\s*(\d+):([0-9a-f]+)\s+(\d+) days (\d+):(\d+):([\d.]+)")


def ck3_pid() -> str:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True).stdout
    m = re.search(r'"ck3\.exe","(\d+)"', out)
    if not m:
        sys.exit("ck3.exe is not running")
    return m.group(1)


def sample(pid: str, out: Path, n: int, depth: int):
    for i in range(n):
        t0 = time.time()
        r = subprocess.run([CDB, "-pv", "-p", pid, "-c", f"!runaway 1; ~*k {depth}; qd"], capture_output=True,
                           text=True, errors="replace")
        (out / f"s{i:03d}.txt").write_text(f"# t={t0:.3f}\n" + r.stdout, encoding="utf-8")
        print(f"sample {i + 1}/{n} ({time.time() - t0:.2f} s)", flush=True)


def parse(text: str):
    """-> (runaway {tid: seconds}, stacks {tid: (name, [frames])})"""
    run, stacks, cur = {}, {}, None
    for line in text.splitlines():
        m = RUNAWAY.match(line)
        if m:
            run[m.group(2)] = int(m.group(3)) * 86400 + int(m.group(4)) * 3600 + int(m.group(5)) * 60 + float(m.group(6))
            continue
        m = THREAD.match(line)
        if m and "Id:" in line:
            cur = m.group(2)
            stacks[cur] = (m.group(3) or "", [])
            continue
        m = FRAME.match(line)
        if m and cur:
            stacks[cur][1].append(m.group(1))
    return run, stacks


def analyse(out: Path, top: int = 12):
    files = sorted(out.glob("s*.txt"))
    parsed = [parse(f.read_text(encoding="utf-8", errors="replace")) for f in files]
    times = [float(f.read_text(encoding="utf-8").split("\n", 1)[0].split("=")[1]) for f in files]
    print(f"{len(files)} samples over {times[-1] - times[0]:.1f} s wall")
    first, last = parsed[0][0], parsed[-1][0]
    names = {}
    for _, st in parsed:
        for tid, (nm, _) in st.items():
            names.setdefault(tid, nm)
    deltas = sorted(((last.get(t, 0) - first.get(t, 0), t) for t in last), reverse=True)[:8]
    print("\nuser CPU between first and last sample:")
    for d, t in deltas:
        print(f"   {d:7.2f} s  {t} {names.get(t, '')}")
    busy = Counter()
    topf, incl = defaultdict(Counter), defaultdict(Counter)
    seen = Counter()
    for _, st in parsed:
        for tid, (nm, frames) in st.items():
            if not frames:
                continue
            seen[tid] += 1
            if any(WAIT.search(f) for f in frames[:4]):
                continue
            busy[tid] += 1
            ck = [f for f in frames if f.startswith("ck3+")]
            if ck:
                topf[tid][ck[0]] += 1
            for f in set(ck):
                incl[tid][f] += 1
    print("\nthreads busy in most samples:")
    for tid, b in busy.most_common(6):
        print(f"\n== thread {tid} {names.get(tid, '')}: busy in {b}/{seen[tid]} samples")
        print("   top ck3 frame:", ", ".join(f"{f} x{c}" for f, c in topf[tid].most_common(6)))
        print("   on the stack (inclusive):")
        for f, c in incl[tid].most_common(top):
            print(f"      {c:3d}/{b}  {f}")


def main():
    args = sys.argv[1:]
    out = Path(args[0])
    n = int(args[args.index("--n") + 1]) if "--n" in args else 40
    depth = int(args[args.index("--depth") + 1]) if "--depth" in args else 80
    out.mkdir(parents=True, exist_ok=True)
    if "--analyse-only" not in args:
        sample(ck3_pid(), out, n, depth)
    analyse(out)


if __name__ == "__main__":
    main()
