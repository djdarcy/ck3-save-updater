"""Red-green audit of the grouped `ck3update -h` (2026-11-02, djdarcy's ask): each mutation reverts one behaviour
of helptext.py / cli.py; the named tests must go RED with it and GREEN after the restore.

The harness is redgreen_s1.py's, copied: a fresh bytecode cache per pytest run, the source held in memory and in a
temporary backup, written back after every mutation and at the end.

Run from the repo root:  python -I tests/one-offs/thinking/redgreen_helptext.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
H = "tests/test_helptext.py"
MUTATIONS = [
    ("a command left out of the groups", "ck3_save_migrator/helptext.py",
     '        ("tools", ("tools",), "the standalone scripts"),\n', "",
     [f"{H}::test_every_command_is_in_exactly_one_group_and_no_group_names_a_missing_one"]),
    ("a bare ck3update is argparse's error again", "ck3_save_migrator/cli.py",
     "    if args.command is None:                             # a bare `ck3update`: where to start, not an error\n"
     "        print(helptext.bare())\n        return 0\n", "",
     [f"{H}::test_bare_command_prints_where_to_start_and_succeeds"]),
    ("the flat list kept beside the groups", "ck3_save_migrator/cli.py",
     "    sub._choices_actions.clear()\n", "",
     [f"{H}::test_help_starts_with_status_and_shows_each_group"]),
    ("a command's help loses its description", "ck3_save_migrator/cli.py",
     "        sp.description = sp.description or choice.help\n", "        pass\n",
     [f"{H}::test_a_command_help_opens_with_its_one_line_description",
      "tests/test_soak.py::test_the_command_says_it_starts_the_game_in_its_help"]),
    ("a start-here line wider than 79", "ck3_save_migrator/helptext.py",
     "  ck3update status              # finds your game and your save folder\n",
     "  ck3update status              # finds your game and your save folder, and says where it found each one\n",
     [f"{H}::test_help_fits_an_80_column_console"]),
    # the sweep's H1: a given --old-game-dir that is not a game folder refuses
    ("a wrong --old-game-dir accepted", "ck3_save_migrator/plan.py",
     '    if old_game_dir and not (Path(old_game_dir) / "common" / "landed_titles").is_dir():\n', "    if False:\n",
     ["tests/test_update.py::test_an_old_game_dir_that_is_not_a_game_folder_is_refused_before_anything_runs"]),
]


def pytest(tests):
    with tempfile.TemporaryDirectory(prefix="rg-pyc-") as pyc:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests], cwd=ROOT,
                           capture_output=True, text=True, timeout=600,
                           env={**os.environ, "PYTHONPYCACHEPREFIX": pyc})
    return r.returncode, r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]


def main() -> int:
    files = sorted({m[1] for m in MUTATIONS})
    original = {f: (ROOT / f).read_bytes() for f in files}
    bad = 0
    with tempfile.TemporaryDirectory(prefix="rg-backup-") as backup:
        for f in files:
            shutil.copy2(ROOT / f, Path(backup) / Path(f).name)
        try:
            for name, f, old, new, tests in MUTATIONS:
                src = original[f].decode("utf-8")
                if "\r\n" in src:                                  # a CRLF checkout: match its line ends
                    old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
                assert src.count(old) == 1, f"{name}: anchor found {src.count(old)} times"
                (ROOT / f).write_bytes(src.replace(old, new).encode("utf-8"))
                red, red_line = pytest(tests)
                (ROOT / f).write_bytes(original[f])
                green, green_line = pytest(tests)
                ok = red != 0 and green == 0
                bad += not ok
                print(f"{'OK  ' if ok else 'FAIL'} {name}: mutated -> {red_line} | restored -> {green_line}")
        finally:
            for f in files:
                (ROOT / f).write_bytes(original[f])
        restored = all((ROOT / f).read_bytes() == (Path(backup) / Path(f).name).read_bytes() for f in files)
    print("source restored and equal to the backup:", restored)
    return 1 if bad or not restored else 0


if __name__ == "__main__":
    sys.exit(main())
