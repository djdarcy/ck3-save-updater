"""Duchy capitals across the 1.21 conversion: what 1.20 had, what the conversion kept, what a fresh 1.21 game has.

Rethink of "the six duchy-capital buildings have nowhere to land" (2026-11-19): 1.21 keeps 16 of 1.20's 17 duchy-capital
building families under the same key, now inside duchy-capital districts (common/districts/duchy_capital_districts.txt),
which a province gets when its county holder also holds the province's duchy (can_have_duchy_capital_building_trigger).

For each save, lists every province carrying a duchy-capital building (1.20: in the holding's buildings, or the
duchy_capital slot) or a duchy_capital_district= (1.21), with the district's type and buildings.

Prediction (written first): v17 holds 5-15 duchy-capital buildings; the conversion kept a duchy_capital_district only
where it built one from a 1.20 building (v19's 2); the fresh game's 11 sit in provinces where v17 had none.

Run: python -I -X utf8 tests/one-offs/thinking/duchy_capital_measure.py <v17> <v19> <fresh 1.21 reference>
Read-only.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

DUCHY_1_20 = {"archery_ranges", "blacksmiths", "burial_site", "charnel_grounds", "dragon_kiln", "examination_hall",
              "great_megalith", "jousting_lists", "leisure_palace", "march", "military_academy", "royal_armory",
              "royal_forest", "royal_garden", "siege_works", "tax_assessor", "tower_of_silence"}


def fam(k):
    return re.sub(r"_\d+$", "", k)


def provinces(g):
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if e.key and e.key.isdigit():
            yield e.key.decode(), g[e.open:e.close]


def db(g, path):
    try:
        return {e.key.decode(): g[e.open:e.close + 1] for e in gs.iter_entries(g, *gs.locate(g, path).body) if e.key}
    except Exception:
        return {}


def typ(b):
    m = re.search(rb'type="?([a-z_0-9]+)', b)
    return m.group(1).decode() if m else "?"


def old_duchy(g):
    out = {}
    for pid, body in provinces(g):
        ks = [k.decode() for k in re.findall(rb'type="?([a-z_0-9]+)', body)]
        hit = sorted({k for k in ks if fam(k) in DUCHY_1_20})
        if hit:
            out[pid] = hit
    return out


def new_duchy(g):
    D, B = db(g, "districts/database"), db(g, "buildings/database")
    out = {}
    for pid, body in provinces(g):
        m = re.search(rb"\n\t\t\tduchy_capital_district=(\d+)", body)
        if m:
            d = D.get(m.group(1).decode(), b"")
            bl = re.search(rb"buildings=\{([^}]*)\}", d)
            bs = [typ(B.get(i.decode(), b"")) for i in re.findall(rb"\d+", bl.group(1))] if bl else []
            out[pid] = (typ(d), bs)
    return out


def main(v17, v19, ref):
    w = read_save(v17).gamestate
    old = old_duchy(w)
    print(f"v17 (1.20): {len(old)} provinces with a duchy-capital building")
    for p, ks in sorted(old.items(), key=lambda x: int(x[0])):
        print(f"  {p}: {ks}")
    for label, path in (("v19 (your campaign, converted + carried)", v19), ("fresh 1.21 game", ref)):
        g = read_save(path).gamestate
        new = new_duchy(g)
        print(f"\n{label}: {len(new)} provinces with a duchy_capital_district")
        for p, (t, bs) in sorted(new.items(), key=lambda x: int(x[0])):
            print(f"  {p}: {t} {bs}  {'(v17 had ' + str(old[p]) + ')' if p in old else '(v17 had none here)'}")
        lost = sorted(set(old) - set(new), key=int)
        print(f"  v17 duchy-capital provinces with no duchy_capital_district here: {len(lost)} {lost[:20]}")


if __name__ == "__main__":
    main(*sys.argv[1:])
