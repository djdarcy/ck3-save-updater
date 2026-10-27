"""The purity and honesty guard of the vendored savediff library (ck3_save_migrator/_vendor/savediff).

savediff stays vendored until it becomes its own repository, and becoming one must be a copy of its folder. So:
(a) the folder holds exactly the files its _VENDORED.md names; (b) nothing in it imports the host package, no
relative import climbs out of it, and the host's name appears in none of its code; (c) every import is from the
standard library or from inside the folder; (d) no host module outside _vendor imports it (an allowlist, empty
today); (e) a copy of the folder imports and runs with the host made unimportable.

Each check is a function of a folder, so the guard is also run against a copy of the tree with a violation planted
in it: a guard that cannot fail proves nothing.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "ck3_save_migrator"
VENDOR = HOST / "_vendor" / "savediff"
PACKAGE = "ck3_save_migrator._vendor.savediff"
TOKEN = "ck3_save_migrator"
# host modules (outside _vendor) allowed to import savediff: none yet; the future `diff` command goes here
ALLOWED_IMPORTERS: set[str] = set()


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts}


def named_in_record(root: Path) -> set[str]:
    """The file names in the first column of _VENDORED.md's "Files" table."""
    text = (root / "_VENDORED.md").read_text(encoding="utf-8")
    section = text.split("## Files", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"(?m)^\|\s*`([^`]+)`\s*\|", section))


def record_violations(root: Path) -> list[str]:
    if not (root / "_VENDORED.md").is_file():
        return ["_VENDORED.md is missing"]
    named, present = named_in_record(root), _files(root)
    return ([f"{f}: in the folder but not named in _VENDORED.md" for f in sorted(present - named)]
            + [f"{f}: named in _VENDORED.md but not in the folder" for f in sorted(named - present)])


def _inside(name: str) -> bool:
    return name == PACKAGE or name.startswith(PACKAGE + ".")


def _imports(py: Path, package: str):
    """(line, resolved absolute module, imported names, was relative) for every import statement of a file;
    ``package`` is the dotted package the file belongs to, for resolving relative imports."""
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name, [], False
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names]
            if node.level:
                target = importlib.util.resolve_name("." * node.level + (node.module or ""), package)
                yield node.lineno, target, names, True
            else:
                yield node.lineno, node.module, names, False


def import_violations(root: Path) -> list[str]:
    """(b) and (c): host imports, relative imports that leave the folder, imports outside the standard library.
    Each file is resolved as if the folder were the package PACKAGE."""
    out = []
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        package = ".".join([PACKAGE, *rel.parts[:-1]])
        for line, module, _, relative in _imports(py, package):
            where = f"{rel.as_posix()}:{line}"
            if relative:
                if not _inside(module):
                    out.append(f"{where}: relative import resolves outside the folder: {module}")
            elif module.split(".")[0] == TOKEN:
                out.append(f"{where}: imports the host package: {module}")
            elif module.split(".")[0] not in sys.stdlib_module_names:
                out.append(f"{where}: imports outside the standard library: {module}")
    return out


def token_violations(root: Path) -> list[str]:
    """(b): the host's name in any line of the folder's code (comments and strings included)."""
    out = []
    for py in sorted(root.rglob("*.py")):
        for n, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if TOKEN in line:
                out.append(f"{py.relative_to(root).as_posix()}:{n}: mentions {TOKEN}: {line.strip()}")
    return out


def host_importers(host: Path) -> list[str]:
    """(d): host modules outside _vendor that import savediff, by module name."""
    out = []
    for py in sorted(host.rglob("*.py")):
        rel = py.relative_to(host)
        if rel.parts[0] == "_vendor":
            continue
        mod = ".".join([TOKEN, *rel.with_suffix("").parts])
        package = ".".join([TOKEN, *rel.parts[:-1]])
        for line, module, names, _ in _imports(py, package):
            hit = _inside(module) or (module == f"{TOKEN}._vendor" and "savediff" in names)
            if hit and mod not in ALLOWED_IMPORTERS:
                out.append(f"{rel.as_posix()}:{line}: imports savediff")
    return out


LIFT_PROBE = (
    "import sys\n"
    f"sys.modules[{TOKEN!r}] = None\n"            # the host made unimportable: any import of it raises
    "sys.path.insert(0, '.')\n"                    # -I leaves the working directory off sys.path
    "import savediff, savediff.shape, savediff.keys\n"
    "s = savediff.shape.shape(b'living={\\n1={\\n}\\n}\\n')\n"
    "assert s['living'].count == 1, s\n"
    "print('lifted', sorted(s))\n"
)


