"""ck3_worker_walk: what are ck3.exe's worker threads doing while the game is paused? (2026-10-28)

After the cathedral-alert test mod removed the 0.55 s single-worker stall, a paused play6 still shows bursts on all
six "Secondary Task" threads: short ones every ~0.45 s and ~0.3 s ones (main thread saturated, render idle) about
every 10 s. This polls the threads' cycle counters in 20 ms bins; whenever the named workers together use more than
--min-cores cores in a bin, it walks every busy one of them plus the main thread (ck3_hitch_walk.Walker:
suspend, StackWalk64, resume) and records the stacks with the burst's size. Then it groups the busy-worker stacks
by their root-side chain of ck3 frames, separately for big bursts (main saturated) and small ones.

Usage: python -I tests/one-offs/ck3_worker_walk.py <out.jsonl> [--seconds 30] [--prefix "Secondary Task"]
                                                  [--min-cores 2.5]
       python -I tests/one-offs/ck3_worker_walk.py <out.jsonl> --analyse
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_hitch_walk import Walker  # noqa: E402
from ck3_thread_cpu_poll import ck3_pid, cycles, ghz, threads  # noqa: E402

WAITS = ("ntdll+", "KERNELBASE+", "KERNEL32+")


def collect(out: Path, seconds: float, prefix: str, min_cores: float):
    pid = ck3_pid()
    hz = ghz()
    th = threads(pid)
    by = {}
    for t, (_, nm) in th.items():
        by.setdefault(nm, t)
    main_t, render = by["Main Thread"], by["Render Thread"]
    workers = [t for t, (_, nm) in th.items() if nm.startswith(prefix)]
    watch = [main_t, render, *workers]
    w = Walker(pid)
    BIN = 0.02
    f = out.open("a", encoding="utf-8")
    t0 = time.perf_counter()
    n = 0
    while time.perf_counter() - t0 < seconds:
        c0 = {t: cycles(th[t][0]) for t in watch}
        a = time.perf_counter()
        time.sleep(BIN)
        dt = time.perf_counter() - a
        s = {t: (cycles(th[t][0]) - c0[t]) / hz / dt for t in watch}
        load = sum(s[t] for t in workers)
        if load < min_cores:
            continue
        big = s[main_t] > 0.85 and s[render] < 0.05
        rec = {"t": round(a - t0, 3), "load": round(load, 2), "big": big, "main": round(s[main_t], 2),
               "render": round(s[render], 2), "stacks": {}}
        for t in [main_t] + sorted(workers, key=lambda t: -s[t]):
            if t != main_t and s[t] < 0.5:
                continue
            rec["stacks"][th[t][1]] = w.walk(t, 120)
        f.write(json.dumps(rec) + "\n")
        n += 1
    f.close()
    print(f"{n} busy bins recorded in {seconds:.0f} s")


SCHED = {"0x3fcfbea", "0x3fcfa11", "0x3fa365a", "0x4254910", "0x3fa3582", "0x3fa4cdf", "0x3fa4e03", "0x3fa4b8c",
         "0x4233b52", "0x422fbd8"}  # thread entry and task-scheduler frames, the same under every job


def profile(out: Path, seconds: float, prefix: str):
    """Sampling profiler: walk every named worker (and the main thread) every ~5 ms; keep the samples in which at
    least one worker is not inside a wait. 'big' marks samples where 4+ workers are busy at once."""
    pid = ck3_pid()
    th = threads(pid)
    by = {}
    for t, (_, nm) in th.items():
        by.setdefault(nm, t)
    main_t = by["Main Thread"]
    workers = [t for t, (_, nm) in th.items() if nm.startswith(prefix)]
    w = Walker(pid)
    f = out.open("a", encoding="utf-8")
    t0 = time.perf_counter()
    n = kept = 0
    while time.perf_counter() - t0 < seconds:
        n += 1
        st = {}
        for t in workers:
            fr = w.walk(t, 120)
            if fr and not any(k in x for x in fr[:4] for k in ("NtWaitFor", "ntdll+0x1659c4")) and \
                    not (fr[0].startswith("ntdll+") and any("0x4231405" in x for x in fr[:5])):
                st[th[t][1]] = fr
        if st:
            kept += 1
            st["Main Thread"] = w.walk(main_t, 120)
            f.write(json.dumps({"t": round(time.perf_counter() - t0, 3), "load": len(st) - 1,
                                "big": len(st) - 1 >= 4, "main": 0, "render": 0, "stacks": st}) + "\n")
        time.sleep(0.005)
    f.close()
    print(f"{kept} of {n} sweeps found a busy worker")


def chain(frames, n=10):
    ck = [x.replace("ck3+", "") for x in frames if x.startswith("ck3+")]
    ck = [x for x in ck if x not in SCHED]
    return " < ".join(ck[::-1][:n][::-1]) if ck else "(no ck3 frames)"


def analyse(out: Path):
    recs = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines() if x.strip()]
    ts = [r["t"] for r in recs]
    print(f"{len(recs)} busy bins; big (main saturated, render idle): {sum(r['big'] for r in recs)}")
    groups = []
    for r in recs:
        if groups and r["t"] - groups[-1][-1]["t"] < 0.1:
            groups[-1].append(r)
        else:
            groups.append([r])
    print("bursts (start s, bins, peak load, big):",
          ", ".join(f"{g[0]['t']:.2f}/{len(g)}/{max(x['load'] for x in g):.1f}/{any(x['big'] for x in g)}"
                    for g in groups))
    for kind in (True, False):
        rs = [r for r in recs if r["big"] == kind]
        if not rs:
            continue
        roots, leaves, mains = Counter(), Counter(), Counter()
        for r in rs:
            for nm, fr in r["stacks"].items():
                if nm == "Main Thread":
                    mains[chain(fr, 8)] += 1
                    continue
                roots[chain(fr, 10)] += 1
                ck = [x for x in fr if x.startswith("ck3+")]
                if ck:
                    leaves[ck[0]] += 1
        print(f"\n=== {'BIG bursts' if kind else 'small bursts'}: {len(rs)} bins")
        print("  worker root-side chains (outermost 10 ck3 frames, innermost on the left):")
        for c, k in roots.most_common(8):
            print(f"    {k:4d}  {c}")
        print("  worker innermost ck3 frames:", ", ".join(f"{x} x{k}" for x, k in leaves.most_common(10)))
        print("  main thread chains:")
        for c, k in mains.most_common(4):
            print(f"    {k:4d}  {c}")


def main():
    a = sys.argv[1:]
    out = Path(a[0])
    if "--analyse" in a:
        analyse(out)
        return
    seconds = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 30
    prefix = a[a.index("--prefix") + 1] if "--prefix" in a else "Secondary Task"
    min_cores = float(a[a.index("--min-cores") + 1]) if "--min-cores" in a else 2.5
    if "--profile" in a:
        profile(out, seconds, prefix)
    else:
        collect(out, seconds, prefix, min_cores)
    analyse(out)


if __name__ == "__main__":
    main()
