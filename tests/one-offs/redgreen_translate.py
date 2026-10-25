"""Red-green audit for R13 (translate.py, idschema.py): revert one behaviour at a time, run tests/test_translate.py,
expect red; restore; expect green at the end.

translate.py and idschema.py are new (untracked), so git cannot restore them: the originals are copied to a
backup folder first and restored in a finally block. The module under test writes no files, opens no network
and spawns nothing, so a mutated guard cannot reach anything outside the test's own bytes.

Usage: python -I tests/one-offs/redgreen_translate.py <backup dir>
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "ck3_save_migrator"
MUTANTS = [
    ("generation kept", "translate.py", "return (i & GEN) | ((i & LOW) + self.base)", "return (i & LOW) + self.base"),
    ("base above max", "translate.py", "m.base = m.save_max_index + 1", "m.base = m.save_max_index"),
    ("3 sections one space", "idschema.py",
     '"character": ("living", "dead_unprunable", "characters/dead_prunable"),', '"character": ("living",),'),
    ("overflow refused", "translate.py", "if top > LOW:", "if False:"),
    ("x_ titles never join", "translate.py", 'if not k.startswith(b"x_")', "if True"),
    ("culture join", "translate.py", 'join("culture", {rc[k]: sc[k] for k in rc.keys() & sc.keys()})',
     'join("culture", {})'),
    ("character join", "translate.py",
     'join("character", {rl[h]: sl[h] for h in rl.keys() & sl.keys()}, pruned_ok=True)',
     'join("character", {}, pruned_ok=True)'),
    ("pruned join allowed", "translate.py", "for h in rl.keys() & sl.keys()}, pruned_ok=True)",
     "for h in rl.keys() & sl.keys()}, pruned_ok=False)"),
    ("founding house join", "translate.py", "houses[r_id] = s_id", "pass"),
    ("traits by name", "translate.py", "trait_map[i] = pos[n]", "trait_map[i] = i"),
    ("none passes", "translate.py", "        if i == NONE:\n            return i\n", ""),
    ("typed reference", "translate.py", 'sp = S.TYPE_SPACE.get(typ or "")', "sp = S.PLAIN"),
    ("unlisted reported", "translate.py", "self.rep.unlisted[(self.kind, path)] += 1", "pass"),
    ("numeric keys", "translate.py",
     'self.put(ksp, c.key_start, c.key_end, int(c.key), (c.start, c.end), path + "#key")', "pass"),
    ("repeat counted once", "translate.py", "            if i not in seen:", "            if True:"),
    ("coat counter +1", "translate.py", "return max(self.save_coa_next_id or 0, top + 1)",
     "return max(self.save_coa_next_id or 0, top)"),
    ("own key translated", "translate.py",
     "st.put(sp, entry.start, entry.start + len(entry.key), int(entry.key), drop=None)", "pass"),
    ("pruned refs counted", "translate.py", "self.rep.to_pruned[space] += 1", "pass"),
    ("unknown types counted", "translate.py", "self.rep.unknown_types[typ] += 1", "pass"),
    ("ambiguous key refused", "translate.py", "        if k in out:\n            raise", "        if False:\n            raise"),
    ("identity spaces", "translate.py", "identity=sp in S.IDENTITY", "identity=False"),
    ("join targets unique", "translate.py", "if len(set(vals)) != len(vals):", "if False:"),
    ("key at depth 0 only", "translate.py", "body.count(b\"}\", 0, m.start()) == 1", "body.count(b\"}\", 0, m.start()) >= 1"),
    # the edge policy (Unit 2)
    ("keep removes", "translate.py",
     "if drop is not None and self.keep is not None and value != NONE and not self.keep(space, value, path):",
     "if False:"),
    ("typed drop takes the item", "translate.py", "anon or holder or whole, path)", "whole, path)"),
    ("drops beat edits", "translate.py", "if not any(ms <= s < me for ms, me in merged)", "if True"),
    ("dropped counted", "translate.py", "self.rep.dropped[(self.kind, path)] += 1", "pass"),
    # references() (Unit 2)
    ("references: typed", "translate.py", 'cls = S.TYPE_SPACE.get(typ or "")', "cls = None"),
    ("references: none skipped", "translate.py", "if not tok.isdigit() or int(tok) == NONE:", "if not tok.isdigit():"),
    # lint.check_ids (Unit 2)
    ("ids: slot collision", "lint.py", "if s in slots and slots[s] != i:", "if False:"),
    ("ids: identical repeat ok", "lint.py",
     "same = prev[0] == sec and _entry_text(g, prev[1]) == _entry_text(g, m.start())", "same = False"),
    ("ids: duplicate seen", "lint.py", "seen[i] = (sec, m.start())", "pass"),
    ("ids: wired into lint", "lint.py", "    check_ids(g, rep, idx)\n", ""),
    # keep sees the path (Unit 3)
    ("keep gets the path", "translate.py", "not self.keep(space, value, path)", "not self.keep(space, value, '')"),
    # the transplant engine and R14/R17 (Unit 3)
    ("seam appended", "transplant.py", "children[tm.join[int(m.group(1))]].append(tm.translate(t))", "pass"),
    ("seam list created", "transplant.py",
     'ep.add(gs.Edit(at, at, b"\\tde_jure_vassals={ " + ids + b" }\\n", "transplant", "seam"))', "pass"),
    ("no campaign links", "transplant.py",
     'if space == "title" and (path == "de_facto_liege" or path.startswith("de_jure_vassals")):', "if False:"),
    ("only output targets kept", "transplant.py", "return v in self.carry[space]", "return True"),
    ("joined never planned", "transplant.py", "ids = set(ids) - set(self.tr.spaces[space].join)", "ids = set(ids)"),
    ("insert at column 0", "transplant.py", "at = self.save.rfind(b\"\\n\", 0, sec.close) + 1", "at = sec.close"),
    ("coat counter written", "transplant.py",
     'ep.add(gs.Edit(c.value_start, c.value_end, str(new).encode(), "transplant", "coat next_id"))', "pass"),
    ("objects carried", "transplant.py", "if v in self.entries(CARRIED[rsp]):", "if False:"),
    ("R14 leaves x_ out", "rules/transplant_1_20.py", ' and not k.startswith("x_")', ""),
    ("R14 new provinces only", "rules/transplant_1_20.py", 'provinces = set(t.entries("provinces")) - save_provinces',
     'provinces = set(t.entries("provinces"))'),
    ("R17 brought along", "rules/__init__.py", '        chosen.add("R17")\n', "        pass\n"),
]
TESTS = {"translate.py": "tests/test_translate.py", "idschema.py": "tests/test_translate.py",
         "lint.py": "tests/test_lint.py", "transplant.py": "tests/test_transplant.py",
         "rules/transplant_1_20.py": "tests/test_transplant.py", "rules/__init__.py": "tests/test_rules.py"}


def run(test_file: str = "tests/test_translate.py tests/test_lint.py tests/test_transplant.py tests/test_rules.py") -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", *test_file.split(), "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, timeout=300)
    return r.returncode


def main():
    backup = Path(sys.argv[1])
    backup.mkdir(parents=True, exist_ok=True)
    originals = {}
    # bytes, not text: a text-mode write on Windows turns LF into CRLF (seen on the first run of this audit)
    for f in TESTS:
        (backup / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PKG / f, backup / f)
        originals[f] = (PKG / f).read_bytes()
    rows = []
    try:
        assert run() == 0, "suite is not green before the audit"
        for name, f, old, new in MUTANTS:
            src = originals[f]
            n = src.count(old.encode())
            if n != 1:
                rows.append((name, f"ANCHOR x{n}"))
                continue
            (PKG / f).write_bytes(src.replace(old.encode(), new.encode()))
            try:
                rows.append((name, "RED (anchor)" if run(TESTS[f]) != 0 else "green (guard: no test notices)"))
            finally:
                (PKG / f).write_bytes(src)
    finally:
        for f, src in originals.items():
            (PKG / f).write_bytes(src)
    final = run()
    for name, res in rows:
        print(f"  {name:24} {res}")
    print(f"restored; suite after: {'GREEN' if final == 0 else 'RED'}")


if __name__ == "__main__":
    main()
