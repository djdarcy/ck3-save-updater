"""Red-green audit for the multi-word names goal (2026-11-17__01-24-33): one REVERTS table per slice.

Copied from redgreen_doctrines.py (faith-edits S4): the source file named per revert, the marker at the end of the
first line. Each revert neutralises one behaviour (signatures kept), runs only the slice's tests, and restores the
file in a finally. The tests write only under pytest's tmp_path.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_names.py <slice>
"""
import pathlib
import subprocess
import sys

CLI = "ck3_save_migrator/cli.py"
NAMES = "ck3_save_migrator/names.py"
LOOKUP = "ck3_save_migrator/faith_lookup.py"
RULES = "ck3_save_migrator/faith_rules.py"
SLICES = {
    "s1": ("tests/test_cli_output_encoding.py", {
        "a main guards its streams": (CLI, "    safe_output()                                        # an accented",
                                      "    pass                                                 # an accented"),
        "b surrogateescape counts as unsafe": (NAMES,
                                               'in ("strict", "surrogateescape") and hasattr(s, "reconfigure"):',
                                               'in ("strict",) and hasattr(s, "reconfigure"):'),
        "c the '?' fallback": (NAMES, '            out.append("?")', "            out.append(c)"),
    }),
    "s3": ("tests/test_names.py", {
        "a commas come first": (NAMES, '    if "," in text:', "    if False:"),
        "b signs start items": (NAMES, "    if modifiers and any(w[0] in SIGNS for w in words):", "    if False:"),
        "c the sign is taken off": (NAMES, "        if modifiers and c[0] in SIGNS:", "        if False:"),
        "d two readings refused": (NAMES, "    if len(found) > 1:", "    if False:"),
        "e uncovered words named": (NAMES, "        missing = [w for k, w in enumerate(words) if k not in covered]",
                                    "        missing = []"),
        "f norm folds accents": (NAMES, '    return re.sub(r"[^a-z0-9]", "", fold_accents(text).lower())',
                                 '    return re.sub(r"[^a-z0-9]", "", text.lower())'),
        "g the qualifier split": (NAMES, '    if ":" in text:', "    if False:"),
        "h longest reads all words as one run": (NAMES, '        chunks = [" ".join(chunks)] if chunks else []',
                                                 "        chunks = chunks"),
    }),
    "s4": ("tests/test_display_names.py tests/test_faith_lookup.py", {
        "a holy sites by display name": (LOOKUP, '    shown = (lambda typ: book.display(f"holy_site_{typ}_name")) '
                                                 'if book else (lambda typ: None)', "    shown = lambda typ: None"),
        "b the preferred ids settle a shared name": (LOOKUP, "        if len(mine) == 1:", "        if False:"),
        "c references resolved": (NAMES, "        for _ in range(REF_DEPTH):", "        for _ in range(0):"),
        "d a miss says the game folder is needed": (LOOKUP,
                                                    '                       + ("" if book or not hint else '
                                                    'f" ({NO_GAME_HINT})"))', '                       + "")'),
        "e rites by display name": (LOOKUP, "    shown = (lambda r: book.display(r.rite_type) if r.rite_type else None) "
                                            "if book else (lambda r: None)", "    shown = lambda r: None"),
        "f a group by its display name": (RULES, '                  if norm(k) == g or (book and norm(book.display('
                                                 'f"{k}_name") or "") == g)}', "                  if norm(k) == g}"),
        "g tenets and doctrines by display name": (RULES, '    shown = (lambda k: book.display(f"{k}_name")) if book '
                                                          'else (lambda k: None)', "    shown = lambda k: None"),
        "h lookups fold accents": (LOOKUP, '    return norm(s or "")',
                                   '    return re.sub(r"[^a-z0-9]", "", (s or "").lower())'),
    }),
}
TESTS, REVERTS = SLICES[sys.argv[1] if len(sys.argv) > 1 else "s1"]
originals = {f: pathlib.Path(f).read_bytes() for f in {src for src, _o, _n in REVERTS.values()}}
for name, (src, old, new) in REVERTS.items():
    text = originals[src].decode("utf-8")
    assert text.count(old) == 1, f"{name}: anchor found {text.count(old)} times"
    try:
        first, *rest = new.split("\n", 1)          # the marker ends the first line, never inside a string
        marked = first + "  # REDGREEN-MUTANT" + ("\n" + rest[0] if rest else "")
        pathlib.Path(src).write_bytes(text.replace(old, marked, 1).encode("utf-8"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "-rf",
                            *TESTS.split()], capture_output=True, text=True, timeout=300)
        failed = [ln.split("::")[-1][:90] for ln in r.stdout.splitlines() if ln.startswith("FAILED")]
        print(f"{name}: {r.stdout.strip().splitlines()[-1]}")
        for f in failed:
            print(f"    red: {f}")
    finally:
        pathlib.Path(src).write_bytes(originals[src])
for f, b in originals.items():
    print("restored:", f, pathlib.Path(f).read_bytes() == b, "| marker:", b"REDGREEN-MUTANT" in pathlib.Path(f).read_bytes())
