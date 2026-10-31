"""The ``tools`` add-on: list and run a folder of standalone scripts exactly as they are.

Each ``*.py`` file in the scripts folder (not recursive) is one tool, named by its file's stem; its description is
the first line of its module docstring, read with ``ast`` (a script is never imported or run to list it). A tool
runs as its own process, ``[python, <script>] + args`` (``script_command``), from the caller's working directory,
with the caller's input and output, and its exit code is the command's. It always runs as a file, never with
``-m``, whatever else the folder holds (an ``__init__.py`` included). Nothing is copied, rewritten or written
anywhere. A run patch's ``tool =`` builds its command with the same ``script_command``.

The scripts folder: ``--scripts-dir``, else ``CK3SM_SCRIPTS_DIR``, else the ``tests/one-offs`` folder of the source
checkout the package is running from.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DIST = "ck3-save-updater"      # the distribution (pip) name


class ToolsError(Exception):
    """A tools request that cannot be carried out (exit code 2)."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    path: Path


def checkout_scripts_dir() -> Path | None:
    """``tests/one-offs`` of the source checkout this package runs from, when it does (an installed wheel has
    none)."""
    root = Path(__file__).resolve().parents[1]
    project = root / "pyproject.toml"
    folder = root / "tests" / "one-offs"
    if folder.is_dir() and project.is_file() and f'name = "{DIST}"' in project.read_text(encoding="utf-8"):
        return folder
    return None


def scripts_dir(explicit: str | None = None) -> Path | None:
    """The scripts folder: ``explicit``, else ``CK3SM_SCRIPTS_DIR``, else the source checkout's ``tests/one-offs``."""
    given = explicit or os.environ.get("CK3SM_SCRIPTS_DIR")
    if given:
        return Path(given)
    return checkout_scripts_dir()


def description(path: Path) -> str:
    """The first line of a script's module docstring, read without importing it; "" when it has none."""
    try:
        doc = ast.get_docstring(ast.parse(path.read_bytes(), filename=str(path)))
    except (SyntaxError, ValueError, UnicodeDecodeError, OSError):
        return ""
    return doc.strip().splitlines()[0].strip() if doc and doc.strip() else ""


def list_tools(folder: Path) -> list[Tool]:
    """One tool per ``*.py`` file directly in ``folder``, sorted by name."""
    if not folder.is_dir():
        raise ToolsError(f"the scripts folder does not exist: {folder}")
    return [Tool(p.stem, description(p), p.resolve()) for p in sorted(folder.glob("*.py")) if p.is_file()]


def find(folder: Path, name: str) -> Tool:
    for t in list_tools(folder):
        if t.name == name:
            return t
    raise ToolsError(f"no tool named {name!r} in {folder} (no {name}.py there; `tools list` shows them)")


def script_command(script: Path, args) -> list[str]:
    """The command that runs one script: the running Python, the script's path, then ``args``. Always a file,
    never ``-m``."""
    return [sys.executable, str(script), *[str(a) for a in args]]


def run_script(script: Path, args, *, cwd=None, **kw) -> int:
    """Run ``script`` with ``args`` as its own process (from ``cwd``, by default the caller's folder, with the
    caller's input and output unless ``kw`` says otherwise); its exit code."""
    return subprocess.run(script_command(script, args), cwd=cwd, **kw).returncode


def run(folder: Path, name: str, args: list[str]) -> int:
    """Run tool ``name`` with ``args``; its exit code."""
    return run_script(find(folder, name).path, args)
