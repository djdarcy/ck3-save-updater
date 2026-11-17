"""S2 (patch-day goal): the in-game test saves -- what does 1.21 keep of districts written by hand?

Two bases (the goal's addendum 16:12 on why not "v17 restamped"):
  A: djdarcy's 1.21 re-save of v17 (a valid 1.21 save), stamp 1.21.0 kept;
  B: v17 itself (1.20.1.2), stamp kept, the districts/buildings databases created -- the game converts it on load.
The same ten cases go into each base, one per province (castle holdings, province id >= 200, so not the player's
Irish home), each recorded in cases.json with its province id, the rows written and what to look at:
  0 control  : the reference's province 458 shape -- villages (pb_villages_01) + manor_houses (pb_manor_houses_01)
  1 i        : villages with its primary plus farming_fields_1
  2 ii       : three regular districts against a limit of 2
  3 iii      : guild_district without its unlocked_by (urban_housing_district)
  4 iv       : walls with ramparts_2 (needs district level 2) on a level-1 primary
  5 v        : a special district (alhambra_01_district with alhambra_01)
  6 vi-a     : the resource district replaced by one of another good (grain_district, grain_resource_building_1)
  7 vi-b     : the resource district's primary lifted to tier 3 of its own good
  8 vii      : villages with more buildings than its slot array (4 against 3)
  9 viii     : villages whose primary has no fulfilled_trade_good_needs
Building rows copy the reference's body for the same type when it has one (fulfilled_trade_good_needs as the game
writes it); case 9's primary is written bare on purpose.
Run: python -I -X utf8 tests/one-offs/thinking/s2_test_save/build.py <resave.ck3> <v17.ck3> <ref.ck3> <out dir>
Writes <out>/MIGRATE_TEST__1.21-stamp121.ck3 and <out>/MIGRATE_TEST__1.21-stamp120.ck3, and cases.json.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save, write_save  # noqa: E402

NONE = "4294967295"


def ref_bodies(ref):
    """building type -> the reference's building body for it (the first of each type)."""
    b = gs.locate(ref, "buildings/database")
    out = {}
    for e in gs.iter_entries(ref, *b.body):
        m = re.search(rb"type=(\w+)", ref[e.open:e.open + 120])
        if m and m.group(1).decode() not in out:
            out[m.group(1).decode()] = ref[e.open:e.close + 1].decode()
    return out


def max_id(g, path):
    try:
        b = gs.locate(g, path)
    except gs.GamestateError:
        return 0
    return max((int(e.key) for e in gs.iter_entries(g, *b.body) if e.key and e.key.isdigit()), default=0)


class Rows:
    """New building and district rows, numbered past each database's maximum."""

    def __init__(self, g, bodies):
        self.b, self.d, self.bodies = max_id(g, "buildings/database"), max_id(g, "districts/database"), bodies
        self.btext, self.dtext = [], []

    def building(self, typ, bare=False):
        self.b += 1
        body = "{\n\t\t\ttype=%s\n\t\t}" % typ if bare or typ not in self.bodies else self.bodies[typ]
        self.btext.append(f"\t\t{self.b}={body}\n")
        return str(self.b)

    def district(self, typ, owner, buildings, slots):
        self.d += 1
        arr = " ".join(buildings + [NONE] * max(0, slots - len(buildings)))
        self.dtext.append(f"\t\t{self.d}={{\n\t\t\tbuildings={{ {arr} }}\n\t\t\ttype={typ}\n\t\t\towner={owner}\n\t\t}}\n")
        return str(self.d)


def castle_provinces(g, need, base):
    pv = gs.locate(g, "provinces")
    out = []
    for e in gs.iter_entries(g, *pv.body):
        if not (e.key and e.key.isdigit()) or int(e.key) < 200:
            continue
        body = g[e.open:e.close]
        ok = b"type=castle_holding" in body or b'type="castle_holding"' in body
        if ok and (base == "B" or re.search(rb"districts=\{ 4294967295 4294967295 \}", body)):
            out.append(e)
        if len(out) == need:
            break
    return out


