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
         "tests/test_dangerous.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    # U1, 2026-11-09: patch format 2
    ("E1 update runs edits too", "patches/model.py",
     'return [p for p in (self.patches[i] for i in self.order) if p.role != "edit"]',
     "return [self.patches[i] for i in self.order]"),
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
     "source=where, folder=folder, from_disk=from_disk, role=role, params=params)",
     "source=where, folder=folder, from_disk=from_disk, params=params)"),
    ("E6 params allowed on a fix", "patches/model.py",
     '    if params and role != "edit":',
     '    if params and role == "nothing":'),
    ("E7 any param type", "patches/model.py",
     "        if t not in PARAM_TYPES:",
     "        if t is None:"),
    ("E8 params are not template values", "patches/model.py",
     "    context_fields = set(context_fields) | {name for name, _, _ in params}",
     "    context_fields = set(context_fields)"),
    ("E9 any kind value", "patches/model.py",
     '    if role not in ("fix", "edit"):',
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
    ("D7 a binary save not explained", "edit.py",
     "    except UnsupportedKindError as exc:\n        raise EditError",
     "    except KeyError as exc:\n        raise EditError"),
    ("D8 --force ignored", "edit.py",
     "    res = write_save(p.save, p.out, force=force)\n    entries = list(prior",
     "    res = write_save(p.save, p.out, force=False)\n    entries = list(prior"),
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
    ("L3 the input's ledger not carried", "edit.py",
     '    entries = list(prior["entries"]) if prior else []',
     "    entries = []"),
    ("L4 a newer ledger format read", "edit.py",
     '    if data.get("format") != LEDGER_FORMAT:',
     "    if False:"),
    ("L5 the output hash not recorded", "edit.py",
     '"input_sha256": in_sha, "sha256": out_sha,',
     '"input_sha256": in_sha, "sha256": in_sha,'),
    # U4, 2026-11-11: revert
    ("R1 a changed save reverted anyway", "edit.py",
     '    if entries[-1].get("sha256") != cur:',
     "    if False:"),
    ("R2 undo at the input offsets", "edit.py",
     '        undo = [Change(c["offset_out"], base64.b64decode(c["after"])',
     '        undo = [Change(c["offset"], base64.b64decode(c["after"])'),
    ("R3 revert all undoes only the last", "edit.py",
     '    elif arg == "all":\n        keep = 0',
     '    elif arg == "all":\n        keep = len(entries) - 1'),
    ("R4 the revert not recorded", "edit.py",
     "    p.steps, p.entries = steps, list(entries) + new",
     "    p.steps, p.entries = steps, list(entries) + new[:0]"),
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
    ("G5 edit's flag not carried to the plan", "cli.py",
     "        p.dangerous = True\n        say(MINIMAL, \"  --dangerous",
     "        pass\n        say(MINIMAL, \"  --dangerous"),
    ("L6 the input hash not recorded", "edit.py",
     '"input_sha256": in_sha, "sha256": out_sha,',
     '"input_sha256": "", "sha256": out_sha,'),
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
    files = {n: PKG / n for n in ("patches/model.py", "edit.py", "cli.py", "config.py", "plan.py")}
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
