"""The player's own settings: a small TOML file the tool owns. It holds the rules turned off, extra folders of the
player's own packs, and the code packs the player trusts (each with the hash of its files when trusted):

    disabled = ["R21"]
    pack_dirs = ["D:/my ck3 packs"]

    [display]
    gap = 2              # spaces between a header and its field names in status's output
    spacing = "compact"  # "compact" (no blank lines, the default) or "blank" (a blank line between blocks)
    align = "flow"       # "flow" (the default), "global" or "blocks": see docs/config.md

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
    if data.get("transplant", "off") not in ("auto", "off"):
        raise ValueError(f"{path}: 'transplant' must be \"auto\" or \"off\"")
    trusted = data.get("trusted", {})
    if not isinstance(trusted, dict) or not all(isinstance(v, str) for v in trusted.values()):
        raise ValueError(f"{path}: 'trusted' must be a table of pack id = \"<hash>\"")
    display = data.get("display", {})
    if not isinstance(display, dict):
        raise ValueError(f"{path}: 'display' must be a table ([display])")
    gap = display.get("gap", DISPLAY["gap"])
    if not isinstance(gap, int) or isinstance(gap, bool) or not 1 <= gap <= 8:
        raise ValueError(f"{path}: [display] gap must be a whole number of spaces from 1 to 8")
    for key, allowed in (("spacing", SPACINGS), ("align", ALIGNS)):
        if display.get(key, DISPLAY[key]) not in allowed:
            raise ValueError(f"{path}: [display] {key} must be one of {', '.join(json.dumps(s) for s in allowed)}")
    cache = data.get("cache", {})
    if not isinstance(cache, dict) or not isinstance(cache.get("index", False), bool):
        raise ValueError(f"{path}: [cache] index must be true or false")
    return data


def index_cache_on(path: Path | None = None) -> bool:
    """``[cache] index = true``: keep each save's block index in a temp folder the tool names, so the next command on
    the same unchanged save skips the build. Off unless the player turns it on (the tool writes nothing unasked)."""
    return bool(read_config(path).get("cache", {}).get("index", False))


# how status and update lay out their blocks ([display], docs/config.md): the spaces after a header, whether a blank
# line separates the blocks ("blank") or not ("compact"), and how the blocks' value columns line up (plan.value_columns)
DISPLAY = {"gap": 2, "spacing": "compact", "align": "flow"}       # djdarcy's pick, 2026-11-01
SPACINGS = ("blank", "compact")
ALIGNS = ("blocks", "global", "flow")


def display_settings(path: Path | None = None) -> dict:
    """The [display] settings, each defaulted: ``gap`` and ``spacing``."""
    return {**DISPLAY, **read_config(path).get("display", {})}


def disabled_ids(path: Path | None = None) -> list[str]:
    return list(read_config(path).get("disabled", []))


def pack_dirs(path: Path | None = None) -> list[str]:
    """The extra folders of the player's own packs (``pack_dirs``), as written."""
    return list(read_config(path).get("pack_dirs", []))


def transplant_mode(path: Path | None = None) -> str:
    """``transplant = "auto"`` lets ``update`` select the new-map rules when a save needs them; "off" otherwise."""
    return read_config(path).get("transplant", "off")


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
    if data.get("transplant"):
        lines.append(f"transplant = {json.dumps(data['transplant'])}")
    if data.get("cache"):            # kept as written: the player's own cache choice
        lines += ["", "[cache]"] + [f"{k} = {json.dumps(v)}" for k, v in data["cache"].items()]
    if data.get("display"):          # kept as written: the player's own layout choices
        lines += ["", "[display]"] + [f"{k} = {json.dumps(v)}" for k, v in data["display"].items()]
    if data.get("trusted"):
        lines += ["", "[trusted]"] + [f"{json.dumps(k)} = {json.dumps(v)}" for k, v in sorted(data["trusted"].items())]
    atomic_write(path, "\n".join(lines) + "\n")
    return path


def atomic_write(path: Path, text: str) -> None:
    """Write ``text`` (UTF-8) so that a crash, a full disk or a kill mid-write leaves the old file whole:
    dazzle-filekit writes a ``.tmp`` file beside it and renames it over the target. Newlines are translated as
    ``Path.write_text`` does, so the bytes are the same. Imported here, not at the top: it costs about 0.1 s, and
    most commands never write."""
    from dazzle_filekit.operations import atomic_write_text
    atomic_write_text(path, text, encoding="utf-8")


def write_disabled(ids: list[str], path: Path | None = None) -> Path:
    """Write the list of turned-off ids (sorted, without repeats), keeping the other settings; returns the file."""
    return write_config({**read_config(path), "disabled": ids}, path)


def write_trusted(trusted: dict[str, str], path: Path | None = None) -> Path:
    """Write the trusted packs, keeping the other settings; returns the file written."""
    return write_config({**read_config(path), "trusted": trusted}, path)


def _order(rule_id: str):
    digits = rule_id[1:]
    return (rule_id[:1], int(digits) if digits.isdigit() else 0, rule_id)
