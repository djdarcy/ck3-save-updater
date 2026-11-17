"""Red-green audit for the frame-pack tests (patch day S4, 2026-11-17): revert each behaviour, expect red, restore.

python -I tests/one-offs/thinking/redgreen_frame.py   (from the repository root)
Each mutant edits one line of production code, runs the frame tests, and restores the file from memory AND checks
the restore by content; the tests reach no file outside tmp_path.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "ck3_save_migrator" / "plan.py"
MODEL = ROOT / "ck3_save_migrator" / "patches" / "model.py"
MUTANTS = [
    ("f1 a frame covers", PLAN, "        pack_rows.append(PackChoice(later.id, \"built in\", \"(inside the package)\", l_ok, l_why))",
     "        covered = covered or l_ok\n        pack_rows.append(PackChoice(later.id, \"built in\", \"(inside the package)\", l_ok, l_why))"),
    ("f2 the refusal does not name the frame", PLAN, "        if frames:\n", "        if False:\n"),
    ("f3 empty order refused again", MODEL, "    if not all(isinstance(x, str) for x in order):",
     "    if not order or not all(isinstance(x, str) for x in order):"),
]
SEL = ["tests/test_update.py", "-k", "frame", "-q", "-p", "no:cacheprovider"]

for name, path, old, new in MUTANTS:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{name}: anchor not unique"
    try:
        path.write_text(text.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
        last = r.stdout.strip().splitlines()[-1]
        print(f"{name}: {'RED' if r.returncode else 'GREEN (survived)'} -- {last}")
    finally:
        path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text, f"{name}: restore failed"
r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
print("restored:", r.stdout.strip().splitlines()[-1])
