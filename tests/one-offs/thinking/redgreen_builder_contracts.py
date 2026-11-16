"""RED-GREEN audit of S4 unit 1 (carried-fields goal): do the new tests go red when the behaviour each pins is
reverted? Mutants span ck3_save_migrator/rules/religion_1_20.py and ck3_save_migrator/contracts.py; each edits one
file in place, runs only the new tests, and restores the original bytes (also on any error).

Run: python -I tests/one-offs/thinking/redgreen_builder_contracts.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REL = ROOT / "ck3_save_migrator" / "rules" / "religion_1_20.py"
CON = ROOT / "ck3_save_migrator" / "contracts.py"
TESTS = ["tests/test_builder_contracts.py", "tests/test_religion.py", "-k",
         "contract or eminent or faith_type or declared or allow"]

MUTANTS = {
    "B1 eminent ignores the origin (always the first site)": (REL, [(
        "    picked = [h for h in holy_idx if h.encode() in origin][:EMINENT_MAX]", "    picked = []")]),
    "B2 no cap of three": (REL, [(
        "if h.encode() in origin][:EMINENT_MAX]", "if h.encode() in origin]")]),
    "B3 eminent line not written": (REL, [(
        '[b"eminent_holy_sites={ " + b" ".join(x.encode() for x in eminent) + b" }"] if eminent', "[] if eminent")]),
    "B4 an empty faith_type counts as a type": (REL, [(
        "    return v if v and v != b'\"\"' else None", "    return v if v else None")]),
    "B5 eminent_holy_sites undeclared": (CON, [(
        '            "eminent_holy_sites": (DERIVED,', '            "eminent_holy_sites_x": (DERIVED,')]),
    "B6 derived fields join the allow-list": (CON, [(
        "            if status in (ABSENT, ON_LOAD):", "            if status in (ABSENT, ON_LOAD, DERIVED):")]),
    "B7 undeclared finds nothing": (CON, [(
        "    return sorted(set(baseline_fields) - declared)", "    return []")]),
}


def run() -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *TESTS],
                       cwd=ROOT, capture_output=True, text=True, timeout=600)
    fails = [ln.split("::")[-1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]
    return p.returncode, ", ".join(fails) or p.stdout.strip().splitlines()[-1]


originals = {REL: REL.read_bytes(), CON: CON.read_bytes()}
try:
    code, out = run()
    print(f"baseline: exit {code} {out}")
    for name, (target, subs) in MUTANTS.items():
        text = originals[target].decode("utf-8")
        nl = "\r\n" if "\r\n" in text else "\n"
        for old, new in subs:
            old, new = old.replace("\n", nl), new.replace("\n", nl)
            assert text.count(old) == 1, f"{name}: anchor not unique or missing: {old[:60]!r}"
            text = text.replace(old, new)
        target.write_bytes(text.encode("utf-8"))
        code, out = run()
        print(f"{name}: {'RED' if code else 'green (survived)'}  {out}")
        target.write_bytes(originals[target])
finally:
    for path, data in originals.items():
        path.write_bytes(data)
code, out = run()
print(f"restored: exit {code} {out}; sources identical: {all(p.read_bytes() == d for p, d in originals.items())}")
