"""P2 step 1 of the own-plot-converter design (2026-11-05__09-48-21): how does native 1.20 write an unfrozen plot?
Splits a game-written save's plots into carried (key present in the old build) and native (started in play), and
reports for each: freeze_data forms, where agent_slots sits in the field order, and the field-order shapes.
Usage: python -I scheme_native_form.py <old build.ck3> <game-written save.ck3>"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import savefile as sf, gamestate as gs  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    try:
        return sf.read_save(p).gamestate
    except sf.UnsupportedKindError:
        raw = open(p, "rb").read()
        return raw[raw.index(b"\n") + 1:]


def entries(d):
    b = gs.locate(d, "schemes/active")
    return {e.key: d[e.open:e.close + 1] for e in gs.iter_entries(d, *b.body) if e.key}


def shape(body):
    out = []
    for k in re.findall(rb"(?m)^\t\t\t(\w+)=", body):
        k = k.decode()
        if not out or out[-1] != k:          # collapse repeats (agent_slots x3, timed_modifier x2)
            out.append(k)
    return tuple(out)


old = entries(load(sys.argv[1]))
new = entries(load(sys.argv[2]))
groups = {"carried": [k for k in new if k in old], "native": [k for k in new if k not in old]}
for g, keys in groups.items():
    print(f"== {g}: {len(keys)}")
    fz = Counter((re.search(rb"freeze_data=\{[^}]*\}", new[k]).group(0) if b"freeze_data" in new[k] else b"(none)")
                 for k in keys)
    print("freeze_data:", fz.most_common(5))
    print("shapes:", Counter(shape(new[k]) for k in keys).most_common(3))
    print("next_id vs slot count:", Counter((re.search(rb"next_id=(\d+)", new[k]).group(1) if b"next_id" in new[k]
                                             else b"-", new[k].count(b"agent_slots=")) for k in keys).most_common(6))
