"""unheld_duchy_risk: the setups the game's "which kingdom is this unheld title in" routine (ck3+0x23186e0) can loop
on, counted per save.

The routine, for a title with no holder, takes the first of its counties and climbs each title's liege title until
it reaches the target tier; a county whose holder has no liege has itself as its liege title, so the climb never
ends (2026-10-27: c_kuzeytorg, first and only county of the unheld d_tana, after its count Liber went independent).

Counts, for every unheld duchy (and kingdom): the first de jure county, whether it is held, whether its holder's
highest title is that county's tier (a count), and whether that holder is today independent (no vassal contract as a
vassal). "At risk" = held by a count; "loops now" = held by an independent count.

Usage: python -I tests/one-offs/unheld_duchy_risk.py <save.ck3> [<save.ck3> ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import shape_diff as P  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402

TIER = {"b": 1, "c": 2, "d": 3, "k": 4, "e": 5}


def main():
    for path in sys.argv[1:]:
        g = P.load(path)
        titles = {}
        for e in gs.iter_entries(g, *gs.locate(g, "landed_titles/landed_titles").body):
            if not (e.key and e.key.isdigit()):
                continue
            s = g[e.start:e.end]
            k = re.search(rb'\n\tkey="?([^"\s]+)', s)
            h = re.search(rb"\n\tholder=(\d+)", s)
            v = re.search(rb"de_jure_vassals=\{([^}]*)\}", s)
            titles[e.key.decode()] = {"key": k.group(1).decode() if k else "?", "holder": h.group(1).decode() if h else None,
                                      "vassals": v.group(1).split() if v else []}
        top = {}                                       # holder -> highest tier held
        for t in titles.values():
            if t["holder"] and t["key"][0] in TIER:
                top[t["holder"]] = max(top.get(t["holder"], 0), TIER[t["key"][0]])
        vc = gs.find_section(g, "vassal_contracts")
        vassals = set(re.findall(rb"\n\t+vassal=(\d+)", g[vc.open:vc.close]))
        rows = {"unheld duchies/kingdoms": 0, "first county held by a count": 0, "... and that count independent": 0}
        examples = []
        for i, t in titles.items():
            if t["key"][0] not in "dk" or t["holder"] or not t["vassals"]:
                continue
            rows["unheld duchies/kingdoms"] += 1
            first = t["vassals"][0].decode()
            # for a kingdom the first vassal is a duchy: descend to its first county
            while first in titles and titles[first]["key"][0] == "d" and titles[first]["vassals"]:
                first = titles[first]["vassals"][0].decode()
            c = titles.get(first)
            if not c or c["key"][0] != "c" or not c["holder"]:
                continue
            if top.get(c["holder"]) == 2:
                rows["first county held by a count"] += 1
                if c["holder"].encode() not in vassals:
                    rows["... and that count independent"] += 1
                    examples.append(f"{t['key']} -> {c['key']} (holder {c['holder']})")
        print(f"== {Path(path).name}: " + "; ".join(f"{k} {v}" for k, v in rows.items()))
        for x in examples[:15]:
            print("     loops now: " + x)


if __name__ == "__main__":
    main()
