"""``ck3update setup``: dazzlecmd-lib's self-setup, for a player whose ``ck3update`` is "not recognized".

Safety first: no test can touch the real PATH, registry or shell profile. Every test that reaches the verb replaces
``dazzlecmd_lib.self_setup.run_self_setup`` with a stub that records its arguments and returns a chosen code, and
also replaces the functions that would write PATH, the registry or a shell fix script with ones that fail the test,
so the safety never rests on ``dry_run`` being honoured.
"""

from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import cli

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def stub(monkeypatch):
    """The recorded calls, and the code the stub returns (set ``stub.code``)."""
    from dazzlecmd_lib import self_setup, shell_fix

    class Stub:
        code = 0
        calls: list = []

        def __call__(self, command_names, **kw):
            self.calls.append((list(command_names), kw))
            return self.code
    s = Stub()
    s.calls = []
    monkeypatch.setattr(self_setup, "run_self_setup", s)

    def never(*a, **k):
        pytest.fail("a PATH, registry or shell-profile writer was reached")
    for name in ("fix_windows", "_write_user_path_raw", "_broadcast_environment_change", "_write_backup",
                 "first_run_hint"):
        monkeypatch.setattr(self_setup, name, never)
    for name in ("write_fix_scripts", "emit_current_shell_fix"):
        monkeypatch.setattr(shell_fix, name, never)
    return s


def test_setup_calls_self_setup_with_this_tools_commands_and_package(stub):
    assert cli.main(["setup"]) == 0
    expected = {"package_name": "ck3-save-updater", "assume_yes": False, "dry_run": False, "emit_shell_fix": False}
    assert stub.calls == [(["ck3update", "ck3-save-migrator"], expected)]


def test_the_flags_arrive_as_assume_yes_dry_run_and_emit_shell_fix(stub):
    assert cli.main(["setup", "--yes", "--dry-run", "--shell-fix"]) == 0
    kw = stub.calls[-1][1]
    assert (kw["assume_yes"], kw["dry_run"], kw["emit_shell_fix"]) == (True, True, True)


@pytest.mark.parametrize("code", [0, 1])
def test_the_exit_code_is_self_setups(stub, code):
    stub.code = code
    assert cli.main(["setup", "--dry-run"]) == code


def test_setup_takes_its_own_name_as_dazzlecmd_libs_advice_writes_it(stub, capsys):
    assert cli.main(["setup", "ck3_save_migrator", "--yes"]) == 0          # python -m <pkg> setup <pkg> --yes
    assert cli.main(["setup", "something-else"]) == 1
    assert "not one of its names" in capsys.readouterr().err and len(stub.calls) == 1


def test_python_dash_m_reaches_the_stub_through_main(stub, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ck3_save_migrator", "setup", "--dry-run"])
    stub.code = 1
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("ck3_save_migrator", run_name="__main__")
    assert exc.value.code == 1 and stub.calls[-1][1]["dry_run"] is True


# --------------------------------------------------------------------------- dazzlecmd-lib is loaded by setup only
LAZY = """
import sys
from ck3_save_migrator import cli
try:
    cli.main(sys.argv[1:])
except SystemExit:
    pass
print("dazzlecmd_lib" in sys.modules, file=sys.stderr)
"""


@pytest.mark.parametrize("args", [None, ["--version"], ["status", "--help"]])
def test_no_other_command_imports_dazzlecmd_lib(args):
    code = "import sys, ck3_save_migrator.cli; print('dazzlecmd_lib' in sys.modules, file=sys.stderr)" \
        if args is None else LAZY
    r = subprocess.run([sys.executable, "-c", code, *(args or [])], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stderr.strip().splitlines()[-1] == "False"


NO_LIB = """
import sys
class NoLib:
    def find_spec(self, name, path=None, target=None):
        if name == "dazzlecmd_lib" or name.startswith("dazzlecmd_lib."):
            raise ImportError("dazzlecmd_lib is made unimportable for this test")
        return None
sys.meta_path.insert(0, NoLib())
from ck3_save_migrator import cli
sys.exit(cli.main(sys.argv[1:]))
"""


def test_without_dazzlecmd_lib_setup_exits_1_naming_the_package_and_other_commands_work():
    env = {**os.environ, "CK3_GAME_DIR": "none"}
    r = subprocess.run([sys.executable, "-c", NO_LIB, "setup", "--dry-run"], cwd=ROOT, capture_output=True,
                       text=True, env=env)
    assert r.returncode == 1
    assert r.stderr.strip().splitlines()[-1].endswith("reinstall it: pip install --force-reinstall ck3-save-updater")
    r = subprocess.run([sys.executable, "-c", NO_LIB, "rules"], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout.startswith("R1 ")
