"""Red-green audit for tests/test_savefile.py: break one behaviour at a time, expect red.

Works on a throwaway copy of the package + tests in a temp folder, so the real
source is never mutated (a hard kill cannot leave a mutant behind).

Usage: python -I tests/one-offs/redgreen_savefile.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MUTANTS = [
    ("meta_block_end ignores quoted strings",
     "        if c == 0x22:  # quoted string", "        if False:  # quoted string"),
    ("length field not recomputed after edits",
     "return self.header.render(len(meta)) + meta + buf.getvalue()",
     "return self.header.render(self.header.meta_len) + meta + buf.getvalue()"),
    ("no verbatim no-op path (always re-deflate)",
     "        if self.can_reuse_input(recompress):\n            return self.header.raw",
     "        if False:\n            return self.header.raw"),
    ("reuse check ignores a changed gamestate",
     "return not self.changed and not recompress and", "return not recompress and"),
    ("in-place guard removed",
     "    if save.source is not None and out_p.resolve() == save.source.resolve():",
     "    if False:"),
    ("disk re-read verification skipped",
     "        verify_bytes(tmp.read_bytes(), expected)   # what reached the disk",
     "        pass  # verify_bytes(tmp.read_bytes(), expected)   # what reached the disk"),
    ("meta derived from the stale plaintext copy instead of the gamestate",
     "        meta = self.derived_meta()\n        buf",
     "        meta = self.meta\n        buf"),
]


def run(copy: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:asyncio", "-x",
                        "tests/test_savefile.py"], cwd=copy, capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if l.strip()][-1:] or ["?"]
    return r.returncode, tail[0]


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "repo"
        shutil.copytree(ROOT / "ck3_save_migrator", copy / "ck3_save_migrator")
        shutil.copytree(ROOT / "tests", copy / "tests", ignore=shutil.ignore_patterns("one-offs", "__pycache__"))
        shutil.copy2(ROOT / "pyproject.toml", copy / "pyproject.toml")
        target = copy / "ck3_save_migrator" / "savefile.py"
        pristine = target.read_text(encoding="utf-8")
        rc, tail = run(copy)
        print(f"baseline           : rc={rc}  {tail}")
        if rc != 0:
            return 1
        for name, old, new in MUTANTS:
            if old not in pristine:
                print(f"ANCHOR MISSING     : {name}")
                bad += 1
                continue
            target.write_text(pristine.replace(old, new, 1), encoding="utf-8")
            rc, tail = run(copy)
            verdict = "RED (caught)" if rc != 0 else "GREEN (MISSED)"
            bad += rc == 0
            print(f"{verdict:19}: {name}  -- {tail}")
            target.write_text(pristine, encoding="utf-8")
    print("all mutants caught" if not bad else f"{bad} mutant(s) not caught")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
