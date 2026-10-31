"""The ``tools`` add-on: ``ck3update tools list | run <name> [args...] | path <name>``, and the one runner it shares
with a run patch's ``tool =``.

A tool runs as ``[python, <script>] + args`` (``tools.script_command``), as a file, never with ``-m``, from the
caller's folder, with its exit code; nothing is written anywhere, and dazzlecmd-lib is not involved. Every script a
test runs is one it wrote into its own temporary folder: nothing runs from the repository's tests/one-offs (the last
test only lists them, which reads their docstrings with ``ast``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ck3_save_migrator import savefile as sf
from ck3_save_migrator import tools
from tests.test_patches_run import a_save, run_rule
from tests.test_patches_run_tool import TOOL, tool_pack

ROOT = Path(__file__).resolve().parents[1]

ECHO = '"""Print the arguments given.\n\nThe second line is not the description."""\nimport sys\n' \
       "print(sys.argv[1:])\nsys.stdout.flush()\nsys.exit(3)\n"
WHERE = "import os\nprint(os.getcwd())\nprint(__name__)\n"

# a meta-path finder that makes every import of dazzlecmd_lib fail, put in place before the command runs
NO_LIB = """
import sys
class NoLib:
    def find_spec(self, name, path=None, target=None):
        if name == "dazzlecmd_lib" or name.startswith("dazzlecmd_lib."):
            raise ImportError("dazzlecmd_lib is made unimportable for this test")
        return None
