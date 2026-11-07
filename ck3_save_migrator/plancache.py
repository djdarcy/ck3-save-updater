"""The checks' verdicts, kept between `status` and `update` (0.4.30; design 2026-11-06 21:10, djdarcy: "I think a lot
of people are going to wonder why they have to redo the same exact process twice").

`status` (and `update`) write each check's verdict for a save to a small file beside the block-index cache. A later
`update` on the same save reuses a verdict only when it says "needed": a stale "needed" only runs a rule that edits
nothing, while a stale "done" could skip a fix, so "done" and "unknown" are always checked again.

The key holds everything a verdict depends on: the save's gamestate (its sha256, so a different save, or the same
file changed, never matches), the tool's own code (its Python files, shipped packs and gene tables), the game it
reads, and every input of the plan. Entries older than a day are swept, the newest few kept, and `ck3update cache
clear` empties them; `[cache] plans = false` turns it off.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import time
from pathlib import Path

from .patches.blockindex import cache_dir as _index_dir

PLAN_CACHE_VERSION = 1             # bump when a verdict's meaning or this file's layout changes
SWEEP_SECONDS = 24 * 3600
KEEP = 4                           # files are KB-sized; a few saves' verdicts are kept
_FINGERPRINT: list = []


def cache_dir() -> Path:
    """Inside the index cache's folder (so ``CK3UPDATE_CACHE_DIR`` moves both, and `cache clear` finds both)."""
    return _index_dir() / "plans"


def code_fingerprint() -> str:
    """The sha256 of the tool's own code and data: every .py, .toml and gene table in the package (any upgrade or
    local edit changes it). Computed once per process."""
    if not _FINGERPRINT:
        root = Path(__file__).resolve().parent
        h = hashlib.sha256()
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in (".py", ".toml", ".txt", ".json") and "__pycache__" not in p.parts:
                h.update(str(p.relative_to(root)).replace("\\", "/").encode())
                h.update(p.read_bytes())
        _FINGERPRINT.append(h.hexdigest())
    return _FINGERPRINT[0]


def _stat(p) -> list:
    """A file's or folder's path, size and modification time (a folder: of every file under it)."""
    if not p:
        return []
    p = Path(p)
    if p.is_file():
        st = p.stat()
        return [str(p), st.st_size, st.st_mtime_ns]
    if p.is_dir():
        return [str(p)] + [[str(f.relative_to(p)), f.stat().st_size, f.stat().st_mtime_ns]
                           for f in sorted(p.rglob("*")) if f.is_file()]
    return [str(p), None]


def plan_key(gamestate: bytes, inputs: dict) -> str:
    """The key of one plan's verdicts: the gamestate's sha256, the code, and ``inputs`` (every plan input; files and
    folders among them are taken by path, size and modification time)."""
    files = {k: _stat(v) for k, v in inputs.items() if k in ("reference", "old_game_dir", "game_dir")}
    folders = {"packs": [_stat(x) for x in inputs.get("packs") or []],
               "user_packs": [_stat(x) for x in inputs.get("user_packs") or []]}
    rest = {k: v for k, v in inputs.items() if k not in files and k not in ("packs", "user_packs")}
    blob = json.dumps({"v": PLAN_CACHE_VERSION, "code": code_fingerprint(),
                       "save": hashlib.sha256(gamestate).hexdigest(), "files": files, "folders": folders,
                       "inputs": rest}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def load(key: str) -> dict | None:
    """The verdicts stored under ``key`` (rule id -> Detection fields), with the time they were made; None when absent,
    older than a day, or unreadable."""
    p = cache_dir() / f"{key}.json"
    try:
        if time.time() - p.stat().st_mtime > SWEEP_SECONDS:
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("v") == PLAN_CACHE_VERSION else None


def save(key: str, verdicts: dict, made_by: str) -> None:
    """Store ``verdicts`` (rule id -> Detection) under ``key``, atomically, and sweep old entries."""
    d = cache_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        body = {"v": PLAN_CACHE_VERSION, "made": time.time(), "by": made_by,
                "verdicts": {rid: dataclasses.asdict(x) for rid, x in verdicts.items()}}
        tmp = d / f"{key}.tmp"
        tmp.write_text(json.dumps(body), encoding="utf-8")
        os.replace(tmp, d / f"{key}.json")
        now = time.time()
        others = sorted((p for p in d.glob("*.json") if p.stem != key), key=lambda p: p.stat().st_mtime, reverse=True)
        for i, old in enumerate(others):
            if i >= KEEP - 1 or now - old.stat().st_mtime > SWEEP_SECONDS:
                old.unlink(missing_ok=True)
    except OSError:
        pass                                            # a cache that cannot be written only costs the next run


def clear() -> tuple[int, int]:
    files = size = 0
    for p in list(cache_dir().glob("*.json")) + list(cache_dir().glob("*.tmp")):
        size += p.stat().st_size
        p.unlink(missing_ok=True)
        files += 1
    return files, size
