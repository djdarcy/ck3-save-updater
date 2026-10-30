"""The shipped pack (ck3_save_migrator/packs/to_1_20) is the registry.

``REGISTRY`` is built from it, and it gives the same ids in the same order, with the same name, since,
description, default and requires, as v0.3.11's Python registry did (recorded from that version in
``tests/fixtures/patches/``); each code patch's ``apply`` is the very function v0.3.11 ran, and ``rules`` prints
what it printed. The last test builds the wheel, installs it into a fresh virtual environment and loads the pack
from an empty directory, so a wheel that forgot its .toml files, or code that reads from the source tree, fails.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

from ck3_save_migrator.patches import read_pack, rules_from_pack
from ck3_save_migrator.rules import REGISTRY, _ORDER, religion_1_20, to_1_20, transplant_1_20

ROOT = Path(__file__).resolve().parents[1]
DECLARATIVE = {"R1", "R4", "R5", "R7", "R11"}


def test_the_pack_order_is_the_registry_order():
    assert list(read_pack().order) == _ORDER


def test_the_registry_is_the_shipped_pack():
    assert [(r.id, r.name, r.apply.patch.kind if hasattr(r.apply, "patch") else "code") for r in REGISTRY] == \
           [(r.id, r.name, r.apply.patch.kind if hasattr(r.apply, "patch") else "code") for r in rules_from_pack()]


# rules added after v0.3.11 (where each goes: after the rule named)
ADDED = {"R23": "R12"}


def since_v0_3_11():
    """The registry without the rules added after v0.3.11."""
    return [r for r in REGISTRY if r.id not in ADDED]


def test_the_rules_added_since_v0_3_11_sit_where_they_belong():
    ids = [r.id for r in REGISTRY]
    for rid, after in ADDED.items():
        assert ids.index(rid) == ids.index(after) + 1, rid


def test_the_registry_is_v0_3_11s_field_by_field():
    """Every rule's id, order, name, since, description, default and requires as v0.3.11's Python registry had
    them (recorded from that version in tests/fixtures/patches/registry_v0.3.11.json); the rules added since are
    checked by the test above."""
    old = json.loads((ROOT / "tests" / "fixtures" / "patches" / "registry_v0.3.11.json").read_text(encoding="utf-8"))
    assert [r.id for r in since_v0_3_11()] == [o["id"] for o in old]
    for mine, theirs in zip(since_v0_3_11(), old):
        assert (mine.name, mine.since, mine.description, mine.default, list(mine.requires)) == \
               (theirs["name"], theirs["since"], theirs["description"], theirs["default"], theirs["requires"]), mine.id


def test_each_code_patch_runs_the_very_function_v0_3_11_ran():
    """The 14 code patches name the same functions v0.3.11's registry held; the 5 retired rules are declarative."""
    old = json.loads((ROOT / "tests" / "fixtures" / "patches" / "registry_v0.3.11.json").read_text(encoding="utf-8"))
    python = {r.id: r.apply for mod in (to_1_20, religion_1_20, transplant_1_20) for r in mod.RULES}
    for r, o in zip(since_v0_3_11(), old):
        if r.id in DECLARATIVE:
            assert r.apply.patch.kind == "declarative" and r.id not in python, r.id
        else:
            module, name = o["function"].split(":")
            assert r.apply is getattr(importlib.import_module(module), name) is python[r.id], r.id
    # and the rules added since are code patches naming their function in the package
    for r in REGISTRY:
        if r.id in ADDED:
            assert r.apply is python[r.id], r.id


def test_the_rules_command_prints_what_v0_3_11_printed(capsys):
    """v0.3.11's lines unchanged, with one line per added rule after the rule it follows."""
    from ck3_save_migrator import cli
    assert cli.main(["rules"]) == 0
    out = capsys.readouterr().out.splitlines()
    expected = (ROOT / "tests" / "fixtures" / "patches" / "rules_v0.3.11.txt").read_text(encoding="utf-8").splitlines()
    assert [ln for ln in out if ln.split()[0] not in ADDED] == expected
    for rid, after in ADDED.items():
        i = next(i for i, ln in enumerate(out) if ln.split()[0] == rid)
        assert out[i - 1].split()[0] == after


def test_the_shipped_pack_uses_no_script_files():
    for p in read_pack().patches.values():
        assert p.script is None or ".py:" not in p.script
        assert p.run is None


def test_patch_folders_are_named_id_dash_name():
    for p in read_pack().patches.values():
        assert p.folder.name == f"{p.id}-{p.name}"


def _build_wheel(out: Path) -> Path:
    """Build from a clean copy of the source, so a stale build/ or egg-info folder cannot supply missing files."""
    src = out.parent / "src"
    skip = shutil.ignore_patterns(".git", "build", "dist", "*.egg-info", "__pycache__", "private", ".venv",
                                  ".pytest_cache", "tests")
    shutil.copytree(ROOT, src, ignore=skip)
    # every builder that is present is tried in turn, so the test runs wherever any of them works
    tried = []
    builders = []
    if shutil.which("uv"):
        builders.append(("uv build", [shutil.which("uv"), "build", "--wheel", "-o", str(out), "-q"]))
    else:
        tried.append("uv build: uv is not installed")
    # pip uses the installed setuptools when there is one (no network needed), else fetches it
    isolation = ["--no-build-isolation"] if importlib.util.find_spec("setuptools") else []
    for module, cmd in (("build", ["-m", "build", "--wheel", "--outdir", str(out)]),
                        ("pip", ["-m", "pip", "wheel", ".", "--no-deps", *isolation, "-w", str(out), "-q"])):
        if importlib.util.find_spec(module) is None:
            tried.append(f"python -m {module}: the {module} module is not installed")
        else:
            builders.append((f"python -m {module}", [sys.executable, *cmd]))
    for name, cmd in builders:
        r = subprocess.run(cmd, cwd=src, capture_output=True, text=True)
        wheels = list(out.glob("*.whl"))
        if r.returncode == 0 and wheels:
            return wheels[0]
        last = (r.stderr.strip() or r.stdout.strip()).splitlines()[-1:] or ["no output"]
        tried.append(f"{name}: exit code {r.returncode}, {last[0][:200]}")
    pytest.skip("no wheel could be built here; " + "; ".join(tried))


def test_the_built_wheel_carries_the_pack_and_loads_it_from_an_empty_directory(tmp_path):
    if sys.version_info < (3, 11):                  # tomli is the only dependency the pack loader needs on 3.10
        pytest.skip("Python 3.10: the wheel's tomli dependency cannot be installed offline")
    whl = _build_wheel(tmp_path / "dist")
    env = tmp_path / "venv"
    venv.EnvBuilder(with_pip=False, clear=True).create(env)
    py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    # a pure-Python wheel installs by unpacking it into site-packages (no pip, no network)
    r = subprocess.run([str(py), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    with zipfile.ZipFile(whl) as z:
        z.extractall(r.stdout.strip())
    empty = tmp_path / "empty"
    empty.mkdir()
    code = ("import ck3_save_migrator.patches as P; rs = P.rules_from_pack(); "
            "assert len(rs) == 20, len(rs); import ck3_save_migrator, sys; "
            "print(len(rs), ck3_save_migrator.__file__)")
    r = subprocess.run([str(py), "-I", "-c", code], cwd=empty, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    count, where = r.stdout.split()
    assert count == "20" and str(env) in where and str(ROOT) not in where
