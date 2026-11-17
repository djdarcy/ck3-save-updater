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
EDITS = "ck3_save_migrator/builtin_edits.py"
CHARS = "ck3_save_migrator/characters.py"
EDIT = "ck3_save_migrator/edit.py"
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
    "u0": ("tests/test_savefile.py", {    # the after-goal-pass goal, S1: the kind-00 reader
        "a kind 00 is read": ("ck3_save_migrator/savefile.py", "READ_ONLY_KINDS = {KIND_TEXT}", "READ_ONLY_KINDS = set()"),
        "b a read-only kind is never written": (
            "ck3_save_migrator/savefile.py", "        if self.header.kind in READ_ONLY_KINDS:\n            raise UnsupportedKindError",
            "        if False:\n            raise UnsupportedKindError"),
    }),
    "u1": ("tests/test_rules_doctrine_fill.py", {   # the after-goal-pass goal, S2: doctrine groups in R10
        "a the origin faith first": (
            "ck3_save_migrator/rules/religion_1_20.py",
            "        pick = sorted(k for k in origin_doctrines if k in rules.doctrines and rules.doctrines[k].group == grp)",
            "        pick = []"),
        "b the religion's default second": (
            "ck3_save_migrator/rules/religion_1_20.py",
            "            pick = sorted(k for k in defaults if k in rules.doctrines and rules.doctrines[k].group == grp)",
            "            pick = []"),
        "c a filled group is left alone": (
            "ck3_save_migrator/rules/religion_1_20.py",
            "    for grp in sorted(k for k in rules.group_category if rules.group_must_be_filled(k) and k not in groups_have):",
            "    for grp in sorted(k for k in rules.group_category if rules.group_must_be_filled(k)):"),
    }),
    "u2": ("tests/test_rules_head_determination.py", {   # the after-goal-pass goal, S3: R32
        "a the template's value is written": (
            "ck3_save_migrator/rules/to_1_20.py",
            '        found.append((at, e.key.decode(), tmpl, defs[tmpl]))',
            '        pass'),
        "b a culture with one is skipped": (
            "ck3_save_migrator/rules/to_1_20.py",
            '        if not (e.key and e.key.isdigit()) or re.search(rb"[\\s{]head_determination=", body):',
            '        if not (e.key and e.key.isdigit()):'),
        "b2 a field after tabs on one line counts": (
            "ck3_save_migrator/rules/to_1_20.py",
            '        if not (e.key and e.key.isdigit()) or re.search(rb"[\\s{]head_determination=", body):',
            '        if not (e.key and e.key.isdigit()) or re.search(rb"\\n\\t*head_determination=", body):'),
        "c a later root replaces an earlier one": (
            "ck3_save_migrator/rules/to_1_20.py",
            "                    out[m.group(1)] = hd.group(1)",
            "                    out.setdefault(m.group(1), hd.group(1))"),
    }),
    "u2l": ("tests/test_lint_fields.py tests/test_lint.py", {   # the after-goal-pass goal, S3: lint's lists
        "a a no-rule field says why": (
            "ck3_save_migrator/lint.py",
            '                gaps.append(what + "".join(f" -- {m[key]}" for m in (FIELD_MEANING, FIELDS_NO_RULE) if key in m))',
            '                gaps.append(what + "".join(f" -- {m[key]}" for m in (FIELD_MEANING,) if key in m))'),
        "b a dead character filed among the living is info": (
            "ck3_save_migrator/lint.py",
            "        (foreign_dead if c in filed_dead else foreign).extend(rows)",
            "        foreign.extend(rows)"),
        "c colored_emblem is the game's own shape": (
            "ck3_save_migrator/lint.py",
            '    ("coat_of_arms/coat_of_arms_manager_database", "colored_emblem"):',
            '    ("x", "colored_emblem"):'),
    }),
    "u4": ("tests/test_savefile.py", {   # the after-goal-pass goal, S5's finding: refuse a read-only save at once
        "a the header check refuses": (
            "ck3_save_migrator/savefile.py", "    if header.kind in READ_ONLY_KINDS:\n        raise UnsupportedKindError(f\"save header kind {header.kind:02x} ({KIND_NAMES[header.kind]}) is read only; \"",
            "    if False:\n        raise UnsupportedKindError(f\"save header kind {header.kind:02x} ({KIND_NAMES[header.kind]}) is read only; \""),
        "b main calls it for the writing commands": (
            "ck3_save_migrator/cli.py", "                refuse_read_only(args.save)          # a save it can never write: before minutes of planning",
            "                pass                                 # a save it can never write: before minutes of planning"),
    }),
    "u5": ("tests/test_refmod_polish.py", {   # the patch-day goal, S5: reference-mod polish
        "a the version reaches the descriptor": (
            "ck3_save_migrator/refmod.py", """            f'name="Ref Bookmark {b.date} (ck3update)"\\nsupported_version="{b.game_version}.*"\\n')""",
            """            f'name="Ref Bookmark {b.date} (ck3update)"\\nsupported_version="1.20.*"\\n')"""),
        "b the art is copied": (
            "ck3_save_migrator/refmod.py", "    for path, source in art(b, out, game_dir).items():",
            "    for path, source in {}.items():"),
        "c a bad version is refused": (
            "ck3_save_migrator/refmod.py", '    if not re.fullmatch(r"\\d+\\.\\d+", gv):', "    if False:"),
    }),
    "u3": ("tests/test_refmod_names.py", {   # the after-goal-pass goal, S4: reference-mod's ruler flags by name
        "a a name resolves to its key": (
            "ck3_save_migrator/refmod.py", "        if key != v:", "        if False:"),
        "b houses by prefix and name": (
            "ck3_save_migrator/refmod.py",
            '            tables["house"][key] = (key, name, f"{pre.strip()} {name}" if pre and name else None)',
            '            tables["house"][key] = (key, name)'),
        "c no game folder: names refused": (
            "ck3_save_migrator/refmod.py", "        if bad:", "        if False:"),
        "d the command resolves the flags": (
            "ck3_save_migrator/cli.py", "    given, resolved = resolve_names(game, given)",
            "    resolved = []"),
    }),
    "s5": ("tests/test_edit_eminent.py tests/test_edit_set_faith.py tests/test_edit_doctrines.py "
           "tests/test_characters.py tests/test_cli_output_encoding.py", {
        "a eminent: the faith's own sites settle a shared name": (
            EDITS, "            g, s, table, book=bk, prefer=faith.holy_sites))]",
            "            g, s, table, book=bk, prefer=None))]"),
        "b eminent: labels in display names": (
            EDITS, """    label = lambda ids: ", ".join(f"{FL.holy_site_name(table.get(i, '?'), bk)} ({i})" for i in ids) or "none\"""",
            """    label = lambda ids: ", ".join(f"{table.get(i, '?')} ({i})" for i in ids) or "none\""""),
        "c eminent: the game's names read": (EDITS, "    g, bk = ctx.gamestate, book(ctx.game_dir)",
                                             "    g, bk = ctx.gamestate, None"),
        "d set-faith: the game's names read": (EDITS, "    rites, faiths, bk = FL.rites(g), FL.faiths(g), ix.book",
                                               "    rites, faiths, bk = FL.rites(g), FL.faiths(g), None"),
        "e set-faith: the character shown": (EDITS, "        cid, entry, first = c.id, ix.living[c.id], ix.shown(c.first_name)",
                                             "        cid, entry, first = c.id, ix.living[c.id], c.first_name"),
        "f doctrines: signs read": (EDITS, '        items = parse_list(str(params["changes"]), modifiers=True)',
                                    '        items = parse_list(str(params["changes"]), modifiers=False)'),
        "g doctrines: display names resolved": (EDITS, "            key = faith_rules.find_belief(rules, it.text, bk)",
                                                "            key = faith_rules.find_belief(rules, it.text, None)"),
        "h doctrines: only a game key passes unresolved": (
            EDITS, '            if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", it.text):   # a game key has an underscore; a name',
            '            if not re.fullmatch(r"[\\w.\\-]+", it.text):'),
        "i doctrines: labels in display names": (
            EDITS, '    nm = lambda k: (bk.display(f"{k}_name") if bk else None) or k        # "Christian Syncretism", else the key',
            "    nm = lambda k: k"),
        "j characters: first names by display name": (CHARS, "        out = {norm(key), norm(self.shown(key))}",
                                                      "        out = {norm(key)}"),
        "k characters: multi-word narrowing": (
            CHARS, '            ok[i] = any(ok[j] and norm(" ".join(words[i:j])) in forms for j in range(i + 1, n + 1))',
            '            ok[i] = any(ok[j] and norm(" ".join(words[i:j])) in forms for j in range(i + 1, min(i + 2, n + 1)))'),
        "l characters: multi-word first names": (CHARS, "        for k in range(1, len(pieces) + 1):",
                                                 "        for k in range(1, 2):"),
        "m characters: described by display name": (
            CHARS, """        return (f"{c.id:>10}  {self.shown(c.first_name)} ({'F' if c.female else 'M'}, {age}, born {c.birth or '?'})  \"""",
            """        return (f"{c.id:>10}  {c.first_name} ({'F' if c.female else 'M'}, {age}, born {c.birth or '?'})  \""""),
        "n the editor passes the game's names": (
            EDIT, "        return CharacterIndex(self.gamestate, book=book(self.game_dir))     # the names the game shows, when found",
            "        return CharacterIndex(self.gamestate)"),
        "o ligatures fold": (
            NAMES, '    return "".join(c for c in unicodedata.normalize("NFKD", text.translate(_LIGATURES)) if not unicodedata.combining(c))',
            '    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))'),
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
