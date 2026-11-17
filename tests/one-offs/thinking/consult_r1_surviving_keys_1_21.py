"""Consultation round 1 (patch day 1.21), question 1: is "same key in 1.21" a safe carry?

For every building type v17 holds (by old holding type): where the same key (R1) or family (R2) is defined in 1.21
(file under common/buildings), which 1.21 districts list it (district.buildings lists first levels; primary_building
is the district's own), which slot type those districts are, and whether the old holding type's 1.21 holding lists
such a district. Also: per-holding counts of carried buildings against the re-save's regular_district_slot_limit.
Read-only. Run: python -I -X utf8 tests/one-offs/thinking/consult_r1_surviving_keys_1_21.py <v17> <resave>
"""
import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

NEW = pathlib.Path("E:/SteamLibrary/steamapps/common/Crusader Kings III/game/common")
TOP = re.compile(r"(?m)^([a-z][a-z0-9_]*)\s*=\s*\{")
fam = lambda k: re.sub(r"_\d+$", "", k)  # noqa: E731


def strip(text):
    return re.sub(r"#[^\n]*", "", text)


def blocks(text):
    """top-level key -> body (brace matched) of a script file."""
    out = {}
    for m in TOP.finditer(text):
        i, depth = m.end(), 1
        while depth and i < len(text):
            depth += (text[i] == "{") - (text[i] == "}")
            i += 1
        out[m.group(1)] = text[m.end():i - 1]
    return out


def inner(body, key):
    m = re.search(r"(?<![a-z_])" + key + r"\s*=\s*\{([^{}]*)\}", body)
    return m.group(1).split() if m else []


def main(v17, resave):
    bdef = {}  # building key -> file
    for f in (NEW / "buildings").rglob("*.txt"):
        for k in blocks(strip(f.read_text("utf-8-sig", "replace"))):
            bdef[k] = f.relative_to(NEW / "buildings").as_posix()
    dist = {}  # district -> (slot type, primary, [first-level buildings], file)
    for f in (NEW / "districts").glob("*.txt"):
        for k, body in blocks(strip(f.read_text("utf-8-sig", "replace"))).items():
            t = re.search(r"(?m)^\s*type\s*=\s*(\w+)", body)
            p = re.search(r"primary_building\s*=\s*(\w+)", body)
            dist[k] = (t.group(1) if t else "regular", p.group(1) if p else None, inner(body, "buildings"), f.name)
    hold = {}
    for k, body in blocks(strip((NEW / "holdings" / "00_holdings.txt").read_text("utf-8-sig", "replace"))).items():
        p = re.search(r"primary_district\s*=\s*(\w+)", body)
        hold[k] = {p.group(1) if p else None} | set(inner(body, "districts"))
    print(f"1.21: {len(bdef)} building keys, {len(dist)} districts, holdings {sorted(hold)}")
    print("district slot types:", collections.Counter(v[0] for v in dist.values()))
    by_family = collections.defaultdict(set)  # building family -> districts that list it
    for d, (_, prim, bl, _) in dist.items():
        for b in bl + ([prim] if prim else []):
            by_family[fam(b)].add(d)
    newfams = collections.defaultdict(list)
    for k in bdef:
        newfams[fam(k)].append(k)

    # v17: (holding type, building type) counts, and per-province lists
    g = read_save(v17).gamestate
    counts, per_prov = collections.Counter(), {}
    for e in gs.iter_entries(g, *gs.locate(g, "provinces").body):
        body = g[e.open:e.close]
        h = re.search(rb"\n\t\tholding=\{", body)
        if not h:
            continue
        ht = re.search(rb"\n\t\t\ttype=\"?(\w+)", body[h.end():])
        m = re.search(rb"\n\t\t\tbuildings=\{(.*?)\n\t\t\t\}", body[h.end():], re.S) or \
            re.search(rb"\n\t\t\tbuildings=\{(.*?) \}\n", body[h.end():], re.S)
        if not m:
            continue
        ts = [t.decode() for t in re.findall(rb'type="?(\w+)', m.group(1))]
        per_prov[e.key.decode()] = (ht.group(1).decode() if ht else "?", ts)
        for t in ts:
            counts[(ht.group(1).decode() if ht else "?", t)] += 1

    cls = collections.Counter()
    rows = collections.defaultdict(lambda: [0, set(), set(), set()])
    for (ht, t), n in counts.items():
        rule = "R1" if t in bdef else "R2" if fam(t) in newfams else "none"
        ds = by_family.get(fam(t), set()) if rule != "none" else set()
        hosted = bool(ds & hold.get(ht, set()))
        slot = {dist[d][0] for d in ds}
        primary = any(dist[d][1] and fam(dist[d][1]) == fam(t) for d in ds)
        if rule == "none":
            c = "unmapped"
        elif not ds:
            c = f"{rule}: key defined, in NO district ({bdef.get(t) or bdef[newfams[fam(t)][0]]})"
        elif hosted:
            c = f"{rule}: in a district the old holding type lists ({'/'.join(sorted(slot))}{', PRIMARY' if primary else ''})"
        else:
            c = f"{rule}: district exists but NOT in the old holding type's list ({'/'.join(sorted(slot))})"
        cls[c] += n
        r = rows[(c, fam(t))]
        r[0] += n
        r[1].add(ht)
        r[2] |= ds
        r[3].add(t)
    print("\n== v17 buildings by class (instances)")
    for c, n in cls.most_common():
        print(f"{n:7}  {c}")
    print("\n== families per class (instances, old holding types, 1.21 districts, old levels seen, 1.21 levels)")
    for (c, f), (n, hts, ds, ts) in sorted(rows.items(), key=lambda kv: (kv[0][0], -kv[1][0])):
        if c == "unmapped":
            continue
        lv_old = sorted(int(re.search(r"_(\d+)$", t).group(1)) for t in ts if re.search(r"_\d+$", t))
        lv_new = sorted(int(re.search(r"_(\d+)$", k).group(1)) for k in newfams.get(f, []) if re.search(r"_\d+$", k))
        print(f"{n:6} {f:34} {c[:60]:60} hold={sorted(hts)} districts={sorted(ds)[:4]} old={lv_old} new={lv_new}")

    # overflow: non-holding old buildings per holding against the re-save's slot limit
    gr = read_save(resave).gamestate
    limit = {}
    for e in gs.iter_entries(gr, *gs.locate(gr, "provinces").body):
        m = re.search(rb"regular_district_slot_limit=(\d+)", gr[e.open:e.close])
        if m:
            limit[e.key.decode()] = int(m.group(1))
    main_fams = {"castle", "city", "temple", "tribe", "nomad", "herder", "temple_citadel"}
    over = collections.Counter()
    need_d = collections.Counter()
    for pid, (ht, ts) in per_prov.items():
        extra = [t for t in ts if fam(t) not in main_fams]
        # distinct regular districts the R1/R2-mapped extras would need (a district holds several buildings)
        ds = set()
        for t in extra:
            cand = {d for d in by_family.get(fam(t), set()) if dist[d][0] == "regular"}
            if cand:
                ds.add(min(cand))
        lim = limit.get(pid)
        over[(len(extra) > (lim or 0))] += 1
        need_d[(len(ds) > (lim or 0))] += 1
    print("\nholdings whose old non-main buildings outnumber regular_district_slot_limit (naive 1 building = 1 slot):",
          dict(over))
    print("holdings whose R1/R2-mapped buildings need more DISTINCT regular districts than the limit:", dict(need_d))
    print("re-save slot limit distribution:", sorted(collections.Counter(limit.values()).items()))


if __name__ == "__main__":
    main(*sys.argv[1:3])
