"""Field baselines: per game version, which fields each kind of entry in a game-written save carries.

A baseline records the STRUCTURE of a save, never its values: for each database (``faiths/database``, ``living``,
``vassal_contracts/database``...) the number of entries, and for each depth-1 field the share of entries that carry it
and the share that leave it empty. Values belong to one bookmark moment; which fields exist is stable per game
version (djdarcy, 2026-11-16: "relying on just a snapshot of data entries is dangerous but the STRUCTURE of that data
should be stable per game version").

The lint's field check compares a migrated save's entries against the reference save when one is given, and against
the shipped baseline for the save's version otherwise, so a player with no reference save still gets the check. A
baseline for a new game version is made from any save that version wrote: ``scripts/make_field_baseline.py``.

Design: the 10-30 generic-updater DWP, step 5 (decided, never built until 0.5.20); the carried-fields goal, S2.
"""
from __future__ import annotations

import json
from importlib import resources

from ._vendor.savediff import keys as K
from ._vendor.savediff import text as T
from .discover import save_versions

FORMAT = 1
_ROUND = 4


def game_version(g: bytes) -> str | None:
    """The game version a gamestate says it was written by (``meta_data``'s ``version=``), or None."""
    return save_versions(g[:65536])["version"]


def build_baseline(g: bytes, min_entries: int = 20) -> dict:
    """The baseline of one game-written gamestate: ``{"format", "game_version", "databases": {path: {"entries": n,
    "fields": {name: [share_present, share_empty]}}}}``. Field names and shares only; deterministic (sorted keys,
    shares rounded to four places)."""
    idx = T.SectionIndex(g)
    dbs: dict = {}
    for path in sorted(K.database_paths(g, idx, min_entries)):
        cov = K.field_coverage(g, idx, path)
        n = cov["entries"]
        if not n:
            continue
        dbs[path] = {"entries": n,
                     "fields": {k: [round(f["present"] / n, _ROUND), round(f["empty"] / n, _ROUND)]
                                for k, f in sorted(cov["fields"].items())}}
    return {"format": FORMAT, "game_version": game_version(g), "databases": dbs}


def dumps(baseline: dict) -> str:
    """The baseline as the bytes it is shipped as: sorted, one database per block, a final newline."""
    return json.dumps(baseline, indent=1, sort_keys=True) + "\n"


def load_baseline(version: str | None) -> dict | None:
    """The shipped baseline for ``version`` (``"1.20.1.2"``), or None when none ships for it."""
    if not version:
        return None
    try:
        f = resources.files("ck3_save_migrator").joinpath("baselines", version, "fields.json")
        if not f.is_file():
            return None
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def added_fields(old: str, new: str, path: str) -> tuple[bytes, ...]:
    """The fields ``new``'s baseline has at ``path`` (``"provinces"``) that ``old``'s lacks, sorted; () when either
    baseline or the database is missing. A version's shape change, computed from two shipped baselines instead of
    written by hand (the F7 audit, refactor-advisor's row 5, 2026-11-18)."""
    a, b = load_baseline(old), load_baseline(new)
    if not a or not b or path not in a["databases"] or path not in b["databases"]:
        return ()
    return tuple(sorted(k.encode() for k in set(b["databases"][path]["fields"]) - set(a["databases"][path]["fields"])))


def shipped_versions() -> list[str]:
    """The game versions a baseline ships for."""
    try:
        root = resources.files("ck3_save_migrator").joinpath("baselines")
        return sorted(p.name for p in root.iterdir() if p.joinpath("fields.json").is_file())
    except (OSError, FileNotFoundError):
        return []


def as_coverage(baseline: dict, path: str) -> dict:
    """One database of a baseline in the shape of ``savediff.keys.field_coverage``, so ``coverage_gaps`` can take it
    as the witness. Counts are rebuilt from the shares; there are no example ids in a baseline."""
    db = baseline.get("databases", {}).get(path)
    if not db:
        return {"path": path, "entries": 0, "unparsed": 0, "first": [], "fields": {}}
    n = db["entries"]
    return {"path": path, "entries": n, "unparsed": 0, "first": [],
            "fields": {k: {"present": round(p * n), "empty": round(e * n), "missing_examples": [],
                           "empty_examples": []} for k, (p, e) in db["fields"].items()}}
