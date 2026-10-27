"""family_faces: which faces of the player's family come from where, and who has none (djdarcy, 2026-10-26: "the old
save ... undoubtedly has characters that didn't exist in the later save and it would be a shame if the genetics got
messed up for those new characters especially from the playable family").

For the player's dynasty (and, for scale, everyone), on a save after the face step:
  * original face: the person is in the 967 save with a face (the face carried is the 967 one);
  * 2023-only face: not in the 967 save with a face (born after it, or faceless there), face from the 1.8.1 save;
  * no face: no stored DNA at all, so the game generates one from the ethnicity on load.
And for the 2023-only family faces: how many have a parent whose face was restored from 967. Those children
inherited their genes in play from the parent's later, rerolled face, so they may look less like the restored
parent than they did in 2023.

Usage: python -I tests/one-offs/family_faces.py <after-face-step.ck3> <967 witness.ck3> [player id]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import dna_whole_save as W  # noqa: E402
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

HOUSE = re.compile(rb"\n\tdynasty_house=(\d+)")
CHILD = re.compile(rb"\n\t\tchild=\{([^}]*)\}")


def main():
    out_p, wit_p = sys.argv[1:3]
    player = sys.argv[3] if len(sys.argv) > 3 else "50822"
    g = sf.read_save(out_p).gamestate
    ours = W.people(g, with_entries=True)
    wit = W.people(sf.read_save(wit_p).gamestate)
    house, parents = {}, {}
    for cid, r in ours.items():
        body = g[r["start"]:r["end"]]
        m = HOUSE.search(body)
        house[cid] = m.group(1).decode() if m else None
        c = CHILD.search(body)
        for kid in (c.group(1).split() if c else []):
            parents.setdefault(kid.decode(), []).append(cid)
    dyn = {}
    for e in gs.iter_entries(g, *gs.locate(g, "dynasties/dynasty_house").body):
        m = re.search(rb"\n\t+dynasty=(\d+)", g[e.start:e.end])
        if m and e.key:
            dyn[e.key.decode()] = m.group(1).decode()
    the_dyn = dyn.get(house.get(player) or "")

    def origin(cid):
        r, w = ours[cid], wit.get(cid)
        in967 = bool(w and w["dna"] and w["name"] == r["name"] and w["birth"] == r["birth"])
        if r["dna"]:
            return "original face (967)" if in967 else "2023-only face"
        return "no face, though 967 has one" if in967 else "no face in any save (game generates one)"

    restored = {cid for cid in ours if origin(cid) == "original face (967)"}
    for label, pop in (("the player's dynasty", [c for c in ours if the_dyn and dyn.get(house[c] or "") == the_dyn]),
                       ("everyone", list(ours))):
        t = Counter((ours[c]["sec"].split("/")[-1], origin(c)) for c in pop)
        print(f"== {label}: {len(pop)} characters (dynasty {the_dyn})")
        for sec in ("living", "dead_unprunable", "dead_prunable"):
            row = {k[1]: v for k, v in t.items() if k[0] == sec}
            if row:
                print(f"  {sec:16} " + "; ".join(f"{k} {v}" for k, v in sorted(row.items())))
        kids = [c for c in pop if origin(c) == "2023-only face" and any(p in restored for p in parents.get(c, []))]
        living_kids = [c for c in kids if ours[c]["sec"] == "living"]
        print(f"  2023-only faces with a parent whose face was restored from 967: {len(kids)} "
              f"(living {len(living_kids)})")
        if label == "the player's dynasty":
            none_living = [c for c in pop if ours[c]["sec"] == "living" and not ours[c]["dna"]]
            print(f"  living family with no face: {len(none_living)}: " +
                  ", ".join(f"{c} {(ours[c]['name'] or b'?').decode('utf-8', 'replace')} b.{(ours[c]['birth'] or b'?').decode()}"
                            for c in none_living[:25]))
            for c in living_kids[:15]:
                ps = ", ".join(f"{p} {(ours[p]['name'] or b'?').decode('utf-8', 'replace')}" for p in parents.get(c, []))
                print(f"    child {c} {(ours[c]['name'] or b'?').decode('utf-8', 'replace')} "
                      f"b.{(ours[c]['birth'] or b'?').decode()}; parents {ps}")


if __name__ == "__main__":
    main()
