"""Red-green audit of the top-index shift's tests (0.5.0; copied from redgreen_v0_4_30.py, lists swapped).

Each mutant neutralises one behaviour and keeps every signature; the new tests run alone; the file is restored from
a backup and its sha256 checked before the next mutant.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_top_index_shift.py
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "ck3_save_migrator"
TESTS = ["tests/test_top_index_shift.py", "tests/test_step_findings.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    ("S1 nothing carried", "gamestate.py",
     "    if new is old:                                           # an empty pass can return the same object\n"
     "        return",
     "    if True:\n        return"),
    ("S2 no shift (old offsets kept)", "gamestate.py",
     "        return p + delta[bisect.bisect_right(ends, p)]      # every edit that ends at or before p",
     "        return p"),
    ("S3 an insert at a close does not move it", "gamestate.py",
     "        return p + delta[bisect.bisect_right(ends, p)]      # every edit that ends at or before p",
     "        return p + delta[bisect.bisect_left(ends, p)]"),
    ("S4 every text counts as well nested", "gamestate.py",
     "        if not (_well_nested(old[e.start:e.end]) and _well_nested(e.replacement)):\n            return None",
     "        if False:\n            return None"),
    ("S5 braces inside strings counted", "gamestate.py",
     "    for m in _BRACE_OR_STRING.finditer(text):\n        tok = m.group()",
     "    for m in re.finditer(rb'[{}]', text):\n        tok = m.group()"),
    ("S6 edits outside a section accepted", "gamestate.py",
     "        if i < 0 or not (blocks[i].open < e.start and e.end <= blocks[i].close):\n            return None",
     "        if i < 0:\n            return None"),
    ("S7 the check mode never raises", "gamestate.py",
     "        if walked != shifted:\n            raise GamestateError",
     "        if False:\n            raise GamestateError"),
    ("L1 SectionIndex walks again", "lint.py",
     "        if idx is not None:\n            self.top = {k.decode(): bs[0] for k, bs in idx.items()}",
     "        if False:\n            self.top = {k.decode(): bs[0] for k, bs in idx.items()}"),
    ("L2 the last block of a repeated key", "lint.py",
     "self.top = {k.decode(): bs[0] for k, bs in idx.items()}",
     "self.top = {k.decode(): bs[-1] for k, bs in idx.items()}"),
    ("L3 no walk when the shared index is None", "lint.py",
     "            self.top = {k.decode(): bs[0] for k, bs in idx.items()}\n            return",
     "            self.top = {k.decode(): bs[0] for k, bs in idx.items()}\n            return\n        return"),
    ("F1 the rule never takes its check's plan", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if False and hit is not None and hit[0] is save.gamestate and hit[1] == values:"),
    ("F2 a plan for other bytes is taken", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if hit is not None and hit[1] == values:"),
    ("F3 a plan with other values is taken", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if hit is not None and hit[0] is save.gamestate:"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_tests() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *TESTS],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    failed = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
    return r.returncode, "\n      ".join(failed) or r.stdout.strip().splitlines()[-1]


def main() -> int:
    backup = Path(tempfile.mkdtemp(prefix="redgreen_"))
    files = {n: PKG / n for n in ("gamestate.py", "lint.py", "patches/pack.py")}
    before = {n: sha(p) for n, p in files.items()}
    saved = {n: backup / n.replace("/", "__") for n in files}      # a flat backup folder: patches/pack.py too
    for n, p in files.items():
        shutil.copy2(p, saved[n])
    print(f"backup: {backup}")
    code, summary = run_tests()                     # known answer: all green before any mutant
    print(f"baseline: exit {code} -- {summary}")
    if code != 0:
        return 2
    try:
        for name, fname, old, new in MUTANTS:
            p = files[fname]
            text = p.read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
            p.write_text(text.replace(old, new), encoding="utf-8", newline="")
            code, summary = run_tests()
            shutil.copy2(saved[fname], p)
            assert sha(p) == before[fname], f"{name}: restore mismatch"
            print(f"{name}: {'RED' if code else 'green (survived)'}\n      {summary}")
    finally:
        for n, p in files.items():
            shutil.copy2(saved[n], p)
        ok = all(sha(p) == before[n] for n, p in files.items())
        print(f"restored, hashes match: {ok}")
    code, summary = run_tests()
    print(f"after: exit {code} -- {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
