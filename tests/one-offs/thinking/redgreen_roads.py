"""Red-green audit for roads.transplant_roads (patch day S7, 2026-11-17): revert each behaviour, expect red, restore.

python -I tests/one-offs/thinking/redgreen_roads.py   (from the repository root). The tests touch only tmp_path.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "ck3_save_migrator" / "roads.py"
MUTANTS = [
    ("g1 route links kept", "        body, n = _ROUTES.subn(b\"\", body)\n", "        n = 0\n"),
    ("g2 existing roads replaced", "    if _entries(target):\n", "    if False:\n"),
    ("g3 the BOM not stripped", '.removeprefix(b"\\xef\\xbb\\xbf")', ""),
    ("g4 keys cut at punctuation", '_KEY = rb"([^\\s={}#\\"]+)"', '_KEY = rb"(\\w+)"'),
    ("g5 undefined types carried", "        if defined is not None and key not in defined:\n", "        if False:\n"),
]
SEL = ["tests/test_roads.py", "-q", "-p", "no:cacheprovider"]

for name, old, new in MUTANTS:
    text = SRC.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{name}: anchor not unique ({text.count(old)})"
    try:
        SRC.write_text(text.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
        print(f"{name}: {'RED' if r.returncode else 'GREEN (survived)'} -- {r.stdout.strip().splitlines()[-1]}")
    finally:
        SRC.write_text(text, encoding="utf-8")
    assert SRC.read_text(encoding="utf-8") == text, f"{name}: restore failed"
r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
print("restored:", r.stdout.strip().splitlines()[-1])
