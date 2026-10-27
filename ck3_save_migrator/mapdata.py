"""The target game's map facts a migration needs: which provinces are impassable.

1.20's map rework made some 1.8.1 land provinces impassable (Tibet, the Ordos: province 9542 among them). A map
unit standing on one has no barony to be filed under, and the game crashes when it files the unit (2026-10-27,
the 989.1.1 crash at ck3+0xb064e8). ``map_data/default.map`` lists them as ``impassable_mountains`` and
``impassable_seas``, each a ``LIST { ... }`` or a ``RANGE { first last }``.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_CLASS = re.compile(r"(?m)^\s*(impassable_mountains|impassable_seas)\s*=\s*(LIST|RANGE)\s*\{([^}]*)\}")


def parse_impassable(text: str) -> frozenset[int]:
    out: set[int] = set()
    for _kind, form, body in _CLASS.findall(re.sub(r"#[^\n]*", "", text)):
        nums = [int(x) for x in body.split()]
        if form == "LIST":
            out.update(nums)
        elif len(nums) == 2:
            out.update(range(nums[0], nums[1] + 1))
    return frozenset(out)


_BARONY = re.compile(r"(?<![\w.])(b_[\w\-']+)\s*=\s*\{[^{}]*?\bprovince\s*=\s*(\d+)")


@lru_cache(maxsize=4)
def barony_provinces(game_dir: Path) -> dict[str, int]:
    """Barony key -> its province, from the game's ``common/landed_titles``: a barony is ``b_x = { province = N }``."""
    out: dict[str, int] = {}
    d = Path(game_dir) / "common" / "landed_titles"
    for f in sorted(d.glob("*.txt")) if d.exists() else []:
        text = re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))
        out.update((m.group(1), int(m.group(2))) for m in _BARONY.finditer(text))
    return out


@lru_cache(maxsize=4)
def impassable_provinces(game_dir: Path) -> frozenset[int]:
    """The impassable provinces of the game in ``game_dir`` (its ``game`` folder); empty when it has no map."""
    f = Path(game_dir) / "map_data" / "default.map"
    return parse_impassable(f.read_text(encoding="utf-8-sig", errors="replace")) if f.exists() else frozenset()
