"""Red-green audit of tests/test_edit_doctrines.py against builtin_edits.set_doctrines/_rewrite and faith_rules (S4).

Same shape as redgreen_set_faith.py (S3), with the source file named per revert. Each revert neutralises one
behaviour (signatures kept), runs only the new tests, and restores the file in a finally. The edit writes only under
pytest's tmp_path and reads a fake game folder there, so a reverted guard cannot reach outside it.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_doctrines.py
"""
import pathlib
import subprocess
import sys

EDITS = "ck3_save_migrator/builtin_edits.py"
RULES = "ck3_save_migrator/faith_rules.py"
TESTS = "tests/test_edit_doctrines.py"
REVERTS = {
    "a a doctrine replaces its group's": (EDITS, "            for c in current:\n                replaced[c] = k",
                                          "            for c in []:\n                replaced[c] = k"),
    "b a choosable group left empty": (EDITS, "if rules.group_must_be_filled(grp):", "if False:"),
    "c special categories optional": (RULES, 'OPTIONAL_CATEGORIES = {"special", "not_creatable"}',
                                      "OPTIONAL_CATEGORIES = set()"),
    "d doctrines every faith carries": (EDITS, "for k in sorted(removed & locked):", "for k in sorted(set()):"),
    "e the tenet cap": (EDITS, "if len(final_tenets) != rules.tenets_cap:", "if False:"),
    "f one of a unique set": (EDITS, "if len(both) > 1:", "if False:"),
    "g a tenet closed to the religion": (EDITS, "if t and tag in t.closed_to:", "if False:"),
    "h a key the game does not define": (EDITS, "if k not in rules.doctrines and k not in rules.tenets:", "if False:"),
    "i the main rite kept in step": (EDITS, 'changes += _rewrite(g, rlines, replaced, removed, adds, b"\\t\\t\\t\\t")',
                                     "changes += []"),
    "j a tenet swap written in place": (EDITS, "        replaced[old] = new\n", "        pass\n"),
    "k --dangerous forces": (EDITS, 'if problems and not ctx.dangerous:\n        raise EditError("set-doctrines: "',
                             'if problems:\n        raise EditError("set-doctrines: "'),
    "l refused without the game's files": (EDITS, 'if ctx.game_dir is None:\n        raise EditError("set-doctrines',
                                           'if False:\n        raise EditError("set-doctrines'),
}
originals = {f: pathlib.Path(f).read_bytes() for f in (EDITS, RULES)}
for name, (src, old, new) in REVERTS.items():
    text = originals[src].decode("utf-8")
    assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
    try:
        first, *rest = new.split("\n", 1)          # the marker ends the first line, never inside a string
        marked = first + "  # REDGREEN-MUTANT" + ("\n" + rest[0] if rest else "")
        pathlib.Path(src).write_bytes(text.replace(old, marked, 1).encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-rf",
                            TESTS], capture_output=True, text=True, timeout=300)
        failed = [ln.split("::")[-1][:90] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"{name}: {r.stdout.strip().splitlines()[-1]}")
        for f in failed:
            print(f"    red: {f}")
    finally:
        pathlib.Path(src).write_bytes(originals[src])
for f, b in originals.items():
    print("restored:", f, pathlib.Path(f).read_bytes() == b, "| marker:", b"REDGREEN-MUTANT" in pathlib.Path(f).read_bytes())
