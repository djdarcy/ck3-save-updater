"""Goal 2026-11-19__22-43-27, S1 measure: the innovations new in 1.21 that the converted campaign never lists.

For three saves (the 1.20 witness, the converted campaign, a fresh 1.21 game at the same date), per culture: which of
1.21's innovations it lists, and which are discovered (`progress=100`) or in progress. The missing set is the fresh
game's innovations that the converted save lists for no culture. For each missing innovation: its era (common/culture/
innovations), and in the fresh game how many cultures have it discovered / in progress / listed only.

Evidence for a "discovered" state in the converted save, per (culture, missing innovation):
  ref   the fresh game's culture with the same culture_template has it discovered
  era   the campaign culture's current era (culture_era_data, progress=100) is at or past the innovation's era
Printed: how often each holds and how often both hold, so the rule's source is chosen from counts.

Prediction (written first): the missing set is the 18 counted on 2026-11-19; most are early-medieval civic
innovations; in the fresh game at 987 most cultures have them listed only (undiscovered), so "both" is small.

Run: python -I -X utf8 tests/one-offs/thinking/s1_innovations_measure.py <v17> <v19> <fresh 1.21 ref> <1.21 game dir>
Read-only.
"""
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import host_rules  # noqa: E402
from ck3_save_migrator.savefile import read_save  # noqa: E402

ERAS = ["culture_era_tribal", "culture_era_early_medieval", "culture_era_high_medieval", "culture_era_late_medieval"]


def cultures(path):
    """culture id -> {template, era (index of the latest era with progress=100), inn: {innovation: progress or None}}."""
    g = read_save(path).gamestate
    out = {}
    for e in gs.iter_entries(g, *gs.locate(g, "culture_manager/cultures").body):
        if not e.key:
            continue
        b = g[e.open:e.close]
        t = re.search(rb'culture_template="?([a-z_0-9]+)', b)
        era = -1
        ed = re.search(rb"culture_era_data=\{(.*?)\n\t\t\t\}", b, re.S)
        if ed:
            for m in re.finditer(rb"type=(culture_era_[a-z_]+)\s*(?:progress=([\d.]+))?", ed.group(1)):
                if m.group(2) and float(m.group(2)) >= 100 and m.group(1).decode() in ERAS:
                    era = max(era, ERAS.index(m.group(1).decode()))
        inn = {}
        ci = re.search(rb"culture_innovation=\{", b)
        if ci:
            body = b[ci.end():gs.match_brace(b, ci.end() - 1)]
            for m in re.finditer(rb"\{\s*type=(innovation_[a-z_0-9]+)\s*(?:progress=([\d.]+))?", body):
                inn[m.group(1).decode()] = float(m.group(2)) if m.group(2) else None
        out[e.key.decode()] = {"template": t.group(1).decode() if t else None, "era": era, "inn": inn}
    return out


def eras(game):
    out = {}
    for f in sorted((pathlib.Path(game) / "common" / "culture" / "innovations").glob("*.txt")):
        for k, body, _ in host_rules._blocks(f):
            m = re.search(r"culture_era\s*=\s*(culture_era_\w+)", body)
            if k.startswith("innovation_") and m:
                out[k] = m.group(1)
    return out


def main(v17, v19, ref, game):
    w, c, f = cultures(v17), cultures(v19), cultures(ref)
    era_of = eras(game)
    fresh_all = {i for x in f.values() for i in x["inn"]}
    conv_all = {i for x in c.values() for i in x["inn"]}
    wit_all = {i for x in w.values() for i in x["inn"]}
    missing = sorted(fresh_all - conv_all)
    print(f"cultures: v17 {len(w)}, v19 {len(c)}, fresh {len(f)}; innovations listed: v17 {len(wit_all)}, v19 {len(conv_all)}, "
          f"fresh {len(fresh_all)}; missing from v19: {len(missing)} (also absent from v17: {sum(i not in wit_all for i in missing)})")
    # what an entry for a missing innovation looks like in the fresh game
    states = collections.Counter()
    by_template = collections.defaultdict(list)
    for x in f.values():
        by_template[x["template"]].append(x)
    print("\ninnovation | era | fresh cultures: discovered / in progress / listed only")
    for i in missing:
        d = sum(1 for x in f.values() if (x["inn"].get(i) or 0) >= 100)
        p = sum(1 for x in f.values() if 0 < (x["inn"].get(i) or 0) < 100)
        lo = sum(1 for x in f.values() if i in x["inn"] and not x["inn"].get(i))
        print(f"{i} | {era_of.get(i, '?')} | {d} / {p} / {lo}")
        states["discovered"] += d
    # evidence per (v19 culture, missing innovation)
    ev = collections.Counter()
    matched = sum(1 for x in c.values() if x["template"] in by_template)
    for x in c.values():
        fx = by_template.get(x["template"])
        for i in missing:
            ref_d = bool(fx) and any((y["inn"].get(i) or 0) >= 100 for y in fx)
            ref_p = bool(fx) and any(0 < (y["inn"].get(i) or 0) < 100 for y in fx)
            era_ok = era_of.get(i) in ERAS and x["era"] >= ERAS.index(era_of[i])
            ev["pairs"] += 1
            ev["ref discovered"] += ref_d
            ev["ref in progress"] += ref_p
            ev["era reached"] += era_ok
            ev["both"] += ref_d and era_ok
            ev["ref discovered, era not reached"] += ref_d and not era_ok
    print(f"\nv19 cultures with a fresh culture of the same template: {matched} of {len(c)}")
    print("evidence over (v19 culture x missing innovation):", dict(ev))
    print("v19 cultures by era reached:", collections.Counter(ERAS[x['era']] if x['era'] >= 0 else 'none' for x in c.values()))
    print("fresh cultures by era reached:", collections.Counter(ERAS[x['era']] if x['era'] >= 0 else 'none' for x in f.values()))


if __name__ == "__main__":
    main(*sys.argv[1:])
