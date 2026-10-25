"""Red-green audit: break one behaviour at a time in a temp copy of the repo, expect the suite to go red.

The real source is never mutated (a hard kill cannot leave a mutant behind).

Usage: python -I tests/one-offs/redgreen.py [savefile|gamestate|all]
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUITES = {
    "savefile": ("ck3_save_migrator/savefile.py", "tests/test_savefile.py", [
        ("meta_block_end ignores quoted strings",
         "        if c == 0x22:  # quoted string", "        if False:  # quoted string"),
        ("length field not recomputed after edits",
         "return self.header.render(len(meta)) + meta + buf.getvalue()",
         "return self.header.render(self.header.meta_len) + meta + buf.getvalue()"),
        ("no verbatim no-op path (always re-deflate)",
         "        if self.can_reuse_input(recompress):\n            return self.header.raw",
         "        if False:\n            return self.header.raw"),
        ("reuse check ignores a changed gamestate",
         "return not self.changed and not recompress and", "return not recompress and"),
        ("in-place guard removed",
         "    if save.source is not None and out_p.resolve() == save.source.resolve():", "    if False:"),
        ("disk re-read verification skipped",
         "        verify_bytes(tmp.read_bytes(), expected)   # what reached the disk",
         "        pass  # verify_bytes(tmp.read_bytes(), expected)   # what reached the disk"),
        ("replace not retried when the file is held",
         "    for attempt in range(REPLACE_ATTEMPTS):", "    for attempt in range(1):"),
        ("no pause between replace attempts",
         "            time.sleep(REPLACE_DELAY)", "            pass"),
        ("replace failure swallowed after the last attempt",
         "            if attempt == REPLACE_ATTEMPTS - 1:\n                raise",
         "            if attempt == REPLACE_ATTEMPTS - 1:\n                return"),
        ("replace failure re-raised as a different error",
         "            if attempt == REPLACE_ATTEMPTS - 1:\n                raise",
         "            if attempt == REPLACE_ATTEMPTS - 1:\n                raise OSError('gave up')"),
        ("meta derived from the stale plaintext copy",
         "        meta = self.derived_meta()\n        buf", "        meta = self.meta\n        buf"),
    ]),
    "gamestate": ("ck3_save_migrator/gamestate.py", "tests/test_gamestate.py", [
        ("brace scan ignores quoted strings",
         "_BRACE_OR_STRING = re.compile(rb'[{}]|\"(?:[^\"\\\\]|\\\\.)*\"')",
         "_BRACE_OR_STRING = re.compile(rb'[{}]')"),
        ("brace scan ignores backslash escapes",
         "_BRACE_OR_STRING = re.compile(rb'[{}]|\"(?:[^\"\\\\]|\\\\.)*\"')",
         "_BRACE_OR_STRING = re.compile(rb'[{}]|\"[^\"]*\"')"),
        ("tokenizer ignores backslash escapes",
         "_TOKEN = re.compile(rb'\"(?:[^\"\\\\]|\\\\.)*\"|",
         "_TOKEN = re.compile(rb'\"[^\"]*\"|"),
        ("entries include nested blocks (no depth-0 guard)",
         "            depth -= 1\n            if depth == 0:\n                key, key_start",
         "            depth -= 1\n            if depth <= 1:\n                key, key_start"),
        ("top-level lookup not anchored at column 0",
         "re.finditer(rb\"(?m)^\" + re.escape(k)", "re.finditer(rb\"(?m)\" + re.escape(k)"),
        ("block key never found (all anonymous)",
         "    if i < floor or data[i] != 0x3D:  # \"=\"", "    if True:  # \"=\""),
        ("deletion does not take the whole line",
         "        return line_start, (line_end + 1 if nl >= 0 else line_end)", "        return start, end"),
        ("deletion leaves trailing tabs on a shared line",
         "        while j < line_end and data[j] in b\" \\t\":\n            j += 1",
         "        while False:\n            j += 1"),
        ("rename replaces key and value",
         "self.add(Edit(c.key_start, c.key_end, n, rule, note))",
         "self.add(Edit(c.key_start, c.value_end, n, rule, note))"),
        ("insert 'end' lands at the start",
         "            at = block.close", "            at = block.open + 1"),
        ("overlap check disabled",
         "            if prev is not None and e.start < prev.end:", "            if False:"),
        ("edits applied unsorted",
         "        eds = sorted(self.edits, key=lambda e: (e.start, e.end))", "        eds = list(self.edits)"),
        ("empty key not recognised",
         "        if t == b\"=\":                                   # \"=value\" with an empty key",
         "        if False:"),
        ("rgb { } value not joined to its key",
         "        elif vt in _VALUE_PREFIXES and", "        elif False and"),
        ("edit counter not incremented",
         "        self.count(edit.rule).edited += 1", "        self.count(edit.rule)"),
        ("child_at matches any child containing the position",
         "            if c.key_start == pos:\n                return block, c",
         "            if c.start <= pos < c.end and c.block is None:\n                return block, c"),
        ("child_at misses an entry's own key",
         "                if pending[k] == e.start and e.key is not None:     # the entry's own key",
         "                if False:     # the entry's own key"),
        ("child_at stops descending into nested blocks",
         "            if c.block is not None and c.block.open < pos < c.block.close:\n                return descend(c.block, pos)",
         "            if False:\n                return descend(c.block, pos)"),
    ]),
    "rules": ("ck3_save_migrator/rules/to_1_20.py", "tests/test_rules.py", [
        ("R1 deletes nothing",
         'p.delete_key(d, to.block, "converging", rule.name)', 'p.delete_key(d, to.block, "converging_x", rule.name)'),
        ("R2 does not truncate",
         "new = b'\"' + base64.b64encode(bits[:TARGET_FLAG_BYTES]) + b'\"'",
         "new = b'\"' + base64.b64encode(bits) + b'\"'"),
        ("R2 truncates lossy values too",
         "                    if any(bits[TARGET_FLAG_BYTES:]):", "                    if False:"),
        ("R3 wrong child order",
         'TITLE_NAME_KEYS = (b"name", b"article", b"adj", b"pre")',
         'TITLE_NAME_KEYS = (b"name", b"adj", b"article", b"pre")'),
        ("R3 block inserted before coat_of_arms_id",
         "            at = len(d) if nl < 0 else nl + 1", "            at = line_start"),
        ("R3 keeps the inline originals",
         "        for c in names.values():\n            s, e = gs.removal_span(d, c.start, c.end)\n            p.add(",
         "        for c in []:\n            s, e = gs.removal_span(d, c.start, c.end)\n            p.add("),
        ("R4 removes nothing",
         "d[v.start:v.end] == b'\"\"'", "d[v.start:v.end] == b'\"x\"'"),
        ("R4 skips the top-level copy",
         '    blocks += [("top-level", b) for b in gs.find_sections(d, "game_rules")]', "    pass"),
        ("R5 removes nothing",
         "        if child.key != b\"\":\n            continue",
         "        if True:\n            continue"),
        ("R6 does not skip dynamic titles",
         '        if key.startswith("x_") or key in defined:', "        if key in defined:"),
        ("R6 ignores the game's conversion table",
         "        if key in conv:", "        if False:"),
        ("R6 reads commented-out definitions",
         '        txt = re.sub(rb"#[^\\n]*", b"", f.read_bytes())', "        txt = f.read_bytes()"),
        ("R7 always sets portraits_version",
         "    if ctx.portraits_version is not None:", "    if True:"),
        ("R7 off by default",
         '"set meta_data version/save_game_version to the target", r7_version_bump)',
         '"set meta_data version/save_game_version to the target", r7_version_bump, default=False)'),
    ]),
    "religion": ("ck3_save_migrator/rules/religion_1_20.py", "tests/test_religion.py", [
        ("R9 catholic override back (option B undone)",
         'TEMPLATE_TO_RITE = {\n    "coptic"', 'TEMPLATE_TO_RITE = {\n    "catholic": "roman_rite",\n    "coptic"'),
        ("R9 no head carry",
         "        if not head or head == NONE.decode() or fid is None or fid not in faiths_db:\n            continue",
         "        if True:\n            continue"),
        ("R9 head conflict not reported",
         "            if assigned[fid] != head:\n                head_conflicts.append",
         "            if False:\n                head_conflicts.append"),
        ("R9 variables not remapped",
         'p.add(gs.Edit(m.start(3), m.end(3), new.encode(), rule.name, f"variable {kind}"))', "pass"),
        ("R9 living explicit counts not kept",
         '"living_explicit_by_rite": dict(living_by_rite)', '"living_explicit_by_rite": {}'),
        ("R10 holy site without a faiths list skipped",
         '_insert_before_close(g, h, b"\\t\\t\\tfaiths={ " + str(fid).encode() + b" }\\n", p, rule.name,',
         'None and _insert_before_close(g, h, b"\\t\\t\\tfaiths={ " + str(fid).encode() + b" }\\n", p, rule.name,'),
        ("R10 fervor not carried",
         'fervor = _old_field(block, "fervor") or b"50"', 'fervor = b"50"'),
        ("R12 house head skipped",
         '        if hr and hr[0]:\n            rite, how = hr[0], "house head"',
         '        if False:\n            rite, how = hr[0], "house head"'),
        ("R12 employer fallback skipped",
         '        elif c["employer"] and (chars.get(c["employer"]) or {}).get("rite"):',
         '        elif False:'),
        ("R12 counties without a rite left alone",
         '        if b"rite" in kids:\n            continue', '        if True:\n            continue'),
        ("R12 dead characters counted as living",
         '        if c["section"] == "living":\n            inherited_by_rite', '        if True:\n            inherited_by_rite'),
        ("R10 founder never written",
         't3 + b"founder=" + founder + b"\\n"', 't3 + b"founder=" + NONE + b"\\n"'),
        ("R10 founder written without the liveness check",
         "founder = founder_id.encode() if founder_in else NONE", "founder = founder_id.encode()"),
        ("R10 founder looked up in living only",
         'for sec in ("living", "dead_unprunable"):', 'for sec in ("living",):'),
        ("R10 changes history not carried",
         'b"changes={"] + ([b"\\t" + changes] if changes else []) + [', 'b"changes={"] + [] + ['),
        ("R10 changes block ends at a brace inside a string",
         r'''_CHANGES = re.compile(rb'(?m)^\s*changes=\{((?:[^{}"]|"(?:[^"\\]|\\.)*")*)\}')''',
         r'''_CHANGES = re.compile(rb'(?m)^\s*changes=\{([^}]*)\}')'''),
        ("R10 origin not set",
         'b"origin=" + parent_faith.encode(),', 'b"origin=4294967295",'),
        ("R10 rite-shape history loss not reported",
         "            if n_changes:\n                lost.append", "            if False:\n                lost.append"),
        ("custom_faith_names counts every faith",
         '[f["name"] for _, f in sorted(faiths.items(), key=lambda kv: int(kv[0])) if f.get("name")]',
         '[f["name"] or "x" for _, f in sorted(faiths.items(), key=lambda kv: int(kv[0]))]'),
        ("R11 nested modifier blocks kept",
         'if child.key == b"modifier" and parent.key in (b"modifier", b"timed_modifier"):',
         'if False:'),
    ]),
    "lint": ("ck3_save_migrator/lint.py", "tests/test_lint.py", [
        ("unclosed braces not reported", "    if depth != 0:", "    if False:"),
        ("section index crashes on an unclosed section",
         "            except gs.GamestateError:       # an unclosed section: check_structure reports it; index the rest\n                break",
         "            except gs.GamestateError:       # an unclosed section: check_structure reports it; index the rest\n                raise"),
        ("characters without a rite not flagged",
         "        if rites:\n            no_rite +=", "        if False:\n            no_rite +="),
        ("character rite ids not checked", "                if rites and val not in rites:", "                if False:"),
        ("main rite ownership not checked", '        elif _val(rites[mr], b"faith") != fid:', "        elif False:"),
        ("title holders must be living (holy-order founders flagged)",
         "            if h and h.group(1) not in char_ids:", "            if h and h.group(1) not in living:"),
        ("inline title names next to title_name_data not flagged",
         '                if re.search(rb"\\n\\t(name|adj|pre|article)=", body):', "                if False:"),
        ("county rites not checked", "        if rites and (r is None or r not in rites):", "        if False:"),
        ("script variable faiths not checked",
         '(kind == b"faith" and ident not in faiths) or', "False or"),
        ("byte-order mark hides each file's first definition",
         '.removeprefix(b"\\xef\\xbb\\xbf")', ""),
        ("every DNA string counted", "if len(m.group(1)) != data.dna_length)", "if True)"),
        ("rejected tokens counted across the whole save",
         'n = len(re.findall(rb"[\\n\\t]" + key + rb"=", g[b.open:b.close])) if b is not None else 0',
         'n = len(re.findall(rb"[\\n\\t]" + key + rb"=", g))'),
        ("opinions not skipped",
         "if _NUMBER.fullmatch(val) or val in data.defined or skip[0] <= m.start() < skip[1]:",
         "if _NUMBER.fullmatch(val) or val in data.defined:"),
        ("bare type= values checked as references",
         "(g[m.start(2) - 1] != 0x22 or val in data.reference_types)", "(val in data.reference_types)"),
        ("game-rule settings checked against definitions instead of rule options",
         'known = data.rule_options if m.group(1) == b"settings" else data.defined', "known = data.defined"),
        ("defined on actions flagged", "if m.group(1) not in data.on_actions)", "if m.group(1) in data.on_actions)"),
        ("defined dynasty templates flagged", "if m.group(1) not in data.dynasty_templates]", "]"),
        ("dynamic x_ titles counted as dead", 'if not k.startswith(b"x_") and k.decode() not in data.title_keys',
         "if k.decode() not in data.title_keys"),
        ("converted titles counted as dead", "\n                and k.decode() not in data.title_conversion]", "]"),
        ("duplicate count equals the dead count", "rep.findings[-1].count = len(dead) - 1",
         "rep.findings[-1].count = len(dead)"),
        ("cultures the save has listed as missing", "data.culture_refs & data.cultures) if c not in have)",
         "data.culture_refs & data.cultures))"),
        ("missing mods dropped from stats", '            rep.stats["mods_not_installed"] = list(data.mods_missing)',
         "            pass"),
        ("game data report names kinds, not what was read",
         'rep.stats["game_data"] = list(data.source_paths or data.sources)', 'rep.stats["game_data"] = list(data.sources)'),
    ]),
    "cli-lint": ("ck3_save_migrator/cli.py", "tests/test_lint.py", [
        ("lint errors do not change the exit code",
         "    if lint_errors:\n        eprint", "    if False:\n        eprint"),
        ("--no-lint ignored", "        if args.no_lint:\n            return None", "        if False:\n            return None"),
        ("no lint report beside the output", "        if not result.dry_run:\n            lint_path",
         "        if False:\n            lint_path"),
        ("CK3_GAME_DIR=none not honoured", '        if given.lower() == "none":\n            return None',
         '        if False:\n            return None'),
        ("migrate --lint-mods none still reads the save's mods",
         'if args.lint_mods == "save" else ([], [])', "if True else ([], [])"),
        ("lint --mods none still reads the save's mods",
         'if getattr(args, "mods", "save") == "save" else ([], [])', "if True else ([], [])"),
        ("a named folder that is not a game folder falls back to discovery",
         "        raise FileNotFoundError(f\"{source} {given} is not the game's 'game' folder \"",
         "        return None\n        raise FileNotFoundError(f\"{source} {given} is not the game's 'game' folder \""),
        ("missing mods not printed", "    if missing:\n        print(f\"{indent}  {len(missing)} mod(s)",
         "    if False:\n        print(f\"{indent}  {len(missing)} mod(s)"),
    ]),
    "cli": ("ck3_save_migrator/cli.py", "tests/test_religion.py", [
        ("branches even without a custom faith (two identical outputs)",
         "branch = may_branch and bool(custom_faith_names(save.gamestate))", "branch = may_branch"),
        ("existing output only refused at write time (after the rules)",
         "_check_paths(args, outputs(branch), existence=True)", "_check_paths(args, outputs(branch), existence=False)"),
        ("in-place only refused at write time",
         "        if out.resolve() == src:\n            raise InPlaceError", "        if False:\n            raise InPlaceError"),
        ("missing output folder not checked",
         '            if not (folder if str(folder) else Path(".")).is_dir():', "            if False:"),
        ("report folder not checked",
         '+ ([Path(report).parent] if report else [])', "+ []"),
    ]),
}


def run(copy: Path, test: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:asyncio", "-x", test],
                       cwd=copy, capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if l.strip()][-1:] or ["?"]
    return r.returncode, tail[0]


def audit(name: str) -> int:
    module, test, mutants = SUITES[name]
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "repo"
        shutil.copytree(ROOT / "ck3_save_migrator", copy / "ck3_save_migrator")
        shutil.copytree(ROOT / "tests", copy / "tests", ignore=shutil.ignore_patterns("one-offs", "__pycache__"))
        shutil.copy2(ROOT / "pyproject.toml", copy / "pyproject.toml")
        target = copy / module
        pristine = target.read_text(encoding="utf-8")
        rc, tail = run(copy, test)
        print(f"== {name}: baseline rc={rc}  {tail}")
        if rc != 0:
            return 1
        for label, old, new in mutants:
            if old not in pristine:
                print(f"  ANCHOR MISSING     : {label}")
                bad += 1
                continue
            target.write_text(pristine.replace(old, new, 1), encoding="utf-8")
            rc, tail = run(copy, test)
            verdict = "RED (caught)" if rc != 0 else "GREEN (MISSED)"
            bad += rc == 0
            print(f"  {verdict:19}: {label}  -- {tail}")
            target.write_text(pristine, encoding="utf-8")
    print(f"  {'all mutants caught' if not bad else f'{bad} mutant(s) not caught'}")
    return bad


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = list(SUITES) if which == "all" else [which]
    return 1 if sum(audit(n) for n in names) else 0


if __name__ == "__main__":
    sys.exit(main())
