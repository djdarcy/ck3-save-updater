"""Python 3.10 is supported (requires-python >= 3.10), and 3.10 has no ``tomllib``.

CONSEQUENCE: 9 (crash) -- a direct ``import tomllib`` fails at import time on 3.10. v0.6.34 shipped one in the district
carry's table loader, so R42 would have crashed for a player on 3.10, and the test that read the same table stopped
CI's 3.10 job at collection (run 44663465967, 2026-11-20), cancelling the other three.

The package reads TOML through ``ck3_save_migrator.patches.model.tomllib`` (tomllib, or tomli on 3.10); this test
holds every other module and test to it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "ck3_save_migrator" / "patches" / "model.py"


def test_no_direct_tomllib_import_outside_the_shared_reader():
    offenders = []
    # the package, and the test modules pytest collects (tests/one-offs are run by hand, never by CI)
    files = list((ROOT / "ck3_save_migrator").rglob("*.py")) + list((ROOT / "tests").glob("*.py"))
    for p in (f for f in files if f != SHARED):
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(import tomllib\b|from tomllib import)", line):
                offenders.append(f"{p.relative_to(ROOT)}:{n}")
    assert not offenders, "import tomllib directly (fails on Python 3.10); use patches.model.tomllib: " + ", ".join(offenders)
