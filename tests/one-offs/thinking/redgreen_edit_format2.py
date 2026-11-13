"""Red-green audit of the save editor's tests (0.5.x; copied from redgreen_top_index_shift.py, lists swapped).

Each mutant neutralises one behaviour and keeps every signature; the new tests run alone; the file is restored from
a backup and its sha256 checked before the next mutant.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_edit_format2.py
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
TESTS = ["tests/test_patch_format2.py", "tests/test_patches_format.py", "tests/test_edit_cli.py",
         "tests/test_edit_ledger.py", "tests/test_edit_revert.py", "tests/test_edit_inplace.py",
         "tests/test_dangerous.py", "tests/test_edit_ironman.py", "tests/test_characters.py",
         "tests/test_edit_set_sex.py", "tests/test_edit_list.py", "tests/test_edit_player_packs.py",
         "tests/test_edit_reshape.py", "tests/test_edit_events.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    # U1, 2026-11-09: patch format 2
    ('E1 update runs edits too', 'patches/model.py',
     'return [p for p in (self.patches[i] for i in self.order) if p.role == "fix"]',
     'return [self.patches[i] for i in self.order]'),
    ("E2 format 2 not read", "patches/model.py",
     "FORMATS = (1, 2) ",
     "FORMATS = (1,)   "),
    ("E3 no 'update the tool' hint", "patches/model.py",
     '+ ("; update the tool" if f > max(FORMATS) else "")',
     '+ ""'),
    ("E4 kind/params allowed in format 1", "patches/model.py",
     '        if f in d and fmt < 2:',
     '        if f in d and fmt < 1:'),
    ("E5 the role is never read", "patches/model.py",
     "source=where, folder=folder, from_disk=from_disk, role=role, params=params, help=help_text)",
     "source=where, folder=folder, from_disk=from_disk, params=params, help=help_text)"),
    ('E6 params allowed on a fix', 'patches/model.py',
     '    if params and role == "fix":',
     '    if params and role == "nothing":'),
    ("E7 any param type", "patches/model.py",
     "        if t not in PARAM_TYPES:",
     "        if t is None:"),
    ("E8 params are not template values", "patches/model.py",
     "    context_fields = set(context_fields) | {name for name, _, _ in params}",
     "    context_fields = set(context_fields)"),
    ('E9 any kind value', 'patches/model.py',
     '    if role not in ("fix", "edit", "view"):',
     '    if role is None:'),
    # U2, 2026-11-09: the front door
    ("D1 output not named <stem>__<edit>", "edit.py",
     'return save_path.with_name(f"{save_path.stem}__{edit_name}.ck3")',
     'return save_path.with_name(f"{save_path.stem}_{edit_name}.ck3")'),
    ("D2 a dry run writes", "cli.py",
     '        say(MINIMAL, "dry run: nothing written", "io")\n        return 0',
     '        say(MINIMAL, "dry run: nothing written", "io")'),
    ("D3 never asks", "cli.py",
     "    if not args.yes and interactive():\n        sys.stderr.write(f\"Write",
     "    if False:\n        sys.stderr.write(f\"Write"),
    ("D4 --yes ignored", "cli.py",
     "    if not args.yes and interactive():\n        sys.stderr.write(f\"Write",
     "    if interactive():\n        sys.stderr.write(f\"Write"),
    ("D5 named values not read", "edit.py",
     '        if t.startswith("--") and t[2:].replace("-", "_") in names:',
     '        if False and t.startswith("--"):'),
    ("D6 flags after the values not taken out", "cli.py",
     '        if t == "--dry-run":\n            args.dry_run = True',
     '        if t == "--never-a-flag":\n            args.dry_run = True'),
    ("D7 a binary save not explained", "edit.py",          # re-anchored for U7's reader table
     "    if reader is None:\n        raise EditError",
     "    if False:\n        raise EditError"),
    ('D8 --force ignored', 'edit.py',
     '    res = write_save(p.save, p.out, force=force)',
     '    res = write_save(p.save, p.out, force=False)'),
    ("D9 missing values not refused", "edit.py",
     "    if missing:\n        usage",
     "    if False:\n        usage"),
    # U3, 2026-11-11: the ledger
    ("L1 no ledger written", "edit.py",
     '\n    atomic_write(ledger_path(p.out), json.dumps(ledger, indent=1) + "\\n")',
     "\n    pass"),
    ("L2 output offsets not shifted", "edit.py",
     "        shift += len(c.after) - len(c.before)",
     "        shift += 0"),
    ("L3 the input's ledger not carried", 'edit.py',
     'apply_changes(ctx.gamestate, changes), list(led["entries"]) if led else [],',
     'apply_changes(ctx.gamestate, changes), [],'),
    ("L4 a newer ledger format read", "edit.py",
     '    if data.get("format") != LEDGER_FORMAT:',
     "    if False:"),
    ('L5 the output hash not recorded', 'edit.py',
     '    p.entries[-1]["sha256"] = res.sha256',
     '    p.entries[-1]["sha256"] = p.ctx.input_sha256'),
    # U4, 2026-11-11: revert
    ('R1 a changed save reverted anyway', 'edit.py',
     '    if entries[-1].get("sha256") != ctx.input_sha256:',
     '    if False:'),
    ("R2 undo at the input offsets", "edit.py",
     '        undo = [Change(c["offset_out"], base64.b64decode(c["after"])',
     '        undo = [Change(c["offset"], base64.b64decode(c["after"])'),
    ("R3 revert all undoes only the last", "edit.py",
     '    elif arg == "all":\n        keep = 0',
     '    elif arg == "all":\n        keep = len(entries) - 1'),
    ('R4 the revert not recorded', 'edit.py',
     'out or output_path(save_path, "revert"), g, list(entries), new)',
     'out or output_path(save_path, "revert"), g, list(entries), new[:0])'),
    ("R5 no ledger not explained", "edit.py",
     "    if not entries:\n        raise EditError(f\"{save_path.name} has no ledger",
     "    if False:\n        raise EditError(f\"{save_path.name} has no ledger"),
    ("R6 any entry number taken", "edit.py",
     "    elif arg.isdigit() and int(arg) < len(entries):",
     "    elif arg.isdigit():"),
    # U5, 2026-11-11: --in-place and the backup key
    ("B1 backups off by default", "config.py",
     '    return bool(read_config(path).get("backup", True))',
     '    return bool(read_config(path).get("backup", False))'),
    ("B2 --no-bak ignored", "cli.py",
     '    if getattr(args, "no_bak", False):\n        return False',
     '    if False:\n        return False'),
    ("B3 --bak ignored", "cli.py",
     '    if getattr(args, "bak", False):\n        return True',
     '    if False:\n        return True'),
    ("B4 a backup kept even when off", "cli.py",
     "    if not backup:\n        os.replace(tmp, save)",
     "    if False:\n        os.replace(tmp, save)"),
    ("B5 the ledger not moved to the save", "cli.py",
     '        atomic_write(E.ledger_path(save_path), json.dumps(led, indent=1) + "\\n")',
     "        pass"),
    ("B6 an existing backup overwritten", "cli.py",
     "    if args.in_place and backup and bak.exists() and not args.force:",
     "    if False:"),
    ("B7 a bad backup value read as true", "config.py",
     '    if not isinstance(data.get("backup", True), bool):',
     "    if False:"),
    ("B8 rewriting the config drops backup", "config.py",
     '    if "backup" in data:             # kept as written',
     '    if False:                        # kept as written'),
    # U6, 2026-11-13: --dangerous
    ("G1 the span never overridden", "plan.py",
     "    if dangerous and not ok and skip_why == NOT_SELECTED:",
     "    if False:"),
    ("G2 the plan does not say so", "plan.py",
     '        notes.append(f"--dangerous: {pack} runs outside its version span ({why}); lint checks the output")',
     "        pass"),
    ("G3 the record not marked", "plan.py",
     '        inputs["dangerous"] = True',
     "        pass"),
    ("G4 the ledger not marked", "edit.py",
     '        entry["dangerous"] = True',
     "        pass"),
    ("G5 edit's flag not carried to the plan", 'cli.py',
     'E.plan_edit(save_path, args.edit, values, out=out, dangerous=args.dangerous)',
     'E.plan_edit(save_path, args.edit, values, out=out, dangerous=False)'),
    # U7, 2026-11-13: the ironman flip and the reader table
    ("I1 meta_data not flipped", "builtin_edits.py",          # I1-I4 moved with the code in U9
     '    if m:\n        changes.append(Change(m.start(1), b"yes", b"no"))',
     '    if False:\n        changes.append(Change(m.start(1), b"yes", b"no"))'),
    ("I2 ironman_manager not flipped", "builtin_edits.py",
     "        if m2:",
     "        if False:"),
    ("I3 the manager search runs past its block", "builtin_edits.py",
     "close.start() if close else len(gamestate)",
     "len(gamestate)"),
    ("I4 CRLF lines not matched", "builtin_edits.py",
     'rb"(?m)^\\tironman=(yes)\\r?$"',
     'rb"(?m)^\\tironman=(yes)$"'),
    ("I5 the reader table ignored", "edit.py",
     "    reader = READERS.get(header.kind)",
     "    reader = {KIND_UNIFIED_TEXT: read_save}.get(header.kind)"),
    # U8, 2026-11-13: the character resolver
    ("C1 the dead's child lists not read", "characters.py",
     "        for space in (self.living, self.dead):",
     "        for space in (self.living,):"),
    ("C2 a mother taken for a father", "characters.py",
     "                slot = 1 if _FEMALE.search(body) else 0",
     "                slot = 0"),
    ("C3 particles not ignored", "characters.py",
     "        rest = [p for p in pieces[1:] if p.lower() not in PARTICLES]",
     "        rest = list(pieces[1:])"),
    ("C4 several matches taken", "characters.py",
     "    if len(found) == 1:",
     "    if found:"),
    ("C5 a past holder counted", "characters.py",
     '_HOLDER = re.compile(rb"(?m)^\\tholder=(\\d+)")',
     '_HOLDER = re.compile(rb"holder=(\\d+)")'),
    ("C6 an id finds the dead", "characters.py",
     "        e = self.living.get(cid)",
     "        e = self.living.get(cid) or self.dead.get(cid)"),
    ("C7 a house or title prefix not stripped", "characters.py",
     '            names.add(key.split("_", 1)[-1].lower())',
     "            pass"),
    ("C8 age ignores the birthday", "characters.py",
     " - ((d[1], d[2]) < (b[1], b[2]))",
     ""),
    ('C9 the editor does not resolve characters', 'edit.py',
     '                out[name] = resolve_character(ctx.gamestate, params[name], ctx.characters).id',
     '                out[name] = params[name]'),
    ("C10 a number not converted", "edit.py",
     "                out[name] = int(params[name])",
     "                out[name] = params[name]"),
    # U9, 2026-11-13: set-sex, the edits pack, help and since on an edit
    ("S1 to male removes nothing", "builtin_edits.py",
     '        return [Change(c.open + m.start(), m.group(0), b"")], what',
     "        return [], what"),
    ("S2 to female not placed after birth", "builtin_edits.py",
     '    at = c.open + (m.end() if m else body.index(b"\\n") + 1)',
     '    at = c.open + body.index(b"\\n") + 1'),
    ("S3 a CRLF save gets an LF line", "builtin_edits.py",
     '    newline = b"\\r\\n" if gamestate[at - 2:at] == b"\\r\\n" else b"\\n"',
     '    newline = b"\\n"'),
    ("S4 already that sex not refused", "builtin_edits.py",
     "    if c.female == female:",
     "    if False:"),
    ("S5 any word taken for a sex", "builtin_edits.py",
     "    if sex not in SEXES:",
     "    if False:"),
    ("H1 an edit's help not read", "patches/model.py",
     "role=role, params=params, help=help_text)",
     'role=role, params=params, help="")'),
    ('H2 help allowed on a fix', 'patches/model.py',
     '    if help_text and role == "fix":',
     '    if False:'),
    ('H3 since optional for a fix too', 'patches/model.py',
     '**({} if role == "fix" else {"default": ""})',
     'default=""'),
    ('H4 the edits pack not loaded', 'edit.py',
     '        for e in edits_from_pack(pack):',
     '        for e in ():'),
    # U10, 2026-11-13: edit --list and help <edit>
    ("T1 an edit not found by its id", "edit.py",
     "    return want in (e.name.lower(), e.id.lower() or None)",
     "    return want == e.name.lower()"),
    ("T2 revert not looked up", "edit.py",
     '    if want == "revert":\n        return REVERT',
     '    if False:\n        return REVERT'),
    ("T3 the ledger does not name the pack", "edit.py",
     '"pack": p.edit.pack,',
     '"pack": "builtin",'),
    ("T4 --list after the values ignored", "cli.py",
     '        elif t == "--list":\n            args.list = True',
     '        elif t == "--list":\n            args.list = False'),
    ("T5 the listing names no pack", "edit.py",
     '    rows = [(e.id or "-", e.name, e.pack, "ready", e.title)',
     '    rows = [(e.id or "-", e.name, "builtin", "ready", e.title)'),
    ("T6 help leaves the values out", "edit.py",
     "    for n, kind, text in e.params:",
     "    for n, kind, text in ():"),
    ("T7 help does not know edits", "cli.py",
     "    if an_edit is not None:",
     "    if False:"),
    # U11, 2026-11-13: a player's own edits. P1 and P8 let an untrusted pack's edit through the state check; the
    # safety test replaces the code importer with one that fails the test, so no pack code can load (rule 1b).
    ("P1 an untrusted pack not refused as such", "edit.py",
     '    if e.state in ("not trusted", "changed since trusted"):',
     "    if False:"),
    ("P2 any state runs", "edit.py",
     '    if e.state != "ready":',
     "    if False:"),
    ('P3 turned off ignored', 'edit.py',
     '        if p.id in off:',
     '        if False:'),
    ("P4 the pack's save span never checked", 'edit.py',
     '    if out:\n        if not dangerous:',
     '    if False:\n        if not dangerous:'),
    ("P5 --dangerous does not override the span", "edit.py",
     "        if not dangerous:",
     "        if True:"),
    ("P6 what --dangerous overrode not recorded", "edit.py",
     '            entry["dangerous_note"] = p.note',
     "            pass"),
    ("P7 a path's template not filled", "patches/engine.py",
     "    for p in spec.paths:                # a path may name a value too",
     "    for p in ():                        # a path may name a value too"),
    ("P8 a pack's trust state not read", 'edit.py',
     'state="ready" if up.state == "runs" else up.state, pack_vars=up.vars,',
     'state="ready", pack_vars=up.vars,'),
    ('P9 a built-in name can be taken', 'edit.py',
     '        if p.name.lower() in taken or p.id.lower() in taken:',
     '        if False:'),
    ("P10 a path's template not checked at load", "patches/model.py",
     "*where_values, *e.paths):",
     "*where_values):"),
    ("P11 disable does not find an edit", "cli.py",
     "            p = next((p for p in up.pack.patches.values() if t in (p.id.lower(), p.name.lower())), None)",
     "            p = next((p for p in up.pack.ordered() if t in (p.id.lower(), p.name.lower())), None)"),
    ("P12 the listing ignores the save's version", 'edit.py',
     '        out = outside(e, version, seed) if e.state == "ready" else None',
     '        out = None'),
    # U12b, 2026-11-13: the door reshaped (three defects; the context; views; one loader)
    ('N1 in place over a save that changed', 'cli.py',
     '    if args.in_place and sha256(save_path.read_bytes()) != p.ctx.input_sha256:',
     '    if False:'),
    ("N2 a pack's campaign ignored", 'edit.py',
     'if k == "campaign" or (k == "save" and version)}',
     'if (k == "save" and version)}'),
    ('N3 a failed swap goes on to move the ledgers', 'cli.py',
     '        if swap:                       # undone',
     '        if False:                      # undone'),
    ('N4 a view planned as an edit', 'cli.py',
     '    if found is not None and found.role == "view":',
     '    if False:'),
    ('N5 a view need not be code', 'patches/model.py',
     '    if role == "view" and "script" not in d:',
     '    if False:'),
    ('N6 a span held against an unknown version', 'edit.py',
     'if k == "campaign" or (k == "save" and version)}',
     'if k in ("campaign", "save")}'),
    ('N7 an unknown name lists built-ins only', 'edit.py',
     '        known = ", ".join(r[1] for r in listing() if r[1] != "revert") or "none yet"',
     '        known = ", ".join(sorted(BUILTIN)) or "none yet"'),
    ('N8 the context has no seed', 'edit.py',
     '        return m.group(1).decode() if m else None',
     '        return None'),
    ('N9 an edit run as a view', 'edit.py',
     '    if edit.role != "view":',
     '    if False:'),
    # U13-U15, 2026-11-13: queued events (the views, remove, reroll)
    ("V1 an event naming her among its targets not listed", "events.py",
     "            if names:",
     "            if False:"),
    ("V2 events not listed soonest first", "events.py",
     "    return sorted(out, key=lambda pair: (date_key(pair[0].date), pair[0].number))",
     "    return out"),
    ("V3 the blank line after a removed event left behind", "builtin_edits.py",
     "            end += len(blank)",
     "            end += 0"),
    ("V4 a reroll keeps the seed", "builtin_edits.py",
     "    seed = new_seed(e.seed)",
     "    seed = e.seed"),
    ("V5 any event number taken", "builtin_edits.py",
     "    if not 1 <= number <= len(events):",
     "    if False:"),
    ("V6 a target that is not a character counted", "events.py",
     r'_TARGET = re.compile(rb"(?m)^\t\t\t(\w+)=\{\s*type=char\s*identity=(\d+)")',
     r'_TARGET = re.compile(rb"(?m)^\t\t\t(\w+)=\{\s*type=\w+\s*identity=(\d+)")'),
    ("V7 a new seed past the game's range", "events.py",
     "    return (seed * 7 + 12345) % SEED_MODULUS",
     "    return seed * 7 + 12345"),
    ("V8 the seed's place taken inside the block, not the save", "events.py",
     "            (m.start() + seed.start(1), m.start() + seed.end(1)) if seed else None,",
     "            (seed.start(1), seed.end(1)) if seed else None,"),
    ("V9 the block's own newline not part of it", "events.py",
     '        end += 2 if g[end:end + 2] == b"\\r\\n" else 1 if g[end:end + 1] == b"\\n" else 0',
     "        end += 0"),
    ('L6 the input hash not recorded', 'edit.py',
     '    p.entries[0]["input_sha256"] = p.ctx.input_sha256',
     '    p.entries[0]["input_sha256"] = ""'),
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
    files = {n: PKG / n for n in ("patches/model.py", "edit.py", "cli.py", "config.py", "plan.py",
                                     "characters.py", "builtin_edits.py", "patches/engine.py", "events.py")}
    before = {n: sha(p) for n, p in files.items()}
    saved = {n: backup / n.replace("/", "__") for n in files}      # a flat backup folder: patches/pack.py too
    for n, p in files.items():
        shutil.copy2(p, saved[n])
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
            shutil.copy2(saved[fname], p)
            assert sha(p) == before[fname], f"{name}: restore mismatch"
            print(f"{name}: {'RED' if code else 'green (survived)'}\n      {summary}")
    finally:
        for n, p in files.items():
            shutil.copy2(saved[n], p)
        ok = all(sha(p) == before[n] for n, p in files.items())
        print(f"restored, hashes match: {ok}")
    code, summary = run_tests()
    print(f"after: exit {code} -- {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
