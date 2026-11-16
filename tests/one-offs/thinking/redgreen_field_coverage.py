"""RED-GREEN audit of S1 (carried-fields goal): does each new field_coverage / coverage_gaps test go red when the
behaviour it pins is reverted? Each mutant edits ck3_save_migrator/_vendor/savediff/keys.py in place, runs only the new
tests, and restores the original bytes (also on any error). Read-write on that one file only; nothing else is touched.

Run: python -I tests/one-offs/thinking/redgreen_field_coverage.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "ck3_save_migrator" / "_vendor" / "savediff" / "keys.py"
SELECT = "field_coverage or coverage_gaps or database_paths"

MUTANTS = {
    "M1 empty counted as filled": [(
        '    if c.block is not None:\n        return not g[c.block.open + 1:c.block.close].strip()\n'
        '    return g[c.value_start:c.value_end] == b\'""\'',
        "    return False")],
    "M2 line-start reader (the old census)": [(
        '            for c in text.iter_children(g, *e.body):\n                if c.key:\n'
        '                    k = c.key.decode("utf-8", "replace")\n                    names.add(k)\n'
        '                    if not _is_empty(g, c):\n                        filled.add(k)',
        '            import re as _re\n'
        '            for m in _re.finditer(rb"(?m)^\\t*(\\w+)=(\\S*)", g[e.open + 1:e.close]):\n'
        '                k = m.group(1).decode()\n                names.add(k)\n'
        '                if m.group(2) not in (b\'""\', b"{"):\n                    filled.add(k)')],
    "M3 numeric keys only": [(
        "if e.key is None or e.key.isdigit()]", "if e.key is not None and e.key.isdigit()]")],
    "M4 siblings only (witness ignored)": [(
        '    for k, wf in witness["fields"].items():',
        '    witness, wn = ours, n\n    for k, wf in witness["fields"].items():')],
    "M5 empty if any writing is empty": [
        ("        filled: set = set()\n", "        filled: set = set()\n        poisoned: set = set()\n"),
        ("                    if not _is_empty(g, c):\n                        filled.add(k)",
         "                    if _is_empty(g, c):\n                        poisoned.add(k)\n"
         "                    else:\n                        filled.add(k)"),
        ("(eid, names, names - filled)", "(eid, names, (names - filled) | poisoned)")],
}
# M6 ("no empty-side guard") survived on 2026-11-16 because the guard was inert (an empty witness has no fields to
# loop over; with none of ours nothing is missing): the guard was removed from keys.py, and the test that checks an
# empty side gives no rows stays as a guard on that contract.


def run() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_savediff_keys.py",
                        "-k", SELECT], cwd=ROOT, capture_output=True, text=True, timeout=300)
    fails = [ln.split("::")[-1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]
    return p.returncode, ", ".join(fails) or p.stdout.strip().splitlines()[-1]


original = TARGET.read_bytes()
try:
    code, out = run()
    print(f"baseline: exit {code} {out}")
    for name, subs in MUTANTS.items():
        text = original.decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        for old, new in subs:
            old, new = old.replace("\n", nl), new.replace("\n", nl)
            assert text.count(old) == 1, f"{name}: anchor not unique or missing: {old[:60]!r}"
            text = text.replace(old, new)
        TARGET.write_bytes(text.encode("utf-8"))
        code, out = run()
        print(f"{name}: {'RED' if code else 'green (survived)'}  {out}")
        TARGET.write_bytes(original)
finally:
    TARGET.write_bytes(original)
code, out = run()
print(f"restored: exit {code} {out}; source identical: {TARGET.read_bytes() == original}")
