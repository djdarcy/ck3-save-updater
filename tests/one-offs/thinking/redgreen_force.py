"""Red-green audit for reference-mod --force (djdarcy 2026-11-17): revert each behaviour, expect red, restore.

python -I tests/one-offs/thinking/redgreen_force.py   (from the repository root). The tests write only under tmp_path.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REFMOD = ROOT / "ck3_save_migrator" / "refmod.py"
MUTANTS = [
    ("r1 --force ignored", "    if existing and not replace:\n", "    if existing:\n"),
    ("r2 every mod taken as ours", "    unknown = [p for p in existing if not _written_by_us(p)]\n",
     "    unknown = []\n"),
    ("r3 no terminal: replaced anyway", "        if confirm is None:\n", "        if False:\n"),
    ("r4 the answer ignored", "        if not confirm(unknown):\n", "        if not (confirm(unknown) or True):\n"),
    ("r5 ours asked about too", "    unknown = [p for p in existing if not _written_by_us(p)]\n",
     "    unknown = list(existing)\n"),
]
SEL = ["tests/test_refmod.py", "-k", "replace", "-q", "-p", "no:cacheprovider"]

for name, old, new in MUTANTS:
    text = REFMOD.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{name}: anchor not unique"
    try:
        REFMOD.write_text(text.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
        print(f"{name}: {'RED' if r.returncode else 'GREEN (survived)'} -- {r.stdout.strip().splitlines()[-1]}")
    finally:
        REFMOD.write_text(text, encoding="utf-8")
    assert REFMOD.read_text(encoding="utf-8") == text, f"{name}: restore failed"
r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
print("restored:", r.stdout.strip().splitlines()[-1])