def lift(folder: Path, into: Path) -> subprocess.CompletedProcess:
    shutil.copytree(folder, into / "savediff", ignore=shutil.ignore_patterns("__pycache__"))
    return subprocess.run([sys.executable, "-I", "-c", LIFT_PROBE], cwd=into, capture_output=True, text=True)


# --------------------------------------------------------------------------- the real tree
def test_a_the_folder_holds_exactly_the_files_the_record_names():
    assert (VENDOR / "_VENDORED.md").is_file()
    assert record_violations(VENDOR) == []
    assert {"__init__.py", "text.py", "shape.py", "ids.py", "keys.py", "_VENDORED.md"} <= named_in_record(VENDOR)


def test_b_c_imports_are_standard_library_or_inside_the_folder():
    assert import_violations(VENDOR) == []


def test_b_the_host_name_appears_in_no_line_of_code():
    assert token_violations(VENDOR) == []


def test_d_no_host_module_imports_savediff_outside_the_allowlist():
    assert host_importers(HOST) == []


def test_e_a_copy_of_the_folder_imports_and_runs_without_the_host(tmp_path):
    r = lift(VENDOR, tmp_path)
    assert r.returncode == 0, r.stderr
    assert "lifted ['living']" in r.stdout


# --------------------------------------------------------------------------- the guard can fail
@pytest.fixture
def copy(tmp_path) -> Path:
    dst = tmp_path / "savediff"
    shutil.copytree(VENDOR, dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


def test_guard_a_catches_an_unrecorded_file(copy):
    (copy / "extra.py").write_text("x = 1\n", encoding="utf-8")
    assert record_violations(copy) == ["extra.py: in the folder but not named in _VENDORED.md"]


def test_guard_a_catches_a_recorded_file_that_is_gone(copy):
    (copy / "ids.py").unlink()
    assert record_violations(copy) == ["ids.py: named in _VENDORED.md but not in the folder"]


def test_guard_a_catches_a_missing_record(copy):
    (copy / "_VENDORED.md").unlink()
    assert record_violations(copy) == ["_VENDORED.md is missing"]


@pytest.mark.parametrize("planted,expect", [
    (f"import {TOKEN}\n", "imports the host package"),
    (f"from {TOKEN} import gamestate\n", "imports the host package"),
    (f"from {TOKEN}.lint import SectionIndex\n", "imports the host package"),
    ("from ... import gamestate\n", "relative import resolves outside the folder"),
    ("from .. import savediff\n", "relative import resolves outside the folder"),
    ("import numpy\n", "imports outside the standard library"),
])
def test_guard_b_c_catch_a_planted_import(copy, planted, expect):
    (copy / "keys.py").write_text((copy / "keys.py").read_text(encoding="utf-8") + planted, encoding="utf-8")
    found = import_violations(copy)
    assert len(found) == 1 and found[0].startswith("keys.py:") and expect in found[0], found


def test_guard_b_catches_the_host_name_in_a_comment(copy):
    (copy / "ids.py").write_text((copy / "ids.py").read_text(encoding="utf-8") + f"# see {TOKEN}\n",
                                 encoding="utf-8")
    found = token_violations(copy)
    assert len(found) == 1 and found[0].startswith("ids.py:") and TOKEN in found[0], found


def test_guard_b_catches_the_host_import_in_a_new_file(copy):
    """The M12 check: a host import added to a savediff file is caught by the token check on its own."""
    (copy / "extra.py").write_text(f"from {TOKEN} import lint\n", encoding="utf-8")
    assert [v for v in token_violations(copy) if v.startswith("extra.py:1:")]


def test_guard_d_catches_a_host_module_that_imports_savediff(tmp_path):
    host = tmp_path / TOKEN
    (host / "_vendor" / "savediff").mkdir(parents=True)
    (host / "__init__.py").write_text("", encoding="utf-8")
    (host / "diffcmd.py").write_text("from ._vendor.savediff import shape\n", encoding="utf-8")
    (host / "other.py").write_text(f"import {PACKAGE}.keys\n", encoding="utf-8")
    assert host_importers(host) == ["diffcmd.py:1: imports savediff", "other.py:1: imports savediff"]


def test_guard_e_fails_when_the_copy_needs_the_host(copy, tmp_path):
    (copy / "text.py").write_text((copy / "text.py").read_text(encoding="utf-8") + f"import {TOKEN}\n",
                                  encoding="utf-8")
    into = tmp_path / "lifted"
    into.mkdir()
    r = lift(copy, into)
    assert r.returncode != 0 and ("ImportError" in r.stderr or "ModuleNotFoundError" in r.stderr), r.stderr
