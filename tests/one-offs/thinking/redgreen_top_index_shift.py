"""Red-green audit of the top-index shift's tests (0.5.0; copied from redgreen_v0_4_30.py, lists swapped).

Each mutant neutralises one behaviour and keeps every signature; the new tests run alone; the file is restored from
a backup and its sha256 checked before the next mutant.
Run from the repo root: python -I tests/one-offs/thinking/redgreen_top_index_shift.py
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
TESTS = ["tests/test_top_index_shift.py", "tests/test_step_findings.py", "tests/test_patches_failures.py",
         "tests/test_deadtitles.py", "tests/test_dna.py", "tests/test_update.py", "tests/test_requirements.py"]

# (name, file, old, new): old must occur exactly once
MUTANTS = [
    ("S1 nothing carried", "gamestate.py",
     "    if new is old:                                           # an empty pass can return the same object\n"
     "        return",
     "    if True:\n        return"),
    ("S2 no shift (old offsets kept)", "gamestate.py",
     "        return p + delta[bisect.bisect_right(ends, p)]      # every edit that ends at or before p",
     "        return p"),
    ("S3 an insert at a close does not move it", "gamestate.py",
     "        return p + delta[bisect.bisect_right(ends, p)]      # every edit that ends at or before p",
     "        return p + delta[bisect.bisect_left(ends, p)]"),
    ("S4 every text counts as well nested", "gamestate.py",
     "        if not (_well_nested(old[e.start:e.end]) and _well_nested(e.replacement)):\n            return None",
     "        if False:\n            return None"),
    ("S5 braces inside strings counted", "gamestate.py",
     "    for m in _BRACE_OR_STRING.finditer(text):\n        tok = m.group()",
     "    for m in re.finditer(rb'[{}]', text):\n        tok = m.group()"),
    ("S6 edits outside a section accepted", "gamestate.py",
     "        if i < 0 or not (blocks[i].open < e.start and e.end <= blocks[i].close):\n            return None",
     "        if i < 0:\n            return None"),
    ("S7 the check mode never raises", "gamestate.py",
     "        if walked != shifted:\n            raise GamestateError",
     "        if False:\n            raise GamestateError"),
    ("L1 SectionIndex walks again", "lint.py",
     "        if idx is not None:\n            self.top = {k.decode(): bs[0] for k, bs in idx.items()}",
     "        if False:\n            self.top = {k.decode(): bs[0] for k, bs in idx.items()}"),
    ("L2 the last block of a repeated key", "lint.py",
     "self.top = {k.decode(): bs[0] for k, bs in idx.items()}",
     "self.top = {k.decode(): bs[-1] for k, bs in idx.items()}"),
    ("L3 no walk when the shared index is None", "lint.py",
     "            self.top = {k.decode(): bs[0] for k, bs in idx.items()}\n            return",
     "            self.top = {k.decode(): bs[0] for k, bs in idx.items()}\n            return\n        return"),
    ("F1 the rule never takes its check's plan", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if False and hit is not None and hit[0] is save.gamestate and hit[1] == values:"),
    ("F2 a plan for other bytes is taken", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if hit is not None and hit[1] == values:"),
    ("F3 a plan with other values is taken", "patches/pack.py",
     "        if hit is not None and hit[0] is save.gamestate and hit[1] == values:",
     "        if hit is not None and hit[0] is save.gamestate:"),
    # U1, 2026-11-07: the update stops at the first failed patch
    ("U1a no stop after a failed patch", "cli.py",
     "            res[-1].extra[\"not_run\"] = total - i\n            break",
     "            res[-1].extra[\"not_run\"] = total - i"),
    ("U1b no count of the patches not run", "cli.py",
     "            res[-1].extra[\"not_run\"] = total - i\n            break",
     "            break"),
    ("U1c the second faith shape still runs", "cli.py",
     "                break                                   # the other shape would be written by neither: stop now",
     "                pass"),
    # U2, 2026-11-07: a check sees its rule's inputs
    ("U2a R25's check drops the old game folder", "detect.py",
     "r25_detect(g, env.game_dir, env.mod_dirs, env.old_game_dir)",
     "r25_detect(g, env.game_dir, env.mod_dirs)"),
    ("U2b a declarative check ignores the rule's context", "detect.py",
     "verdict(g, p, env.rule_ctx or RuleContext(game_dir=env.game_dir))",
     "verdict(g, p, RuleContext(game_dir=env.game_dir))"),
    ("U2c R19's check ignores the transplanted characters", "detect.py",
     "res = plan_save(g, env.dna, state.get(\"transplanted_characters\"))",
     "res = plan_save(g, env.dna)"),
    # U4, 2026-11-07: R15's own check
    ("U4a R15 back on R6's report check", "detect.py",
     "\"R6\": _dead_titles, \"R15\": _r15,",
     "\"R6\": _dead_titles, \"R15\": _dead_titles,"),
    ("U4b R15's check counts removed titles only", "detect.py",
     "    kinds = Counter(m.kind for m in maps)\n",
     "    maps = [m for m in maps if m.kind == \"dead\"]\n    kinds = Counter(m.kind for m in maps)\n"),
    ("U4c no old-map guard", "detect.py",          # re-anchored 2026-11-07: the guard is now the resolver's None
     "    if old_lt is None:\n        return Detection(\"unknown\", why=why)\n",
     ""),
    ("U4d R19 splices outside the edit pass", "rules/faces.py",
     "        p.apply_to(save)",
     "        save.set_gamestate(p.apply(save.gamestate))"),
    # U5', 2026-11-07: an update that does not ask skips the checks and explains each count
    ("U5a the checks always run", "cli.py",
     "display_checks=not args.checks_skipped)",
     "display_checks=True)"),
    ("U5b no explanation after the counts", "cli.py",
     "        what = f\"  -- {r.description}\" if explain and r.description else \"\"",
     "        what = \"\""),
    ("U5c a dry run skips its checks too", "cli.py",
     "    args.checks_skipped = not (asking or args.dry_run)",
     "    args.checks_skipped = not asking"),
    ("U5d the plan ignores the switch", "plan.py",
     "        for s in judge if display_checks else []:",
     "        for s in judge:"),
    # T, 2026-11-07: the built-in old-map table (DWP 19:52)
    ("T1 the table is never used", "deadtitles.py",
     "    t = next((t for t in load_tables(KNOWN_TITLES) if line and line in t[\"game_lines\"]), None)",
     "    t = None"),
    ("T2 any version line takes the table", "deadtitles.py",
     "if line and line in t[\"game_lines\"]), None)",
     "if True), None)"),
    ("T3 the table wins over a given folder", "deadtitles.py",
     "    if old_game_dir:\n        folder = Path(old_game_dir)",
     "    if False:\n        folder = Path(old_game_dir)"),
    ("T4 the plan ignores the save's version", "plan.py",
     "            folder, source = old_map(old_game_dir, sv[\"version\"])",
     "            folder, source = old_map(old_game_dir, None)"),
    ("T5 the plan does not name the source", "plan.py",
     "                notes.append(f\"{r.id}'s old map: {source}\")",
     "                pass"),
    ("T6 the check ignores the save's version", "detect.py",
     "    old_lt, why = D.old_map(env.old_game_dir, env.save_version)",
     "    old_lt, why = D.old_map(env.old_game_dir, None)"),
    ("T7 the plan gives the check no version", "plan.py",
     "save_version=sv[\"version\"])",
     "save_version=None)"),
    ("T8 the rule ignores the save's version", "rules/transplant_1_20.py",
     "D.old_map(ctx.old_game_dir, '.'.join(map(str, have)) if have else None)",
     "D.old_map(ctx.old_game_dir, None)"),
    ("T9 the script drops the provinces", "../scripts/title_table.py",
     "            out.append(f\"{pad}\\tprovince = {province[key]}\\n\")",
     "            pass"),
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
    files = {n: PKG / n for n in ("gamestate.py", "lint.py", "patches/pack.py", "cli.py", "detect.py",
                                  "rules/faces.py", "plan.py", "deadtitles.py", "rules/transplant_1_20.py",
                                  "../scripts/title_table.py")}
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
