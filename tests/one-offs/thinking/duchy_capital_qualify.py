"""For each v17 province with a 1.20 duchy-capital building: would 1.21 let that province have a duchy-capital district?

1.21's can_have_duchy_capital_building_trigger (scripted_triggers/00_building_requirement_triggers.txt:536): the county's
holder holds the province's de jure duchy (a republic instead needs the county as its capital and duchy tier or above).
The district then also needs its own gate: military_duchy_capital_district none beyond that; ducal_residence_district a
household government (feudal, clan, administrative, celestial, meritocratic, the two Japanese).

Prints, per province: the 1.20 building, the county and duchy (1.21's map), the county holder and duchy holder in v19,
the holder's government, and the verdict.

Run: python -I -X utf8 tests/one-offs/thinking/duchy_capital_qualify.py <v19> <1.21 game dir> <province> [<province> ...]
Read-only.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.carry_1_21 import gov_of_landed  # noqa: E402
from ck3_save_migrator.deadtitles import title_tree  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

HOUSEHOLD = {"feudal_government", "clan_government", "administrative_government", "celestial_government",
             "meritocratic_government", "japan_administrative_government", "japan_feudal_government"}


def records(v19, game, pids):
    """[{province, barony, county, duchy, county_holder, duchy_holder, government, allowed, household}] for v19."""
    parent, prov = title_tree(pathlib.Path(game) / "common" / "landed_titles")
    barony_of = {str(p): b for b, p in prov.items()}
    g = read_save(v19).gamestate
    holder = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        body = g[e.open:e.close]
        k = re.search(rb'\bkey="?([a-z_]+)', body)
        h = re.search(rb"\n\tholder=(\d+)", body)
        if k:
            holder[k.group(1).decode()] = h.group(1).decode() if h else None
    living = {e.key.decode(): e for e in gs.iter_entries(g, *gs.locate(g, "living").body) if e.key}
    out = []
    for pid in pids:
        b = barony_of.get(pid)
        c = parent.get(b) if b else None
        d = parent.get(c) if c else None
        ch, dh = holder.get(c), holder.get(d)
        gov = gov_of_landed(g, living[ch]) if ch in living else "?"
        out.append({"province": pid, "barony": b, "county": c, "duchy": d, "county_holder": ch, "duchy_holder": dh,
                    "government": gov, "allowed": ch is not None and ch == dh, "household": gov in HOUSEHOLD})
    return out


def main(v19, game, *pids):
    parent, prov = title_tree(pathlib.Path(game) / "common" / "landed_titles")
    barony_of = {str(p): b for b, p in prov.items()}
    g = read_save(v19).gamestate
    holder = {}
    for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
        body = g[e.open:e.close]
        k = re.search(rb'\bkey="?([a-z_]+)', body)
        h = re.search(rb"\n\tholder=(\d+)", body)   # the entry's own holder, one tab in (heir/claim lists are not)
        if k:
            holder[k.group(1).decode()] = h.group(1).decode() if h else None
    living = {e.key.decode(): e for e in gs.iter_entries(g, *gs.locate(g, "living").body) if e.key}
    for pid in pids:
        b = barony_of.get(pid)
        c = parent.get(b) if b else None
        d = parent.get(c) if c else None
        ch, dh = holder.get(c), holder.get(d)
        gov = gov_of_landed(g, living[ch]) if ch in living else "?"
        ok = ch is not None and ch == dh
        print(f"{pid}: {b} -> {c} -> {d} | county holder {ch}, duchy holder {dh}, government {gov} | "
              f"duchy-capital district allowed: {'YES' if ok else 'no'}"
              + (f"; ducal residence also needs a household government: {'yes' if gov in HOUSEHOLD else 'no'}" if ok else ""))


if __name__ == "__main__":
    main(*sys.argv[1:])
