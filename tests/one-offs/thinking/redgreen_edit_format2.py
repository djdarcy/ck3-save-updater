"""Red-green audit of the save editor's tests (0.5.x; copied from redgreen_top_index_shift.py, lists swapped).

Each mutant neutralises one behaviour and keeps every signature; the new tests run alone; the file is restored from
a backup and its sha256 checked before the next mutant.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_edit_format2.py
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
TESTS = ["tests/test_patch_format2.py", "tests/test_patches_format.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    # U1, 2026-11-09: patch format 2
    ("E1 update runs edits too", "patches/model.py",
     'return [p for p in (self.patches[i] for i in self.order) if p.role != "edit"]',
     "return [self.patches[i] for i in self.order]"),
    ("E2 format 2 not read", "patches/model.py",
     "FORMATS = (1, 2) ",
     "FORMATS = (1,)   "),
    ("E3 no 'update the tool' hint", "patches/model.py",
     '+ ("; update the tool" if f > max(FORMATS) else "")',
     '+ ""'),
    ("E4 kind/params allowed in format 1", "patches/model.py",
     '        if f in d and fmt < 2:',
     '        if f in d and fmt < 1:'),
    ("E5 the role is never read", "patches/model.py",
     "source=where, folder=folder, from_disk=from_disk, role=role, params=params)",
     "source=where, folder=folder, from_disk=from_disk, params=params)"),
    ("E6 params allowed on a fix", "patches/model.py",
     '    if params and role != "edit":',
     '    if params and role == "nothing":'),
    ("E7 any param type", "patches/model.py",
     "        if t not in PARAM_TYPES:",
     "        if t is None:"),
    ("E8 params are not template values", "patches/model.py",
     "    context_fields = set(context_fields) | {name for name, _, _ in params}",
     "    context_fields = set(context_fields)"),
    ("E9 any kind value", "patches/model.py",
     '    if role not in ("fix", "edit"):',
     '    if role is None:'),
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
    files = {n: PKG / n for n in ("patches/model.py",)}
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
