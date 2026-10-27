"""units_off_impassable: move map units standing on a province the target game makes impassable back to the
province they came from (prev=), and drop their unfinished path. Writes a new file; never in place.

2026-10-27: play5 (the hand-back on) crashed at 989.1.1 at ck3+0xb064e8, writing through a province's +0x848
pointer when an army's owner became valid. Unit 1744830531 (owner 16835700, a campaign ruler the hand-back gives
land back to) stands on province 9542, which 1.20's map lists in impassable_mountains (it was land in 1.8.1); with
its owner landless (play5a) the game never files the unit, with him landed it does, and 9542 has no barony.

Usage: python -I tests/one-offs/units_off_impassable.py <in.ck3> <out.ck3> <game dir>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def impassable(game: Path) -> set[int]:
    text = (game / "map_data" / "default.map").read_text(encoding="utf-8-sig", errors="replace")
    out: set[int] = set()
    for kind, form, body in re.findall(r"(?m)^\s*(impassable_mountains|impassable_seas)\s*=\s*(LIST|RANGE)\s*\{([^}]*)\}",
                                       text):
        nums = [int(x) for x in body.split()]
        out |= set(nums) if form == "LIST" else set(range(nums[0], nums[1] + 1))
    return out


def main():
    src, dst, game = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    bad = impassable(game)
    save = sf.read_save(src)
    g = save.gamestate
    ep = gs.EditPass()
    moved = []
    for e in gs.iter_entries(g, *gs.find_section(g, "units").body):
        t = g[e.start:e.end]
        loc = re.search(rb"\n\t+location=(\d+)", t)
        if not loc or int(loc.group(1)) not in bad:
            continue
        prev = re.search(rb"\n\t+prev=(\d+)", t)
        to = int(prev.group(1)) if prev and int(prev.group(1)) not in bad else None
        if to is None:
            print(f"  unit {e.key.decode()} on {loc.group(1).decode()}: no passable prev, left")
            continue
        new = t[:loc.start(1)] + str(to).encode() + t[loc.end(1):]
        new = re.sub(rb"\n\t+(path=\{[^}]*\}|total_cost=[\d.]+|movement_progress=[\d.]+)", b"", new)
        ep.add(gs.Edit(e.start, e.end, new, "units", "off impassable"))
        moved.append((e.key.decode(), int(loc.group(1)), to))
    ep.apply_to(save)
    sf.write_save(save, dst, force=True)
    print(f"wrote {dst}: {len(bad)} impassable provinces; moved {len(moved)} unit(s): {moved}")


if __name__ == "__main__":
    main()
