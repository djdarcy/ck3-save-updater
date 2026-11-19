"""S2 of the built-state carry goal: the Rome proof of concept, one county, one game load.

Takes the v18 golden (a 1.21 save whose regular districts the game's conversion emptied), reads Rome's (province 2575)
1.20 regular buildings from the witness (v17), maps each through the S1 successor table (settled rows only; an open
row is skipped and named), checks each with host_rules BEFORE writing, and writes Rome's two regular districts the way
a fresh 1.21 game shapes them: a district row {buildings={ <pb_X_01> <successor>... } type=X_district owner=2575}, one
building row {type=...} per building, and the holding's districts={ a b }. Tier: the old level, capped at the
successor chain's top (S0 (2): 1.21's chains are no shorter).

PREDICTION (written 13:4x, before anything ran):
  P1  the game's re-save of the written save keeps both districts and all five buildings written (two pb lines,
      meadowlands_pastures_2, farming_fields_3, burgage_plots_3); 0 dropped;
  P2  Rome's holding income rises from v18's 0.00865 to above 1 (toward v17's 9.18; the curtain walls and the wonder's
      own income are outside this test, so 9.18 is not expected);
  P3  curtain_walls_02 is skipped and named (an open row of djdarcy's), never guessed.
CONTROL (pass/fail): pastures_1 into villages_district is refused by host_rules before the write, and is not written.
Observation only (no pass/fail): nothing else in the save changes (diff confined to Rome and the two databases).

Run: python -I -X utf8 tests/one-offs/thinking/s2_rome_poc.py <v18> <v17> <game dir> <s1 table.json> <out.ck3>
Writes only <out.ck3>, and refuses to overwrite it.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import host_rules  # noqa: E402
from ck3_save_migrator.carry_1_21 import _append, _next_index  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

ROME = "2575"
EMPTY = "4294967295"


def fam(k):
    return re.sub(r"_\d+$", "", k)


def lvl(k):
    t = k.rsplit("_", 1)[-1]
    return int(t) if t.isdigit() else 1


def province(g, pid):
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        if e.key == pid.encode():
            return e
    raise KeyError(pid)


def main(v18, v17, game, table, out):
    out = pathlib.Path(out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    rules = host_rules.load(game)
    rows = {(r["family"], r["holding"]): r for r in json.loads(pathlib.Path(table).read_text(encoding="utf-8"))}

    w = read_save(v17).gamestate
    wb = w[province(w, ROME).open:province(w, ROME).close]
    hb = wb[wb.find(b"holding={"):]
    holding = re.search(rb'type="?(\w+)', hb).group(1).decode()
    bl = re.search(rb"buildings=\{(.*?)\n\t\t\t\}", hb, re.S)
    old = [k.decode() for k in re.findall(rb'type="?([\w\-\']+)', bl.group(1))] if bl else []
    print(f"Rome in the witness: {holding}, buildings {old}")

    plan, skipped = {}, []                       # district -> [buildings]
    for k in old:
        r = rows.get((fam(k), holding))
        if r is None or r["kind"] in ("holding line", "wonder"):
            continue
        if r["kind"] != "settled":
            skipped.append((k, "open row for djdarcy (S1, HOLD 13:2x)"))
            continue
        sfam = fam(r["successor"])
        chain = sorted((b for b in rules.buildings if re.fullmatch(re.escape(sfam) + r"_\d+", b)), key=lvl)
        key = next((b for b in chain if lvl(b) == min(lvl(k), lvl(chain[-1]))), chain[0])
        v = rules.building_in(key, r["district"])
        if not v.ok:
            skipped.append((k, f"host_rules: {v.why}"))
            continue
        plan.setdefault(r["district"], []).append(key)

    # the control arm: a key no district of this holding lists must be refused before any write
    ctl = rules.building_in("pastures_1", "villages_district")
    control_pass = ctl.ok is False
    print(f"CONTROL pastures_1 -> villages_district: {ctl.ok} ({ctl.why}) -> {'PASS' if control_pass else 'FAIL'}")
    if not control_pass:
        sys.exit("control failed: host_rules would let an unhostable building through")

    if len(plan) > 2:
        sys.exit(f"more district types than slots: {sorted(plan)} (the overflow rule is S3's)")
    sv = read_save(v18)
    g = sv.gamestate
    e = province(g, ROME)
    body = g[e.open:e.close]
    m = re.search(rb"districts=\{ " + EMPTY.encode() + rb" " + EMPTY.encode() + rb" \}", body)
    if not m:
        sys.exit("Rome's regular slots are not both empty in this save")
    nb, nd = _next_index(g, "buildings/database") - 1, _next_index(g, "districts/database") - 1
    btext, dtext, ids = [], [], []
    for district, keys in sorted(plan.items()):
        pb = f"pb_{district.removesuffix('_district')}_01"
        assert rules.building_in(pb, district).ok, pb
        bids = []
        for k in [pb] + keys:
            nb += 1
            bids.append(str(nb))
            btext.append(f"\t\t{nb}={{\n\t\t\ttype={k}\n\t\t}}\n")
        nd += 1
        ids.append(str(nd))
        dtext.append(f"\t\t{nd}={{\n\t\t\tbuildings={{ {' '.join(bids)} }}\n\t\t\ttype={district}\n\t\t\towner={ROME}\n\t\t}}\n")
        print(f"write {district} ({nd}): {[pb] + keys}")
    ids += [EMPTY] * (2 - len(ids))
    at = e.open + m.start()
    g = g[:at] + f"districts={{ {' '.join(ids)} }}".encode() + g[at + len(m.group(0)):]
    g = _append(g, "buildings/database", "buildings", "".join(btext))
    g = _append(g, "districts/database", "districts", "".join(dtext))
    sv.set_gamestate(g)
    out.write_bytes(sv.to_bytes())
    print(f"skipped and named: {skipped}")
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main(*sys.argv[1:6])
