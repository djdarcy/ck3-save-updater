"""Red-green audit for carry_1_21.carry_wonders (patch day S6, 2026-11-17): revert each behaviour, expect red, restore.

python -I tests/one-offs/thinking/redgreen_carry_1_21.py   (from the repository root). The tests touch only tmp_path.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "ck3_save_migrator" / "carry_1_21.py"
MUTANTS = [
    ("c1 great_building not read", "(?:special_building|duchy_capital_building|great_building)",
     "(?:special_building|duchy_capital_building)"),
    ("c2 duchy given a type line", '"duchy_capital_districts.txt": ("duchy_capital_district", False)',
     '"duchy_capital_districts.txt": ("duchy_capital_district", True)'),
    ("c3 a filled slot written again", '            if re.search(rb"\\b" + slot.encode() + rb"=\\d", hb):\n',
     "            if False:\n"),
    ("c4 the district's line not checked", "            if v.ok is False:\n", "            if False:\n"),
    ("c5 unmapped not reported", "                res.unmapped.append((pid, key, how))\n", "                pass\n"),
    # the real bug of the first run: special_building_type (the slot) read as a built wonder
    ("c6 a bare slot taken as built", "        if not built:\n            continue\n",
     "        built += [m.decode() for m in re.findall(rb'special_building_type=\"?([^\\s\"]+)', hb) "
     "if m.decode() not in built]\n        if not built:\n            continue\n"),
]
SEL = ["tests/test_carry_1_21.py", "-q", "-p", "no:cacheprovider"]

for name, old, new in MUTANTS:
    text = SRC.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{name}: anchor not unique ({text.count(old)})"
    try:
        SRC.write_text(text.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
        last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
        print(f"{name}: {'RED' if r.returncode else 'GREEN (survived)'} -- {last}")
    finally:
        SRC.write_text(text, encoding="utf-8")
    assert SRC.read_text(encoding="utf-8") == text, f"{name}: restore failed"
r = subprocess.run([sys.executable, "-m", "pytest", *SEL], cwd=ROOT, capture_output=True, text=True)
print("restored:", r.stdout.strip().splitlines()[-1])
