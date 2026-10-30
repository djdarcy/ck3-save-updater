"""ids: split a save id into its slot and generation, and translate ids between two saves' id spaces.

A CK3 id is a SLOT in the low 24 bits and a GENERATION in the high 8: a freed slot is reused with the previous
occupant's generation + 1. ``NONE`` (0xFFFFFFFF) is the game's "no id"; some fields write it 64 bits wide
(``NONE64``, 18446744073709551615), so ``NONES`` holds both and ``is_none`` tests for either. Two saves of one lineage can number the
same object differently; a translation between their id spaces is always an explicit step (``offset_by_mode``
finds one, ``translate`` applies it), never assumed.
"""
from __future__ import annotations

from collections import Counter
from typing import Hashable, TypeVar

LOW = 0xFFFFFF
GEN = 0xFF000000
NONE = 0xFFFFFFFF
NONE64 = 0xFFFFFFFFFFFFFFFF
NONES = frozenset({NONE, NONE64})

K = TypeVar("K", bound=Hashable)


def is_none(i: int) -> bool:
    """True for the game's "no id", 32 or 64 bits wide."""
    return i in NONES


def slot(i: int) -> int:
    """The slot index: the low 24 bits."""
    return i & LOW


def generation(i: int) -> int:
    """The generation: the high 8 bits, shifted down (0 to 255)."""
    return (i & GEN) >> 24


def make(slot_: int, generation_: int) -> int:
    """The id of ``slot_`` under ``generation_``; ``make(slot(i), generation(i)) == i`` for any 32-bit id."""
    return ((generation_ & 0xFF) << 24) | (slot_ & LOW)


def translate(i: int, offset: int) -> int:
    """``i`` with its slot shifted by ``offset`` and its generation kept.

    The caller keeps the shifted slot inside 24 bits; a slot pushed outside them is masked, not carried into the
    generation."""
    return (i & GEN) | ((slot(i) + offset) & LOW)


def offset_by_mode(a: dict[K, int], b: dict[K, int]) -> tuple[int | None, set[K]]:
    """The slot offset that carries most of ``a``'s ids onto ``b``'s, and the keys it carries.

    Over the keys both maps share whose two ids have the same generation, count ``slot(b[k]) - slot(a[k])``; the
    most common difference is the offset, returned with the set of keys at exactly that difference. On a tie the
    SMALLEST offset wins (deterministic; ``Counter.most_common`` would pick by insertion order). ``(None, set())``
    when no key is shared at the same generation.
    """
    diffs: Counter = Counter()
    for k, ia in a.items():
        ib = b.get(k)
        if ib is None or (ia & GEN) != (ib & GEN):
            continue
        diffs[slot(ib) - slot(ia)] += 1
    if not diffs:
        return None, set()
    top = max(diffs.values())
    off = min(d for d, n in diffs.items() if n == top)
    return off, {k for k, ia in a.items()
                 if k in b and (ia & GEN) == (b[k] & GEN) and slot(b[k]) - slot(ia) == off}
