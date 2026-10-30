"""The player's own settings: a small TOML file the tool owns. It holds the rules turned off, extra folders of the
player's own packs, and the code packs the player trusts (each with the hash of its files when trusted):

    disabled = ["R21"]
    pack_dirs = ["D:/my ck3 packs"]

    [trusted]
    "my_fixes" = "<sha256 of the pack folder's files>"

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

APP = "ck3-save-migrator"      # the folder keeps its name from before the rename, so an existing config keeps working


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
    for key, what in (("disabled", "rule ids, such as [\"R21\"]"), ("pack_dirs", "folders, such as [\"D:/packs\"]")):
        val = data.get(key, [])
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ValueError(f"{path}: '{key}' must be a list of {what}")
    trusted = data.get("trusted", {})
    if not isinstance(trusted, dict) or not all(isinstance(v, str) for v in trusted.values()):
        raise ValueError(f"{path}: 'trusted' must be a table of pack id = \"<hash>\"")
    return data


def disabled_ids(path: Path | None = None) -> list[str]:
    return list(read_config(path).get("disabled", []))


def pack_dirs(path: Path | None = None) -> list[str]:
    """The extra folders of the player's own packs (``pack_dirs``), as written."""
    return list(read_config(path).get("pack_dirs", []))


def trusted_packs(path: Path | None = None) -> dict[str, str]:
    """pack id -> the hash of its files when the player trusted it (``ck3update trust``)."""
    return dict(read_config(path).get("trusted", {}))


def write_config(data: dict, path: Path | None = None) -> Path:
    """Write the settings this tool knows (``disabled``, ``pack_dirs``, ``trusted``); returns the file written. The
    file is written by hand (no TOML writer is needed): JSON strings are TOML strings."""
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    disabled = ", ".join(json.dumps(i) for i in sorted(set(data.get("disabled", [])), key=_order))
    lines = ["# ck3-save-updater settings; change with `ck3update enable/disable <id>` and `ck3update trust/untrust "
             "<pack id>`", f"disabled = [{disabled}]"]
    if data.get("pack_dirs"):
        lines.append(f"pack_dirs = [{', '.join(json.dumps(d) for d in data['pack_dirs'])}]")
    if data.get("trusted"):
        lines += ["", "[trusted]"] + [f"{json.dumps(k)} = {json.dumps(v)}" for k, v in sorted(data["trusted"].items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_disabled(ids: list[str], path: Path | None = None) -> Path:
    """Write the list of turned-off ids (sorted, without repeats), keeping the other settings; returns the file."""
    return write_config({**read_config(path), "disabled": ids}, path)


def write_trusted(trusted: dict[str, str], path: Path | None = None) -> Path:
    """Write the trusted packs, keeping the other settings; returns the file written."""
    return write_config({**read_config(path), "trusted": trusted}, path)


def _order(rule_id: str):
    digits = rule_id[1:]
    return (rule_id[:1], int(digits) if digits.isdigit() else 0, rule_id)
