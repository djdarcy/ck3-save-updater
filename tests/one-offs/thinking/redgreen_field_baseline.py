"""RED-GREEN audit of S2 (carried-fields goal): do the tests in tests/test_field_baseline.py go red when the behaviour
each pins is reverted in ck3_save_migrator/baselines.py? Each mutant edits that one file in place, runs only those
tests, and restores the original bytes (also on any error). Same pattern as redgreen_field_coverage.py.

Run: python -I tests/one-offs/thinking/redgreen_field_baseline.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "ck3_save_migrator" / "baselines.py"

MUTANTS = {
    "M1 values leak (example ids written)": [(
        '        dbs[path] = {"entries": n,\n', '        dbs[path] = {"entries": n, "first": cov["first"],\n')],
    "M2 keys unsorted on dump": [(
        "json.dumps(baseline, indent=1, sort_keys=True)", "json.dumps(baseline, indent=1)")],
    "M3 version ignored on load": [(
        'joinpath("baselines", version, "fields.json")', 'joinpath("baselines", "1.20.1.2", "fields.json")')],
    "M4 empty share dropped in as_coverage": [(
        '"empty": round(e * n)', '"empty": 0')],
    "M5 wrong meta field": [(
        'save_versions(g[:65536])["version"]', 'save_versions(g[:65536])["save_game_version"]')],
}


def run() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_field_baseline.py"],
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
