"""ck3_hitch_catch: take ck3.exe stack samples timed to land inside the hitch. (2026-10-28)

ck3_thread_cpu_poll.py showed the hitch: every ~1.7 s, for ~0.55 s, the main thread and one "Primary Task" worker run
at 100% while the render thread draws nothing. This polls the threads' cycle counters (no elevation), finds burst
onsets (render thread idle while the main thread is saturated), learns the period, and launches a non-invasive cdb
sample (-pv) timed so its suspension lands inside a burst. While cdb holds the threads suspended every counter
stops; the poller sees that freeze, so each sample is labelled IN or OUT of a burst by measurement, not by hope.

Usage: python -I tests/one-offs/ck3_hitch_catch.py <out folder> [--n 12] [--depth 120]
Each sample: <out>/h###.txt (cdb output; header says IN/OUT, the offset into the burst, and the busy worker).
"""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_thread_cpu_poll import ck3_pid, cycles, ghz, threads  # noqa: E402

CDB = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"
TICK = 0.005
WIN = 0.05  # seconds per detection bin


class Poller(threading.Thread):
    def __init__(self, th, hz):
        super().__init__(daemon=True)
        self.th, self.hz = th, hz
        self.by_name = {}
        for t, (_, nm) in th.items():
            self.by_name.setdefault(nm, t)
        self.main, self.render = self.by_name["Main Thread"], self.by_name["Render Thread"]
        self.workers = [t for t, (_, nm) in th.items() if nm.startswith("Primary Task")]
        self.rows = []  # (time, {tid: cycles})
        self.stop = False

    def run(self):
        while not self.stop:
            self.rows.append((time.perf_counter(), {t: cycles(h) for t, (h, _) in self.th.items()}))
            time.sleep(TICK)

    def share(self, tid, t_from, t_to):
        a = next((r for r in self.rows if r[0] >= t_from), None)
        b = next((r for r in reversed(self.rows) if r[0] <= t_to), None)
        if not a or not b or b[0] <= a[0]:
            return None
        return (b[1][tid] - a[1][tid]) / self.hz / (b[0] - a[0])

    def in_burst(self, t_from, t_to):
        m, r = self.share(self.main, t_from, t_to), self.share(self.render, t_from, t_to)
        return m is not None and m > 0.85 and r < 0.03

    def busy_worker(self, t_from, t_to):
        best = max(self.workers, key=lambda w: self.share(w, t_from, t_to) or 0)
        return self.th[best][1], self.share(best, t_from, t_to) or 0

    def freezes(self, t_from):
        """(start, end) spans after t_from where no thread's counter moved (cdb holding them suspended)."""
        out, start = [], None
        rows = [r for r in self.rows if r[0] >= t_from]
        for (ta, ca), (tb, cb) in zip(rows, rows[1:]):
            still = all(cb[t] == ca[t] for t in (self.main, self.render, *self.workers))
            if still and start is None:
                start = ta
            if not still and start is not None:
                out.append((start, ta))
                start = None
        return [f for f in out if f[1] - f[0] > 0.03]


def onsets(p: Poller, since: float, min_bins: int = 4):
    """Burst onsets since `since`: the start of a run of >= min_bins consecutive WIN-long in-burst bins (a single
    saturated bin is an ordinary heavy frame; the hitch is ~11 bins)."""
    rows = [r[0] for r in p.rows if r[0] >= since]
    if not rows:
        return []
    flags, t = [], rows[0]
    while t + WIN <= rows[-1]:
        flags.append((t, p.in_burst(t, t + WIN)))
        t += WIN
    out, run = [], 0
    for i, (t, f) in enumerate(flags):
        run = run + 1 if f else 0
        if run == min_bins:
            out.append(flags[i - min_bins + 1][0])
    return out


def main():
    a = sys.argv[1:]
    out = Path(a[0])
    n = int(a[a.index("--n") + 1]) if "--n" in a else 12
    depth = int(a[a.index("--depth") + 1]) if "--depth" in a else 120
    out.mkdir(parents=True, exist_ok=True)
    pid = str(ck3_pid())
    hz = ghz()
    p = Poller(threads(int(pid)), hz)
    p.start()
    t_start = time.perf_counter()
    time.sleep(6)
    ons = onsets(p, t_start)
    if len(ons) < 3:
        sys.exit(f"only {len(ons)} burst onsets in 6 s; is the hitch present?")
    gaps = [b - a for a, b in zip(ons, ons[1:])]
    period = sorted(gaps)[len(gaps) // 2]
    durs = []
    print(f"onsets at {[round(o - t_start, 2) for o in ons]}; period ~{period:.3f} s")
    latency = 0.35  # cdb launch -> suspension; refined from each measured freeze
    targets = [0.08 + 0.4 * i / max(1, n - 1) for i in range(n)]  # spread across the burst
    log = []
    for i, off in enumerate(targets):
        recent = onsets(p, time.perf_counter() - 4 * period)
        while not recent:
            time.sleep(period)
            recent = onsets(p, time.perf_counter() - 4 * period)
        nxt = recent[-1]
        while nxt + off - latency < time.perf_counter() + 0.02:
            nxt += period
        time.sleep(max(0, nxt + off - latency - time.perf_counter()))
        launched = time.perf_counter()
        r = subprocess.run([CDB, "-pv", "-p", pid, "-c", f"~*k {depth}; qd"], capture_output=True, text=True,
                           errors="replace")
        time.sleep(0.3)
        fz = p.freezes(launched)
        if not fz:
            label, detail = "UNKNOWN", "no freeze seen"
        else:
            f0 = fz[0][0]
            latency = 0.5 * latency + 0.5 * (f0 - launched)
            inb = p.in_burst(f0 - 0.06, f0 - 0.005)
            back = f0 - 0.005
            while p.in_burst(back - WIN, back):  # walk back to the start of this saturated run
                back -= WIN
            into = f0 - back
            wk, sh = p.busy_worker(f0 - 0.1, f0 - 0.005)
            label = "IN" if inb else "OUT"
            detail = f"freeze at +{f0 - launched:.3f}s after launch, {into:.3f}s after onset, busiest worker {wk} {sh:.0%}"
        (out / f"h{i:03d}.txt").write_text(f"# {label}: {detail}\n" + r.stdout, encoding="utf-8")
        log.append(f"h{i:03d} target +{off:.2f}s -> {label}: {detail}")
        print(log[-1], flush=True)
    p.stop = True
    (out / "catch.log").write_text("\n".join(log) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
