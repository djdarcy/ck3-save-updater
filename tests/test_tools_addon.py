"""The optional ``tools`` add-on: ``ck3-save-migrator tools list | run <name> [args...] | path <name>``.

Every test runs the command line in a subprocess, as a user would. A script run through ``tools run`` must behave as
the script run directly: the same standard output, byte for byte, and the same exit code. The scripts folder is never
written to; the only files written are the generated listing in the cache folder.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("dazzlecmd_lib")

ROOT = Path(__file__).resolve().parents[1]

ECHO = '"""Print the arguments given.\n\nThe second line is not the description."""\nimport sys\n' \
       "print(sys.argv[1:])\nsys.stdout.flush()\nsys.exit(3)\n"


def cli(*args: str, cwd: Path = ROOT, env: dict | None = None) -> subprocess.CompletedProcess:
    full = {k: v for k, v in os.environ.items() if k not in ("CK3SM_SCRIPTS_DIR", "CK3SM_TOOLS_CACHE")}
    # the project folder on the path, so the command runs from any folder without the package being installed
    full["PYTHONPATH"] = os.pathsep.join(p for p in (str(ROOT), os.environ.get("PYTHONPATH", "")) if p)
    full.update(env or {})
    return subprocess.run([sys.executable, "-m", "ck3_save_migrator", *args], cwd=cwd, capture_output=True,
                          env=full)


@pytest.fixture
def scripts(tmp_path) -> Path:
    d = tmp_path / "scripts"
    d.mkdir()
    (d / "echo_args.py").write_text(ECHO, encoding="utf-8")
    (d / "no_doc.py").write_text("print('hello')\n", encoding="utf-8")
    (d / "notes.txt").write_text("not a tool\n", encoding="utf-8")
    (d / "run.sh").write_text("echo not a tool\n", encoding="utf-8")
    (d / "sub").mkdir()
    (d / "sub" / "nested.py").write_text('"""Not a tool: in a subfolder."""\n', encoding="utf-8")
    return d


def snapshot(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*"))}


def tools(scripts: Path, cache: Path, *rest: str, cwd: Path = ROOT, env: dict | None = None):
    return cli("tools", "--scripts-dir", str(scripts), "--cache-dir", str(cache), *rest, cwd=cwd, env=env)


def test_list_shows_each_script_with_the_first_docstring_line(scripts, tmp_path):
    r = tools(scripts, tmp_path / "cache", "list")
    assert r.returncode == 0, r.stderr
    rows = [line.split(None, 1) for line in r.stdout.decode().splitlines()]
    assert rows == [["echo_args", "Print the arguments given."], ["no_doc"]]


def test_list_never_runs_or_imports_a_script(tmp_path):
    d = tmp_path / "scripts"
    d.mkdir()
    marker = tmp_path / "ran"
    (d / "loud.py").write_text(f'"""Loud."""\nopen({str(marker)!r}, "w").write("x")\nraise SystemExit(9)\n',
                               encoding="utf-8")
    r = tools(d, tmp_path / "cache", "list")
    assert r.returncode == 0 and r.stdout.decode().split() == ["loud", "Loud."] and not marker.exists()


def test_run_is_the_script_run_directly(scripts, tmp_path):
    args = ["a", "b c", "-h", "--flag=1", "-v"]
    direct = subprocess.run([sys.executable, str(scripts / "echo_args.py"), *args], capture_output=True,
                            cwd=tmp_path)
    via = tools(scripts, tmp_path / "cache", "run", "echo_args", *args, cwd=tmp_path)
    assert direct.returncode == 3
    assert (via.stdout, via.returncode) == (direct.stdout, direct.returncode)


def test_run_leaves_the_scripts_folder_alone_and_writes_only_in_the_cache(scripts, tmp_path):
    work, home = tmp_path / "work", tmp_path / "home"
    work.mkdir()
    home.mkdir()
    # a home of its own, so a write to the user's home or config folders would show up here too
    env = {"HOME": str(home), "USERPROFILE": str(home), "APPDATA": str(home), "LOCALAPPDATA": str(home),
           "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache")}
    before, outside = snapshot(scripts), snapshot(tmp_path)
    cache = tmp_path / "cache"
    assert tools(scripts, cache, "run", "echo_args", "x", cwd=work, env=env).returncode == 3
    assert tools(scripts, cache, "list", cwd=work, env=env).returncode == 0
    assert snapshot(scripts) == before
    written = {k for k in snapshot(tmp_path) if k not in outside}
    assert "cache/shadow/kits/oneoffs.kit.json" in written
    assert all(k == "cache" or k.startswith("cache/") for k in written), written


def test_path_prints_the_script_path(scripts, tmp_path):
    r = tools(scripts, tmp_path / "cache", "path", "echo_args")
    assert r.returncode == 0 and Path(r.stdout.decode().strip()) == (scripts / "echo_args.py").resolve()


@pytest.mark.parametrize("verb", ["run", "path"])
def test_an_unknown_tool_exits_non_zero_naming_it(scripts, tmp_path, verb):
    r = tools(scripts, tmp_path / "cache", verb, "nope")
    assert r.returncode != 0 and "'nope'" in r.stderr.decode()


def test_the_scripts_folder_comes_from_the_environment(scripts, tmp_path):
    r = cli("tools", "--cache-dir", str(tmp_path / "cache"), "list", env={"CK3SM_SCRIPTS_DIR": str(scripts)})
    assert r.returncode == 0 and r.stdout.decode().split()[0] == "echo_args"


def test_a_missing_scripts_folder_is_named(tmp_path):
    r = tools(tmp_path / "absent", tmp_path / "cache", "list")
    assert r.returncode == 2 and "absent" in r.stderr.decode()


def test_with_no_scripts_folder_at_all_it_says_so_and_exits_2(tmp_path):
    probe = ("import sys; from ck3_save_migrator import cli, tools; tools.checkout_scripts_dir = lambda: None; "
             "sys.exit(cli.main(['tools', 'list']))")
    env = {k: v for k, v in os.environ.items() if k != "CK3SM_SCRIPTS_DIR"}
    r = subprocess.run([sys.executable, "-c", probe], cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "no scripts folder" in r.stderr and "--scripts-dir" in r.stderr


def test_list_over_the_repository_one_offs_has_one_tool_per_py_file(tmp_path):
    r = cli("tools", "--cache-dir", str(tmp_path / "cache"), "list")
    assert r.returncode == 0, r.stderr
    names = [line.split(None, 1)[0] for line in r.stdout.decode().splitlines()]
    assert names == sorted(p.stem for p in (ROOT / "tests" / "one-offs").glob("*.py"))
