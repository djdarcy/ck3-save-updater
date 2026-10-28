"""The optional ``tools`` add-on: list and run a folder of standalone scripts exactly as they are.

Each ``*.py`` file in the scripts folder (not recursive) is one tool, named by its file's stem; its description is
the first line of its module docstring, read with ``ast`` (a script is never imported or run to list it). A tool runs
through dazzlecmd-lib's aggregator engine as its own process, ``[python, <script>] + args``, from the caller's
working directory, and its exit code is the command's. Nothing is copied, rewritten or added next to the scripts:
the engine is pointed at a "shadow kit" generated in a cache folder on every call.

dazzlecmd-lib is imported only when a tool is run (``engine``); the rest of the package never imports it. The
scripts folder: ``--scripts-dir``, else ``CK3SM_SCRIPTS_DIR``, else the ``tests/one-offs`` folder of the source
checkout the package is running from.
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

APP = "ck3-save-migrator"
KIT = "oneoffs"
MANIFEST = ".ck3sm-tool.json"
INSTALL_HINT = f'the tools add-on needs dazzlecmd-lib: pip install "{APP}[tools]"'


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
    if folder.is_dir() and project.is_file() and f'name = "{APP}"' in project.read_text(encoding="utf-8"):
        return folder
    return None


def scripts_dir(explicit: str | None = None) -> Path | None:
    """The scripts folder: ``explicit``, else ``CK3SM_SCRIPTS_DIR``, else the source checkout's ``tests/one-offs``."""
    given = explicit or os.environ.get("CK3SM_SCRIPTS_DIR")
    if given:
        return Path(given)
    return checkout_scripts_dir()


def cache_dir(explicit: str | None = None) -> Path:
    """Where the shadow kit is generated: ``explicit``, else ``CK3SM_TOOLS_CACHE``, else the user cache folder."""
    given = explicit or os.environ.get("CK3SM_TOOLS_CACHE")
    if given:
        return Path(given)
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / APP / "tools"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / APP / "tools"


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


def shadow_kit(tools: list[Tool], cache: Path) -> Path:
    """(Re)generate the shadow kit for ``tools`` under ``cache``; returns its project root. Only ``cache`` is
    written: the scripts themselves are referenced by absolute path, never copied."""
    root = cache / "shadow"
    if root.exists():
        shutil.rmtree(root)
    (root / "kits").mkdir(parents=True)
    kit = {"name": KIT, "description": "standalone scripts, run as they are", "always_active": True,
           "tools_dir": "tools", "manifest": MANIFEST, "tools": [f"{KIT}:{t.name}" for t in tools]}
    (root / "kits" / f"{KIT}.kit.json").write_text(json.dumps(kit, indent=2), encoding="utf-8")
    for t in tools:
        d = root / "tools" / KIT / t.name
        d.mkdir(parents=True)
        manifest = {"name": t.name, "description": t.description, "pass_through": True,
                    "runtime": {"type": "python", "script_path": str(t.path)}}
        (d / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root


def engine(tools: list[Tool], cache: Path):
    """dazzlecmd-lib's aggregator engine over a fresh shadow kit. ImportError when the library is missing."""
    from dazzlecmd_lib import AggregatorEngine        # the only import of dazzlecmd-lib in the package
    root = shadow_kit(tools, cache)
    return AggregatorEngine(name=f"{APP}-tools", command=f"{APP} tools", tools_dir="tools", kits_dir="kits",
                            manifest=MANIFEST, config_dir=str(cache / "config"), project_root=str(root))


def run(folder: Path, cache: Path, name: str, args: list[str]) -> int:
    """Run tool ``name`` with ``args``; its exit code."""
    tools = list_tools(folder)
    if name not in {t.name for t in tools}:
        find(folder, name)                              # raises, naming it
    rc = engine(tools, cache).run([name, *args])
    return int(rc or 0)


def library_available() -> bool:
    try:
        import dazzlecmd_lib  # noqa: F401
    except ImportError:
        return False
    return True
