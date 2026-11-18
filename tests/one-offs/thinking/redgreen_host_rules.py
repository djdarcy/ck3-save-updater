"""Red-green audit for host_rules (patch day S6 groundwork, 2026-11-17): revert each behaviour, expect red, restore.

python -I tests/one-offs/thinking/redgreen_host_rules.py   (from the repository root). The tests touch only tmp_path.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "ck3_save_migrator" / "host_rules.py"
MUTANTS = [
    ("h1 primary_building not a seed",
     '_list(body, "buildings") + re.findall(r"\\bprimary_building\\s*=\\s*" + _KEY, body)', '_list(body, "buildings")'),
    ("h2 no recursive read", 'sorted((game / "districts").rglob("*.txt"))', 'sorted((game / "districts").glob("*.txt"))'),
    ("h3 keys cut at punctuation", '_KEY = r"([^\\s={}#\\"]+)"', '_KEY = r"(\\w+)"'),
    ("h4 gated taken as open", "        open_ = [d for d in hosts if not d.gated]\n",
     "        open_ = list(hosts)\n"),
    ("h5 no next tiers", "                    if x in nxt:\n", "                    if False:\n"),
    ("h6 every district a regular one", 'else "regular" if f.name.startswith("regular") else "special")',
     'else "regular")'),
]
SEL = ["tests/test_host_rules.py", "-q", "-p", "no:cacheprovider"]

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
