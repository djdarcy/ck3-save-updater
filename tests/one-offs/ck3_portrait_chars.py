"""ck3_portrait_chars: which characters is ck3.exe building portraits for? (2026-10-28)

ck3_worker_walk.py showed the paused-game load is portrait building (FUN_140aeeb00: character id -> portrait
description, then portrait-modifier triggers). This samples the Secondary Task workers every ~5 ms; for a worker
whose stack runs through the portrait chain (ck3+0x2c4f8f5 / 0xaeeba2), it copies the stack (ck3_hitch_strings
.snapshot_stack) and collects every qword that points at a character object -- [p+0x1c] == 'Char' (0x43686172) and
[p+0x18] == a plausible id -- the same layout the decompiles read through the character table at [ck3+0x5c7c4f0].
Counts per character id; the ids can be looked up in the save.

Usage: python -I tests/one-offs/ck3_portrait_chars.py <out.json> [--seconds 20]
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ck3_hitch_strings import rpm, snapshot_stack  # noqa: E402
from ck3_hitch_walk import Walker  # noqa: E402
from ck3_thread_cpu_poll import ck3_pid, threads  # noqa: E402

CHAR = 0x43686172


def main():
    a = sys.argv[1:]
    out = Path(a[0])
    seconds = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 20
    pid = ck3_pid()
    th = threads(pid)
    workers = [t for t, (_, nm) in th.items() if nm.startswith("Secondary Task")]
    w = Walker(pid)
    ids, per_sample = Counter(), []
    t0 = time.perf_counter()
    samples = 0
    while time.perf_counter() - t0 < seconds:
        for t in workers:
            fr = w.walk(t, 120)
            if not any(x in ("ck3+0x2c4f8f5", "ck3+0xaeeba2") for x in fr):
                continue
            stack = snapshot_stack(w, t)
            found = set()
            for i in range(0, len(stack) - 7, 8):
                p = int.from_bytes(stack[i:i + 8], "little")
                if 0x10000 < p < 0x7FFFFFFFFFFF:
                    b = rpm(w.hp, p + 0x18, 8)
                    if len(b) == 8 and int.from_bytes(b[4:], "little") == CHAR:
                        cid = int.from_bytes(b[:4], "little")
                        if cid != 0xFFFFFFFF:
                            found.add(cid)
            samples += 1
            ids.update(found)
            per_sample.append(sorted(found))
        time.sleep(0.005)
    out.write_text(json.dumps({"samples": samples, "counts": ids.most_common(), "per_sample": per_sample}),
                   encoding="utf-8")
    print(f"{samples} portrait-building samples; {len(ids)} distinct characters seen")
    for cid, n in ids.most_common(30):
        print(f"   {n:5d}  char {cid}")


if __name__ == "__main__":
    main()
