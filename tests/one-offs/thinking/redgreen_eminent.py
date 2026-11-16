"""Red-green audit of tests/test_edit_eminent.py against builtin_edits.set_eminent_holy_sites (S2, E11).

Each revert neutralises one behaviour (signatures kept), runs only the new tests, and restores the file in a finally.
The edit writes only under pytest's tmp_path, so a reverted guard cannot reach outside it.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_eminent.py
"""
import pathlib
import subprocess
import sys

SRC = pathlib.Path("ck3_save_migrator/builtin_edits.py")
REVERTS = {
    "a not-a-holy-site refusal": ("stray = [i for i in want if i not in faith.holy_sites]", "stray = []"),
    "b the 1-3 count rule": ("if not EMINENT_MIN <= len(set(want)) <= EMINENT_MAX:", "if False:"),
    "c the duplicate refusal": ("if len(set(want)) != len(want):", "if False:"),
    "d placed after holy_sites": ("change = Change(e.open + h.end(), b\"\", h.group(1) + new + h.group(2))",
                                  "change = Change(e.open + h.start(), b\"\", h.group(1) + new + h.group(2))"),
    "e --dangerous forces": ("if problems and not ctx.dangerous:", "if problems:"),
    "f already-set writes nothing": ("if want == faith.eminent:", "if False:"),
}
orig = SRC.read_bytes()
text = orig.decode("utf-8")
for name, (old, new) in REVERTS.items():
    assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
    try:
        SRC.write_bytes(text.replace(old, new + "  # REDGREEN-MUTANT").encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-rf",
                            "tests/test_edit_eminent.py"], capture_output=True, text=True)
        failed = [ln.split("::")[-1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"{name}: {r.stdout.strip().splitlines()[-1]}")
        for f in failed:
            print(f"    red: {f}")
    finally:
        SRC.write_bytes(orig)
print("restored:", SRC.read_bytes() == orig, "| marker left:", b"REDGREEN-MUTANT" in SRC.read_bytes())
