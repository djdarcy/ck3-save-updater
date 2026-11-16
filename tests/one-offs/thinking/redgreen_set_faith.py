"""Red-green audit of tests/test_edit_set_faith.py against builtin_edits.set_faith and _rite_label (S3, E12).

Copied from redgreen_eminent.py (S2); only the reverts and the test file differ.
Each revert neutralises one behaviour (signatures kept), runs only the new tests, and restores the file in a finally.
The edit writes only under pytest's tmp_path, so a reverted guard cannot reach outside it.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_set_faith.py
"""
import pathlib
import subprocess
import sys

SRC = pathlib.Path("ck3_save_migrator/builtin_edits.py")
TESTS = "tests/test_edit_set_faith.py"
REVERTS = {
    "a the dead refused without --dangerous": ("if not ctx.dangerous:\n            raise EditError(f\"set-faith: {cid}",
                                               "if False:\n            raise EditError(f\"set-faith: {cid}"),
    "b a faith means its main rite": ("faith = FL.find_faith(g, target, faiths)",
                                      "faith = FL.find_faith(g, \"no such faith\", faiths)"),
    "c succession noted only on a faith change": ("if old is None or old.faith != rite.faith:", "if True:"),
    "d already-follows writes nothing": ("if m.group(1).decode() == rite.id:", "if False:"),
    "e a dead id reaches the edit": ("if not (who.isdigit() and int(who) in ix.dead):", "if True:"),
    "f a custom rite named by its faith": (
        """return f"{(f.name or f.tag) if f else 'faith ' + str(r.faith)}'s own rite ({r.id})\"""",
        """return f"? ({r.id})\""""),
}
orig = SRC.read_bytes()
text = orig.decode("utf-8")
for name, (old, new) in REVERTS.items():
    assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
    try:
        SRC.write_bytes(text.replace(old, new + "  # REDGREEN-MUTANT").encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-rf",
                            TESTS], capture_output=True, text=True)
        failed = [ln.split("::")[-1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"{name}: {r.stdout.strip().splitlines()[-1]}")
        for f in failed:
            print(f"    red: {f}")
    finally:
        SRC.write_bytes(orig)
print("restored:", SRC.read_bytes() == orig, "| marker left:", b"REDGREEN-MUTANT" in SRC.read_bytes())
