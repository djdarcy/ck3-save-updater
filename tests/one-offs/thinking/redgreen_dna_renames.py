"""Red-green audit of tests/test_dna_renames.py: neutralise the rename behaviour in dna.py (API kept), one mutant at
a time, run the four tests, restore the file byte-exact. Synthetic layouts only.

Usage: python -I tests/one-offs/thinking/redgreen_dna_renames.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "ck3_save_migrator" / "dna.py"
MUTANTS = {
    "M1 build_plan ignores renames": ("renamed_to = {new: old for old, new in (renames or {}).items()",
                                      "renamed_to = {new: old for old, new in ({}).items()"),
    "M2 Setup never passes RENAMES": ('ren = RENAMES if "renames" in self.face_changes else None', "ren = None"),
    "M3 the new-name guard removed": ("if old in pos and new not in pos and old not in tnames}",
                                      "if old in pos and old not in tnames}"),
}


def main():
    original = SRC.read_bytes()
    h0 = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8")
    try:
        for name, (old, new) in MUTANTS.items():
            assert text.count(old) == 1, f"{name}: anchor not unique"
            SRC.write_text(text.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line",
                                "tests/test_dna_renames.py"], cwd=REPO, capture_output=True, text=True, timeout=300)
            print(f"{name}: {r.stdout.strip().splitlines()[-1]}")
            for ln in r.stdout.splitlines():
                if ln.startswith("FAILED"):
                    print("    ", ln[:150])
    finally:
        SRC.write_bytes(original)
    assert hashlib.sha256(SRC.read_bytes()).hexdigest() == h0, "RESTORE FAILED"
    print("restored byte-exact")


if __name__ == "__main__":
    main()
