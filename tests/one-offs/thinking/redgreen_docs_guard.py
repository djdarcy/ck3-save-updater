"""Red-green audit of tests/test_docs_guard.py: neutralise one behaviour of docs_guard.py at a time (API kept), run
the five tests, restore the file byte-exact. The tests use tmp_path only (docs and backups passed explicitly).

Usage: python -I tests/one-offs/thinking/redgreen_docs_guard.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "tests" / "one-offs" / "docs_guard.py"
MUTANTS = {
    "M1 protected change not compared": ('if cur["size"] != m["size"] or sha256(docs / rel) != m["sha256"]:', "if False:"),
    "M2 restore does not copy back": ('shutil.copy2(backup / "files" / rel, docs / rel)', "pass"),
    "M3 new protected file deleted, not moved": ("shutil.move(str(docs / rel), str(moved))", "(docs / rel).unlink()"),
    "M4 any new save allowed": ('if cur["class"] == "saves" and Path(rel).name.startswith(ALLOWED_NEW_SAVE):',
                                'if cur["class"] == "saves":'),
    "M5 nothing ignored": ('IGNORED = ("logs", "crashes", "dumps", "exceptions", "cache", ".launcher-cache", '
                           '"shadercache", "pops_filestorage",\n           "account")', "IGNORED = ()"),
    "M6 save changes not seen": ('elif cur["size"] != m["size"] or cur["mtime"] != m["mtime"]:', "elif False:"),
    "M7 restore writes saves": ('if cls != "protected":', "if False:"),
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
                                "tests/test_docs_guard.py"], cwd=REPO, capture_output=True, text=True, timeout=120)
            fails = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED") or "AssertionError" in ln
                     or "Error" in ln and "tests/test_docs_guard.py" in ln]
            last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
            print(f"{name}: {last}")
            for ln in fails[:6]:
                print("    ", ln[:160])
    finally:
        SRC.write_bytes(original)
    assert hashlib.sha256(SRC.read_bytes()).hexdigest() == h0, "RESTORE FAILED"
    print("restored byte-exact")


if __name__ == "__main__":
    main()
