"""Red-green audit of 0.4.30's 9 new tests (update --[no-]ask, the plan verdict cache).

Each mutant neutralises one behaviour and keeps every signature; the 9 tests run alone; the file is restored from a
backup and its sha256 checked before the next mutant. Run from the repo root: python -I tests/one-offs/thinking/redgreen_v0_4_30.py
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PKG = ROOT / "ck3_save_migrator"
TESTS = ["tests/test_update.py::test_update_asks_by_default_at_a_terminal_and_runs_on_a_yes",
         "tests/test_update.py::test_update_writes_nothing_without_a_yes",
         "tests/test_update.py::test_no_ask_never_asks_and_a_script_is_never_asked",
         "tests/test_update.py::test_ask_without_a_terminal_runs_nothing",
         "tests/test_plan_cache.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    ("M1 the ask step removed", "cli.py",
     "if (interactive() if ask is None else ask) and not args.dry_run and not confirm_run():",
     "if False and (interactive() if ask is None else ask) and not args.dry_run and not confirm_run():"),
    ("M2 no default ask at a terminal", "cli.py",
     "if (interactive() if ask is None else ask) and",
     "if (False if ask is None else ask) and"),
    ("M3 --no-ask ignored", "cli.py",
     "if (interactive() if ask is None else ask) and",
     "if (interactive() if ask in (None, False) else ask) and"),
    ("M4 no-terminal refusal removed", "cli.py",
     "    if not _tty(sys.stdin):\n        say(WARNING, \"--ask needs a terminal",
     "    if False:\n        say(WARNING, \"--ask needs a terminal"),
    ("M5 any answer is a yes", "cli.py",
     "return answer.strip().lower() in (\"y\", \"yes\")",
     "return True"),
    ("M6 reuse nothing", "plan.py",
     "if prior and prior.get(\"state\") == \"needed\":",
     "if False and prior and prior.get(\"state\") == \"needed\":"),
    ("M7 reuse any verdict", "plan.py",
     "if prior and prior.get(\"state\") == \"needed\":",
     "if prior:"),
    # first form, "plan_key(g, {} or {...})", was equivalent ({} is falsy, so the dict was still passed): redone here
    ("M8 the key ignores the inputs", "plancache.py",
     "\"inputs\": rest}, sort_keys=True",
     "\"inputs\": {}}, sort_keys=True"),
    ("M11 the key ignores the save", "plancache.py",
     "\"save\": hashlib.sha256(gamestate).hexdigest(),",
     "\"save\": \"\","),
    ("M12 the key ignores the code", "plancache.py",
     "\"code\": code_fingerprint(),",
     "\"code\": \"\","),
    ("M9 the switch ignored", "plan.py",
     "\"use_record\": use_record}) if plan_cache_on() else None",
     "\"use_record\": use_record}) if True else None"),
    ("M10 cache clear leaves the verdicts", "cli.py",
     "pfiles, psize = plancache.clear()",
     "pfiles, psize = 0, 0"),
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_tests() -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *TESTS],
                       cwd=ROOT, capture_output=True, text=True, timeout=900)
    failed = [ln for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
    return r.returncode, "\n      ".join(failed) or r.stdout.strip().splitlines()[-1]


def main() -> int:
    backup = Path(tempfile.mkdtemp(prefix="redgreen_"))
    files = {n: PKG / n for n in ("cli.py", "plan.py", "config.py", "plancache.py")}
    before = {n: sha(p) for n, p in files.items()}
    for n, p in files.items():
        shutil.copy2(p, backup / n)
    print(f"backup: {backup}")
    code, summary = run_tests()                     # known answer: all green before any mutant
    print(f"baseline: exit {code} -- {summary}")
    if code != 0:
        return 2
    try:
        for name, fname, old, new in MUTANTS:
            p = files[fname]
            text = p.read_text(encoding="utf-8")
            assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
            p.write_text(text.replace(old, new), encoding="utf-8", newline="")
            code, summary = run_tests()
            shutil.copy2(backup / fname, p)
            assert sha(p) == before[fname], f"{name}: restore mismatch"
            print(f"{name}: {'RED' if code else 'green (survived)'}\n      {summary}")
    finally:
        for n, p in files.items():
            shutil.copy2(backup / n, p)
        ok = all(sha(p) == before[n] for n, p in files.items())
        print(f"restored, hashes match: {ok}")
    code, summary = run_tests()
    print(f"after: exit {code} -- {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
