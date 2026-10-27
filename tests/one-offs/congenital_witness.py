"""congenital_witness: did the campaign's earlier migrations change inborn traits, the way they rerolled faces?
(djdarcy, 2026-10-26: "some things may have been broken and those broken elements may have been passed on as
defective genes/traits? Note often I hand modified character traits so that could be it too").

Inborn traits are fixed at birth in play (beauty, intellect and physique tiers, the genetic conditions), so for a
person in both the early save and the late save (same full id, same first name, same birth date), a difference in
them is either a version step's conversion, a mod change, or a hand edit. Traits are compared by NAME through each
save's own traits_lookup. Reports, for the player's dynasty and for everyone: people compared, people whose inborn
traits differ, the trait names gained and lost, and examples.

Usage: python -I tests/one-offs/congenital_witness.py <early.ck3> <late.ck3> [player id]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

SECTIONS = ("living", "dead_unprunable", "characters/dead_prunable")
INBORN = re.compile(r"^(beauty|intellect|physique)_(good|bad)(_\d)?$|^(albino|dwarf|giant|spindly|scaly|clubfooted|"
                    r"hunchbacked|lisping|stuttering|inbred|pure_blooded|fecund|wheezing|bleeder|lunatic_genetic|"
                    r"possessed_genetic|depressed_genetic|infertile|sickly|feeble|strong|shrewd|dull|comely|homely|"
                    r"giant|blind|lunatic_1|possessed_1|depressed_1|melancholic|imbecile|genius|quick|slow|"
                    r"herculean|hale|robust|amazonian|beautiful|handsome|ugly|hideous|"
                    r"physique_good_\d|intellect_good_\d|beauty_good_\d)$")


def read(path: str) -> dict:
    g = sf.read_save(path).gamestate
    tl = gs.find_section(g, "traits_lookup")
    names = [t.decode() for t in re.findall(rb'"?([A-Za-z0-9_]+)"?', g[tl.open + 1:tl.close])]
    out, house = {}, {}
    for e in gs.iter_entries(g, *gs.locate(g, "dynasties/dynasty_house").body):
        d = re.search(rb"\n\t+dynasty=(\d+)", g[e.start:e.end])
        if d and e.key:
            house[e.key.decode()] = d.group(1).decode()
    for sec in SECTIONS:
        try:
            b = gs.locate(g, sec)
        except gs.GamestateError:
            continue
        for e in gs.iter_entries(g, *b.body):
            if not (e.key and e.key.isdigit()):
                continue
            body = g[e.start:e.end]
            ind = re.match(rb"[^\n]*\n(\t*)", body).group(1)
            f = lambda k: re.search(rb"\n" + ind + k + rb'="?([^"\n]*?)"?\s*\n', body)        # noqa: E731
            tr = re.search(rb"\n" + ind + rb"traits=\{([^}]*)\}", body)
            tn = {names[int(i)] for i in re.findall(rb"\d+", tr.group(1))} if tr else set()
            nm, bi, hs = f(b"first_name"), f(b"birth"), f(b"dynasty_house")
            out[e.key.decode()] = {"name": nm.group(1) if nm else None, "birth": bi.group(1) if bi else None,
                                   "dyn": house.get(hs.group(1).decode()) if hs else None,
                                   "inborn": {t for t in tn if INBORN.match(t)}}
    return out


def main():
    early, late = read(sys.argv[1]), read(sys.argv[2])
    player = sys.argv[3] if len(sys.argv) > 3 else "50822"
    dyn = late[player]["dyn"]
    both = [c for c in early if c in late and early[c]["name"] == late[c]["name"]
            and early[c]["birth"] == late[c]["birth"]]
    for label, pop in (("the player's dynasty", [c for c in both if late[c]["dyn"] == dyn]), ("everyone", both)):
        changed = [c for c in pop if early[c]["inborn"] != late[c]["inborn"]]
        lost, gained = Counter(), Counter()
        for c in changed:
            lost.update(early[c]["inborn"] - late[c]["inborn"])
            gained.update(late[c]["inborn"] - early[c]["inborn"])
        print(f"== {label}: {len(pop)} people in both saves; inborn traits differ for {len(changed)}")
        print("  lost:   " + ", ".join(f"{k} {v}" for k, v in lost.most_common(20)))
        print("  gained: " + ", ".join(f"{k} {v}" for k, v in gained.most_common(20)))
        for c in changed[:12]:
            e, l = early[c]["inborn"], late[c]["inborn"]
            print(f"    {c} {(late[c]['name'] or b'?').decode('utf-8', 'replace')} b.{(late[c]['birth'] or b'?').decode()}:"
                  f" {sorted(e - l)} -> {sorted(l - e)}")


if __name__ == "__main__":
    main()
