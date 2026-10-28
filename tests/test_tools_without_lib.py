"""Without dazzlecmd-lib the ``tools`` command says how to install it, in one line, and exits 2; its help still works.

The library is made unimportable in a subprocess (``sys.modules["dazzlecmd_lib"] = None``), so this runs whether or
not it is installed here."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = """
import sys
sys.modules["dazzlecmd_lib"] = None              # any import of it now fails
from ck3_save_migrator import cli
sys.exit(cli.main(sys.argv[1:]))
"""


def probe(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", PROBE, *args], cwd=ROOT, capture_output=True, text=True)


def test_tools_list_without_the_library_prints_the_install_hint_and_exits_2(tmp_path):
    r = probe("tools", "--scripts-dir", str(tmp_path), "list")
    assert r.returncode == 2
    assert r.stdout == ""
    assert r.stderr.strip().splitlines() == ['the tools add-on needs dazzlecmd-lib: pip install '
                                             '"ck3-save-updater[tools]"']


def test_tools_run_without_the_library_exits_2_with_the_hint(tmp_path):
    (tmp_path / "x.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    r = probe("tools", "--scripts-dir", str(tmp_path), "run", "x")
    assert r.returncode == 2 and 'pip install "ck3-save-updater[tools]"' in r.stderr


def test_tools_help_works_without_the_library():
    for args in (["tools", "--help"], ["tools", "run", "--help"]):
        r = probe(*args)
        assert r.returncode == 0, r.stderr
        assert "usage:" in r.stdout and "dazzlecmd" not in r.stderr
