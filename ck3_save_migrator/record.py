"""The record of one save game: what each update did to it, read back to pre-fill the next update.

A campaign is updated more than once (a newer save of the same ruler, the next game version). Its saves share the
gamestate's top-level ``random_seed`` (carried by this tool's migration and kept by the game through play), so the
record is keyed by it: ``<config dir>/games/<random_seed>.toml``, beside the config file (``CK3SM_CONFIG`` moves
both). It is written after every successful ``update`` (never by ``--dry-run``, ``status`` or ``migrate``),
atomically, and holds:

    label = "My_Old_Campaign"           # the first update's original save file name, kept
    seed = 494202972

    [[update]]                          # one row per update, the newest last
    date = "2026-11-01T02:00:00+01:00"
    input = "..."                       # and input_sha256
    output = "..."                      # and output_sha256 (other_outputs when a custom faith gave two)
    tool = "ck3-save-updater 0.3.17"
    game_version = "1.20.1.2"
    patches = [{ id = "R1", pack = "to_1_20" }, ...]
    inputs = { vars = { "G1.witness" = "..." }, old_game_dir = "...", transplant = "auto", wos_shape = "faith" }
    prefilled = ["--var G1.witness"]    # which of the inputs came from the record, not the command line

``inputs`` are the ones the update used, whether given or pre-filled, so the newest row always holds every input
for the next update. A reference save is never recorded (it belongs to one date), nor any part of a save.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from .config import atomic_write, config_path
from .patches.model import tomllib

INPUT_KEYS = ("vars", "old_game_dir", "transplant", "wos_shape", "portraits_version")


def games_dir() -> Path:
    return config_path().parent / "games"


def record_path(seed: str) -> Path:
    return games_dir() / f"{seed}.toml"


def read_record(seed: str | None) -> dict | None:
    """The record of the save game with this ``random_seed``, or None (no seed, no record, or an unreadable one)."""
    if not seed:
        return None
    path = record_path(seed)
    if not path.is_file():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data if isinstance(data.get("update"), list) else None


def latest_inputs(rec: dict | None) -> dict:
    """The newest row's inputs (empty without a record)."""
    rows = (rec or {}).get("update") or []
    return dict(rows[-1].get("inputs") or {}) if rows else {}


def summary(rec: dict) -> str:
    rows = rec["update"]
    last = rows[-1]
    when = str(last.get("date", "?"))[:16].replace("T", " ")
    return (f"{rec.get('label', '?')}: last updated {when} by {last.get('tool', '?')} from "
            f"{Path(str(last.get('input', '?'))).name} ({len(rows)} update{'s' if len(rows) != 1 else ''})")


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{json.dumps(str(k))} = {_val(x)}" for k, x in v.items() if x is not None) + " }"
    return json.dumps(str(v))                       # a JSON string is a TOML basic string


def to_toml(rec: dict) -> str:
    lines = ["# ck3update's record of one save game: what each update did to it (docs/updating-a-save.md)",
             f"label = {_val(rec['label'])}", f"seed = {_val(rec['seed'])}"]
    for row in rec["update"]:
        lines += ["", "[[update]]"] + [f"{k} = {_val(v)}" for k, v in row.items() if v is not None]
    return "\n".join(lines) + "\n"


def append_update(seed: str, label: str, row: dict) -> Path:
    """Add one update row to the save game's record (made with ``label`` the first time), atomically."""
    rec = read_record(seed) or {"label": label, "seed": int(seed) if str(seed).isdigit() else seed, "update": []}
    rec["update"] = list(rec["update"]) + [row]
    path = record_path(seed)
    atomic_write(path, to_toml(rec))
    return path


def now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")
