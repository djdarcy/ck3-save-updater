"""ck3_split_capture: read the AI army planner's state out of a running ck3.exe stuck in the endless split.

2026-10-27: the 20 March 989 stop is ck3+0x19f93e0 (1.20.1.2) splitting an army group without end: each pass that
reaches the last group appends a new one (ck3+0x19f8d30, tag 0x41495355) and the walk goes on into it. The split
shrinks only when the members it moves carry strength: a member id resolves through the table at [ck3+0x5d33390]
to an object whose +0x178 names an id in the table at [ck3+0x5d32e58], whose +0x38 the strength is read from; an id
that does not resolve takes the default object [ck3+0x5d32e60] instead. This script finds the stuck frame and dumps
the planner (its first argument, kept in the frame's home slot: frame SP + 0x210), its groups (+0x40 list, +0x4c
count; a group keeps member ids at +0x10, count +0x1c, tag +0x4c), and each member's chain.

Non-invasive (cdb -pv): the game's threads are suspended for each read and resumed on detach. Three reads.
Never run against anything but ck3.exe. Writes only into <out folder>.

Usage: python -I tests/one-offs/ck3_split_capture.py <out folder>
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

CDB = r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\cdb.exe"
LO, HI = 0x19F93E0, 0x19F9C65          # FUN_1419f93e0, the split loop
HOME = 0x210                           # frame SP + 0x1c8 locals + 8 pushes + return address = the rcx home slot
UNITS, ARMIES, DEFAULT = "ck3+0x5d33390", "ck3+0x5d32e58", "ck3+0x5d32e60"
FRAME = re.compile(r"^\s*([0-9a-f`]{17})\s+[0-9a-f`]{17}\s+ck3\+0x([0-9a-f]+)", re.M)
THREAD = re.compile(r"^\s*[.#]?\s*(\d+)\s+Id:", re.M)


def pid() -> int:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ck3.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    m = re.search(r'"ck3\.exe","(\d+)"', out)
    if not m:
        sys.exit("ck3.exe is not running")
    return int(m.group(1))


def cdb(p: int, cmds: list[str], out: Path) -> str:
    r = subprocess.run([CDB, "-pv", "-p", str(p), "-c", "; ".join(cmds + ["qd"])], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=240, errors="replace")
    out.write_text(r.stdout + r.stderr, encoding="utf-8")
    return r.stdout


def release(p: int) -> str:
    """A non-invasive attach suspends every thread once and qd releases it, so while attached each thread must
    show "Suspend: 1"; more means a session left the game frozen (ck3_freeze_capture.sh did, twice, 2026-10-27).
    Release the excess, whatever caused it."""
    notes = []
    for _ in range(3):
        r = subprocess.run([CDB, "-pv", "-p", str(p), "-c", "~; qd"], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=120, errors="replace")
        counts = [int(n) for n in re.findall(r"Suspend: (\d+)", r.stdout)]
        if not counts or max(counts) <= 1:
            break
        subprocess.run([CDB, "-pv", "-p", str(p), "-c", "~*m; qd"], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
        notes.append(f"released a leftover suspension (suspend count {max(counts)} while attached)")
    return "; ".join(notes)


def values(text: str, tag: str) -> list[list[str]]:
    return [l.split()[1:] for l in text.splitlines() if l.startswith(tag + " ")]


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    p = pid()
    # 1. which thread is in the split, and its frame SP
    t1 = cdb(p, ["~*k 40"], out / "1_stacks.txt")
    sp, thread = None, None
    for block in re.split(r"(?=^\s*[.#]?\s*\d+\s+Id:)", t1, flags=re.M):
        th = THREAD.match(block)
        for m in FRAME.finditer(block):
            if LO <= int(m.group(2), 16) < HI:
                sp, thread = int(m.group(1).replace("`", ""), 16), th and th.group(1)
                break
        if sp:
            break
    if sp is None:
        rel = release(p) or "no leftover suspension"
        (out / "summary.txt").write_text(f"no thread is inside ck3+0x19f93e0: not the split loop\nrelease: {rel}\n")
        print(f"no thread is inside the split loop; release: {rel}")
        return
    # 2. the planner, its owner object, and its first and last groups
    cmds = [f"r $t0 = poi(0x{sp + HOME:x})",
            '.printf "PLANNER %p\\n", @$t0',
            "dq @$t0 L20",
            "r $t1 = dwo(@$t0+0x4c)", "r $t2 = poi(@$t0+0x40)", "r $t3 = poi(@$t0+0x58)",
            '.printf "GROUPS %x LIST %p OWNER %p OWNER78 %x OWNER68 %x P60 %p\\n", @$t1, @$t2, @$t3, '
            'dwo(@$t3+0x78), by(@$t3+0x68), poi(@$t0+0x60)',
            "dq @$t3 L20"]
    for label, idx in [("G0", "0"), ("G1", "1"), ("G2", "2"), ("GL2", "@$t1-3"), ("GL1", "@$t1-2"), ("GL", "@$t1-1")]:
        cmds += [f"r $t4 = poi(@$t2 + 8*({idx}))",
                 f'.printf "{label} %p COUNT %x TAG %x IDS %p\\n", @$t4, dwo(@$t4+0x1c), dwo(@$t4+0x4c), poi(@$t4+0x10)',
                 "dd poi(@$t4+0x10) L18"]
    t2 = cdb(p, cmds, out / "2_planner.txt")
    ids = []
    for l in t2.splitlines():
        m = re.match(r"^([0-9a-f`]{17})\s+((?:[0-9a-f]{8}\s*){1,4})$", l.strip())
        if m:
            ids += [x for x in m.group(2).split() if x != "00000000"]
    ids = list(dict.fromkeys(ids))[:48]
    # 3. each member id -> object (+0x10 must echo the id) -> +0x178 id -> object or the default
    cmds = [f'.printf "DEFAULT %p\\n", poi({DEFAULT})']
    for i in ids:
        cmds += [f"r $t0 = poi(poi(poi({UNITS})+0x20)+8+(0x{i}&0xffffff)*0x10)",
                 "r $t1 = dwo(@$t0+0x178)",
                 f"r $t2 = poi(poi(poi({ARMIES})+0x20)+8+(@$t1&0xffffff)*0x10)",
                 f'.printf "M {i} %p %x %x %p %x\\n", @$t0, dwo(@$t0+0x10), @$t1, @$t2, dwo(@$t2+0x10)',
                 "dq @$t2+0x30 L4"]
    t3 = cdb(p, cmds, out / "3_members.txt")
    lines = [f"thread {thread}, split frame SP 0x{sp:x}, home slot 0x{sp + HOME:x}"]
    lines += [l for l in t2.splitlines() if re.match(r"^(PLANNER|GROUPS|G0|G1|G2|GL2|GL1|GL) ", l)]
    lines += [l for l in t3.splitlines() if re.match(r"^(DEFAULT|M) ", l)]
    lines.append("M columns: member id, object, object's own id (must equal), +0x178 id, its object, that object's id")
    lines.append("release: " + (release(p) or "no leftover suspension"))
    (out / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:40]))


if __name__ == "__main__":
    main()
