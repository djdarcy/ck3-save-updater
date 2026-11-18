"""S2 of the patch-day goal: what the game kept of our hand-built 1.21 districts, under each version stamp.

For each case province (cases.json, written by build.py), the staged save's holding (slot -> district type ->
building types) against the game's own re-save of it, by type (the game may renumber ids). Verdict per case:
kept (same districts and buildings), changed (named), dropped (our districts gone).

Prediction (the final assessment, 2026-11-17__15-28-05, unconfirmed then): the 1.21.0 stamp keeps the control and
case 1 and rejects cases 3 and 8; the 1.20 stamp rebuilds districts and drops ours.
CONTROL: case 0 is the reference's own shape. If the 1.21.0-stamped re-save does not keep it, the reading (or the
builder) is wrong, and nothing else here counts.

Run: python -I -X utf8 tests/one-offs/thinking/s2_test_save/read_resaves.py <cases.json> <staged> <resave> [<staged> <resave>]
Reads only.
"""
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

EMPTY = "4294967295"


def holdings(g: bytes, pids: set) -> dict:
    """province id -> {"type", "fields": {slot field: district type}, "regular": [district types],
    "buildings": {district type: [building types]}, "size": level}"""
    try:
        bt = {e.key.decode(): (re.search(rb"type=(\S+)", g[e.open:e.open + 200]) or [None, b"?"])[1].decode()
              for e in gs.iter_entries(g, *gs.locate(g, "buildings/database").body)}
        dd = {}
        for e in gs.iter_entries(g, *gs.locate(g, "districts/database").body):
            body = g[e.open:e.close]
            m = re.search(rb"\bbuildings=\{([^{}]*)\}", body)
            dd[e.key.decode()] = (re.search(rb"type=(\S+)", body).group(1).decode(),
                                  [bt.get(x, "?" + x) for x in (m.group(1).decode().split() if m else []) if x != EMPTY])
    except gs.GamestateError:
        bt, dd = {}, {}
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        pid = e.key.decode()
        if pid not in pids:
            continue
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{(.*?)\n\t\t\}", body, re.S)
        hb = h.group(1) if h else b""
        t = re.search(rb'\n\t\t\ttype="?(\w+)', hb)
        fields = {m.group(1).decode(): dd.get(m.group(2).decode(), ("?" + m.group(2).decode(), []))[0]
                  for m in re.finditer(rb"\b(\w*district)=(\d+)", hb)}
        m = re.search(rb"\bdistricts=\{([^{}]*)\}", hb)
        reg = [dd.get(x, ("?" + x, []))[0] for x in (m.group(1).decode().split() if m else []) if x != EMPTY]
        blds = {}
        for d in list(re.findall(rb"\b\w*district=(\d+)", hb)) + [x.encode() for x in (m.group(1).decode().split() if m else [])]:
            d = d.decode()
            if d in dd:
                blds.setdefault(dd[d][0], []).extend(dd[d][1])
        old = re.search(rb"\n\t\t\tbuildings=\{(.*?)\n\t\t\t\}", hb, re.S)
        lv = re.search(rb"province_size_level=(\d+)", body)
        out[pid] = {"type": t.group(1).decode() if t else None, "fields": fields, "regular": reg,
                    "buildings": blds, "size": lv.group(1).decode() if lv else None,
                    "old_buildings": re.findall(rb'type="?(\w+)', old.group(1)).__len__() if old else 0}
    return out


def show(h: dict) -> str:
    if not h:
        return "(no holding)"
    parts = [f"{h['type']}", f"size {h['size']}"]
    parts += [f"{k}={v}" for k, v in sorted(h["fields"].items())]
    if h["regular"]:
        parts.append(f"districts={h['regular']}")
    parts.append("buildings=" + "; ".join(f"{d}:{b}" for d, b in sorted(h["buildings"].items())))
    if h["old_buildings"]:
        parts.append(f"(1.20 buildings= list: {h['old_buildings']})")
    return " | ".join(parts)


def main(cases_path, *pairs):
    cases = json.load(open(cases_path, encoding="utf-8"))
    for staged, resave in zip(pairs[::2], pairs[1::2]):
        name = pathlib.Path(staged).name
        cs = cases[name]["cases"]
        pids = {c["province"] for c in cs}
        gs_, gr = read_save(staged).gamestate, read_save(resave).gamestate
        a, b = holdings(gs_, pids), holdings(gr, pids)
        for g, label in ((gs_, "staged"), (gr, "re-save")):
            n_d = len(list(gs.iter_entries(g, *gs.locate(g, "districts/database").body))) if b"districts={" in g else 0
            n_b = len(list(gs.iter_entries(g, *gs.locate(g, "buildings/database").body))) if b"buildings={" in g else 0
            v = re.search(rb'\bversion="([^"]+)"', g[:4000])
            print(f"== {name} [{label}] version {v.group(1).decode() if v else '?'}: {n_d} districts, {n_b} buildings")
        for c in cs:
            pid = c["province"]
            same = a.get(pid, {}).get("buildings") == b.get(pid, {}).get("buildings") and \
                a.get(pid, {}).get("regular") == b.get(pid, {}).get("regular") and \
                a.get(pid, {}).get("fields") == b.get(pid, {}).get("fields")
            print(f"\ncase {c['case']} p{pid} {c['what']}: {'KEPT' if same else 'CHANGED'}")
            print(f"   staged : {show(a.get(pid))}")
            print(f"   re-save: {show(b.get(pid))}")


if __name__ == "__main__":
    main(*sys.argv[1:])