sys.meta_path.insert(0, NoLib())
from ck3_save_migrator import cli
code = cli.main(sys.argv[1:])
assert "dazzlecmd_lib" not in sys.modules
sys.exit(code)
"""


def cli(*args: str, cwd: Path = ROOT, env: dict | None = None, no_lib: bool = False) -> subprocess.CompletedProcess:
    full = {k: v for k, v in os.environ.items() if k != "CK3SM_SCRIPTS_DIR"}
    # the project folder on the path, so the command runs from any folder without the package being installed
    full["PYTHONPATH"] = os.pathsep.join(p for p in (str(ROOT), os.environ.get("PYTHONPATH", "")) if p)
    full.update(env or {})
    head = ["-c", NO_LIB] if no_lib else ["-m", "ck3_save_migrator"]
    return subprocess.run([sys.executable, *head, *args], cwd=cwd, capture_output=True, env=full)


@pytest.fixture
def scripts(tmp_path) -> Path:
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "echo_args.py").write_text(ECHO, encoding="utf-8")
    (d / "no_doc.py").write_text("print('hello')\n", encoding="utf-8")
    (d / "where.py").write_text(WHERE, encoding="utf-8")
    (d / "notes.txt").write_text("not a tool\n", encoding="utf-8")
    (d / "sub").mkdir()
    (d / "sub" / "nested.py").write_text('"""Not a tool: in a subfolder."""\n', encoding="utf-8")
    return d


def snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*"))}


def run_tools(scripts: Path, *rest: str, **kw):
    return cli("tools", "--scripts-dir", str(scripts), *rest, **kw)


# --------------------------------------------------------------------------- list and path
def test_list_shows_each_script_with_the_first_docstring_line(scripts):
    r = run_tools(scripts, "list")
    assert r.returncode == 0, r.stderr
    rows = [line.split(None, 1) for line in r.stdout.decode().splitlines()]
    assert rows == [["echo_args", "Print the arguments given."], ["no_doc"], ["where"]]


def test_list_never_runs_or_imports_a_script(tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    marker = tmp_path / "ran"
    (d / "loud.py").write_text(f'"""Loud."""\nopen({str(marker)!r}, "w").write("x")\nraise SystemExit(9)\n',
                               encoding="utf-8")
    r = run_tools(d, "list")
    assert r.returncode == 0 and r.stdout.decode().split() == ["loud", "Loud."] and not marker.exists()


def test_path_prints_the_script_path(scripts):
    r = run_tools(scripts, "path", "echo_args")
    assert r.returncode == 0 and Path(r.stdout.decode().strip()) == (scripts / "echo_args.py").resolve()


@pytest.mark.parametrize("verb", ["run", "path"])
def test_an_unknown_tool_exits_2_naming_it(scripts, verb):
    r = run_tools(scripts, verb, "nope")
    assert r.returncode == 2 and "'nope'" in r.stderr.decode()


def test_the_scripts_folder_comes_from_the_environment(scripts):
    r = cli("tools", "list", env={"CK3SM_SCRIPTS_DIR": str(scripts)})
    assert r.returncode == 0 and r.stdout.decode().split()[0] == "echo_args"


def test_a_missing_scripts_folder_is_named(tmp_path):
    r = run_tools(tmp_path / "absent", "list")
    assert r.returncode == 2 and "absent" in r.stderr.decode()


def test_with_no_scripts_folder_at_all_it_says_so_and_exits_2():
    probe = ("import sys; from ck3_save_migrator import cli, tools; tools.checkout_scripts_dir = lambda: None; "
             "sys.exit(cli.main(['tools', 'list']))")
    env = {k: v for k, v in os.environ.items() if k != "CK3SM_SCRIPTS_DIR"}
    r = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "no scripts folder" in r.stderr and "--scripts-dir" in r.stderr


# --------------------------------------------------------------------------- run
def test_run_is_the_script_run_directly(scripts, tmp_path):
    args = ["a", "b c", "-h", "--flag=1", "-v"]
    direct = subprocess.run([sys.executable, str(scripts / "echo_args.py"), *args], capture_output=True, cwd=tmp_path)
    via = run_tools(scripts, "run", "echo_args", *args, cwd=tmp_path)
    assert direct.returncode == 3
    assert (via.stdout, via.returncode) == (direct.stdout, direct.returncode)


def test_run_runs_from_the_callers_folder(scripts, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    out = run_tools(scripts, "run", "where", cwd=work).stdout.decode().splitlines()
    assert Path(out[0]).resolve() == work.resolve()


def test_a_script_in_a_folder_with_an_init_py_still_runs_as_a_file(scripts):
    (scripts / "__init__.py").write_text("raise SystemExit('imported as a package')\n", encoding="utf-8")
    r = run_tools(scripts, "run", "where")
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode().splitlines()[-1] == "__main__"


def test_run_needs_no_dazzlecmd_lib_and_writes_nothing(scripts, tmp_path):
    work, home = tmp_path / "work", tmp_path / "home"
    work.mkdir()
    home.mkdir()
    # a home and cache of their own, so a write to the user's cache or config folders would show up here
    env = {"HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(home), "LOCALAPPDATA": str(home / "local"),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache")}
    before = snapshot(tmp_path)
    r = run_tools(scripts, "run", "echo_args", "x", cwd=work, env=env, no_lib=True)
    assert r.returncode == 3, r.stderr
    assert r.stdout.decode().strip() == "['x']"
    assert snapshot(tmp_path) == before                       # no cache folder, nothing beside the scripts


# --------------------------------------------------------------------------- one command builder
def test_tools_run_and_a_tool_run_patch_build_their_command_with_the_same_function(tmp_path, monkeypatch):
    calls = []
    real = tools.script_command

    def recording(script, args):
        calls.append(Path(script).name)
        return real(script, args)
    monkeypatch.setattr(tools, "script_command", recording)
    monkeypatch.chdir(tmp_path)
    pack = tool_pack(tmp_path, TOOL)                     # a tool = "edit_save" run patch
    save = sf.read_save(a_save(tmp_path))
    assert run_rule(pack, save, {"scripts_dir": str(tmp_path / "scripts")}).edited == 1
    (tmp_path / "scripts" / "quiet.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
    assert tools.run(tmp_path / "scripts", "quiet", []) == 0
    assert calls == ["edit_save.py", "quiet.py"]


def test_the_command_is_python_then_the_script_then_the_arguments(tmp_path):
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    assert tools.script_command(tmp_path / "x.py", ["a", 1]) == [sys.executable, str(tmp_path / "x.py"), "a", "1"]


# --------------------------------------------------------------------------- the repository's one-offs, listed only
def test_list_over_the_repository_one_offs_has_one_tool_per_py_file():
    r = cli("tools", "list")
    assert r.returncode == 0, r.stderr
    names = [line.split(None, 1)[0] for line in r.stdout.decode().splitlines()]
    assert names == sorted(p.stem for p in (ROOT / "tests" / "one-offs").glob("*.py"))
