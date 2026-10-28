"""The player's own settings: a small TOML file the tool owns. For now it holds one thing, the rules turned off.

    disabled = ["R21"]

The file: ``CK3SM_CONFIG`` when set (tests point it at a temporary folder), else
``%APPDATA%\\ck3-save-migrator\\config.toml`` on Windows and ``~/.config/ck3-save-migrator/config.toml`` (or under
``XDG_CONFIG_HOME``) elsewhere. It is read with ``tomllib`` (``tomli`` on Python 3.10) and written by hand, so it
needs no new dependency. A missing file means nothing is turned off.

A turned-off rule is left out of ``--rules all`` in ``migrate`` and ``check``; naming it in ``--rules`` still runs it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .patches.model import tomllib

APP = "ck3-save-migrator"


def config_path() -> Path:
    given = os.environ.get("CK3SM_CONFIG")
    if given:
        return Path(given)
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / APP / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / APP / "config.toml"


def read_config(path: Path | None = None) -> dict:
    path = path or config_path()
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: not valid TOML ({exc}); fix or delete it") from None
    disabled = data.get("disabled", [])
    if not isinstance(disabled, list) or not all(isinstance(x, str) for x in disabled):
        raise ValueError(f"{path}: 'disabled' must be a list of rule ids, such as [\"R21\"]")
    return data


def disabled_ids(path: Path | None = None) -> list[str]:
    return list(read_config(path).get("disabled", []))


def write_disabled(ids: list[str], path: Path | None = None) -> Path:
    """Write the list of turned-off ids (sorted, without repeats); returns the file written."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = ", ".join(json.dumps(i) for i in sorted(set(ids), key=_order))   # JSON strings are TOML strings
    path.write_text("# ck3-save-migrator settings; change with `ck3-save-migrator enable/disable <id>`\n"
                    f"disabled = [{items}]\n", encoding="utf-8")
    return path


def _order(rule_id: str):
    digits = rule_id[1:]
    return (rule_id[:1], int(digits) if digits.isdigit() else 0, rule_id)
