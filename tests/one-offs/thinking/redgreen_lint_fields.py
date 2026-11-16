"""RED-GREEN audit of S3 (carried-fields goal): do the tests in tests/test_lint_fields.py go red when the behaviour
each pins is reverted in ck3_save_migrator/lint.py? Each mutant edits that one file in place, runs only those tests,
and restores the original bytes (also on any error). Same pattern as redgreen_field_coverage.py.

Run: python -I tests/one-offs/thinking/redgreen_lint_fields.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "ck3_save_migrator" / "lint.py"

MUTANTS = {
    "R1 no tolerance for the game's own share": [(
        "    return lack > expected + 3 * expected ** 0.5", "    return True")],
    "R2 allow-list ignored": [(
        "            if key in FIELDS_ABSENT_ON_PURPOSE or key in FIELDS_FILLED_ON_LOAD:", "            if False:")],
    "R3 reference ignored": [(
        '    if reference is not None:\n        return "the reference save", reference, None',
        '    if False:\n        return "the reference save", reference, None')],
    "R4 meaning not appended": [(
        'gaps.append(what + (f" -- {FIELD_MEANING[key]}" if key in FIELD_MEANING else ""))', "gaps.append(what)")],
    "R5 no skipped note": [(
        'rep.skipped.append(f"carried fields: {name} ships', '(lambda s: None)(f"carried fields: {name} ships')],
    "R6 nothing-to-compare emptied": [(
        "    nothing = [p for p in K.database_paths(g, gi) if p not in witnessed]", "    nothing = []")],
    "R7 fields flag ignored": [(
        "    if fields:\n        check_reference_fields(g, rep, reference)",
        "    if True:\n        check_reference_fields(g, rep, reference)")],
}


def run() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_lint_fields.py"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
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
