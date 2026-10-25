"""Unit 3 (R14) input: which baronies changed province between the save's game version and 1.20?

Re-measures the design's 10-move fix list (G1, measured on a 2022 vanilla copy) against the 1.8.2 game files the
ladder downloaded (private/data/versions/1.8.2/game) and the installed 1.20 game. 1.8.2 is the patch after the
save's 1.8.1. Prints the moved baronies (old province -> new province), each province's 1.20 barony, and the
chains (a vacated province taken by another moved barony, a swap).

Usage: python -I tests/one-offs/measure_unit3_moved_baronies.py <old game dir> <new game dir>
"""
import re
import sys
from pathlib import Path

RX = re.compile(r"\b(b_[\w\-']+)\s*=\s*\{|\bprovince\s*=\s*(\d+)")


def barony_provinces(game: Path) -> dict[str, int]:
    out, cur = {}, None
    for f in sorted((game / "common" / "landed_titles").glob("*.txt")):
        t = re.sub(r"#[^\n]*", "", f.read_text(encoding="utf-8-sig", errors="replace"))
        for m in RX.finditer(t):
            if m.group(1):
                cur = m.group(1)
            elif cur:
                out.setdefault(cur, int(m.group(2)))
                cur = None
    return out


def main():
    old, new = barony_provinces(Path(sys.argv[1])), barony_provinces(Path(sys.argv[2]))
    by_prov_new = {p: b for b, p in new.items()}
    both = old.keys() & new.keys()
    moved = sorted((b, old[b], new[b]) for b in both if old[b] != new[b])
    print(f"old baronies {len(old):,}, new {len(new):,}, in both {len(both):,}, same province "
          f"{len(both) - len(moved):,}, moved {len(moved)}; old max province {max(old.values())}, new {max(new.values())}")
    for b, o, n in moved:
        print(f"  {b:24} {o:>6} -> {n:<6}  1.20 barony now on {o}: {by_prov_new.get(o, '(none: wasteland/sea)')}")
    gone = sorted(b for b in old if b not in new)
    print(f"baronies only in old: {len(gone)}")


if __name__ == "__main__":
    main()