def build(g, bodies, base, provinces=None):
    rows, p, cases = Rows(g, bodies), gs.EditPass(), []
    provs = provinces or castle_provinces(g, 10, base)
    for i, e in enumerate(provs):
        pid, body = e.key.decode(), g[e.open:e.close]
        res_m = re.search(rb"resource_district=(\d+)", body)
        regular, extra, note = None, "", ""
        if i == 0:
            regular = [rows.district("villages_district", pid, [rows.building("pb_villages_01")], 3),
                       rows.district("manor_houses_district", pid, [rows.building("pb_manor_houses_01")], 2)]
            note = "control: the reference's shape"
        elif i == 1:
            regular = [rows.district("villages_district", pid,
                                     [rows.building("pb_villages_01"), rows.building("farming_fields_1")], 3)]
            note = "primary plus farming_fields_1"
        elif i == 2:
            regular = [rows.district(t, pid, [rows.building(pb)], 2) for t, pb in
                       (("villages_district", "pb_villages_01"), ("manor_houses_district", "pb_manor_houses_01"),
                        ("walls_district", "pb_walls_01"))]
            note = "three districts, limit 2"
        elif i == 3:
            regular = [rows.district("guild_district", pid, [rows.building("pb_guild_01")], 2)]
            note = "guild without urban_housing"
        elif i == 4:
            regular = [rows.district("walls_district", pid,
                                     [rows.building("pb_walls_01"), rows.building("ramparts_2")], 2)]
            note = "ramparts_2 on a level-1 walls district"
        elif i == 5:
            sd = rows.district("alhambra_01_district", pid, [rows.building("alhambra_01")], 1)
            extra = f"\n\t\t\tspecial_district={sd}\n\t\t\tspecial_district_type=alhambra_01_district"
            note = "special district (alhambra)"
        elif i == 6:
            rd = rows.district("grain_district", pid, [rows.building("grain_resource_building_1")], 2)
            note = f"resource district replaced by grain ({rd})"
            if res_m:
                p.add(gs.Edit(e.open + res_m.start(1), e.open + res_m.end(1), rd.encode(), "S2", note))
            else:
                extra = f"\n\t\t\tresource_district={rd}"
        elif i == 7:
            rd = rows.district("forestry_district", pid, [rows.building("forestry_resource_building_3")], 2)
            note = f"resource district at tier 3 ({rd})"
            if res_m:
                p.add(gs.Edit(e.open + res_m.start(1), e.open + res_m.end(1), rd.encode(), "S2", note))
            else:
                extra = f"\n\t\t\tresource_district={rd}"
        elif i == 8:
            regular = [rows.district("villages_district", pid,
                                     [rows.building("pb_villages_01")] + [rows.building("farming_fields_1")
                                                                          for _ in range(3)], 3)]
            note = "4 buildings in a 3-slot array"
        elif i == 9:
            regular = [rows.district("villages_district", pid, [rows.building("pb_villages_01", bare=True)], 3)]
            note = "primary without fulfilled_trade_good_needs"
        dl = re.search(rb"districts=\{[^}]*\}", body)
        if regular is not None:
            text = ("districts={ " + " ".join(regular + [NONE] * max(0, 2 - len(regular))) + " }").encode()
            if dl:
                p.add(gs.Edit(e.open + dl.start(), e.open + dl.end(), text, "S2", note))
            else:
                extra = "\n\t\t\t" + text.decode() + extra
        if extra:
            h = re.search(rb"\n\t\t\ttype=\"?castle_holding\"?", body)
            p.add(gs.Edit(e.open + h.end(), e.open + h.end(), extra.encode(), "S2", note))
        cases.append({"case": i, "province": pid, "what": note, "districts": regular})
    return rows, p, cases


def apply(save, rows, p, base):
    g = save.gamestate
    if base == "A":
        bb, db = gs.locate(g, "buildings/database"), gs.locate(g, "districts/database")
        p.insert(bb, "end", "".join(rows.btext).encode(), "S2", "buildings")
        p.insert(db, "end", "".join(rows.dtext).encode(), "S2", "districts")
        p.apply_to(save)
    else:
        p.apply_to(save)
        save.set_gamestate(save.gamestate + (
            "districts={\n\tdatabase={\n" + "".join(rows.dtext) + "\t}\n}\n"
            "buildings={\n\tdatabase={\n" + "".join(rows.btext) + "\t}\n}\n").encode())


def main(resave, v17, ref, out):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    bodies = ref_bodies(read_save(ref).gamestate)
    report = {}
    for base, src, name in (("A", resave, "MIGRATE_TEST__1.21-stamp121.ck3"),
                            ("B", v17, "MIGRATE_TEST__1.21-stamp120.ck3")):
        save = read_save(src)
        rows, p, cases = build(save.gamestate, bodies, base)
        apply(save, rows, p, base)
        write_save(save, out / name)
        report[name] = {"base": src, "cases": cases, "new_buildings": len(rows.btext), "new_districts": len(rows.dtext)}
        print(f"{name}: {len(cases)} cases, {len(rows.btext)} buildings, {len(rows.dtext)} districts")
    (out / "cases.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])
