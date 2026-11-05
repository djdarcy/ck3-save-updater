"""Print a carried plot raw from the build and from the game's day-one re-save, side by side (P1 of the
own-plot-converter goal). Also prints the key-order shapes over all paired plots, so the converter can match the
game's order, and one 'invalidated' plot.
Usage: python -I scheme_raw_pair.py <build.ck3> <re-save.ck3> [n_examples]"""
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
    return tuple(k.decode() for k in re.findall(rb"(?m)^\t\t\t(\w+)=", body))


old, new = entries(load(sys.argv[1])), entries(load(sys.argv[2]))
n = int(sys.argv[3]) if len(sys.argv) > 3 else 1
paired = [k for k in old if k in new]
print("old shapes:", Counter(shape(old[k]) for k in paired).most_common(4))
print("new shapes:", Counter(shape(new[k]) for k in paired).most_common(6))
shown = 0
for k in paired:
    if shown >= n:
        break
    print(f"--- {k.decode()} OLD\n{old[k].decode()}\n--- NEW\n{new[k].decode()}")
    shown += 1
inv = [k for k in paired if b"status=invalidated" in new[k]]
if inv:
    k = inv[0]
    print(f"--- invalidated {k.decode()} OLD\n{old[k].decode()}\n--- NEW\n{new[k].decode()}")
NONE = b"4294967295"


def facts(body):
    own = re.search(rb"(?m)^\t\t\towner=(\d+)", body)
    tgt = re.search(rb"(?m)^\t\t\ttarget=(\d+)", body)
    return (("owner" if own and own.group(1) != NONE else "no-owner"),
            ("target" if tgt and tgt.group(1) != NONE else "no-target"),
            ("type" if re.search(rb"(?m)^\t\t\ttype=", body) else "no-type"),
            ("ready" if b"ready=yes" in body else "-"))


st = Counter((re.search(rb"status=(\w+)", new[k]).group(1).decode(), facts(old[k])) for k in paired)
print("status by (owner, target, type, ready):", sorted(st.items()))
fz = Counter(re.search(rb"freeze_data=\{[^}]*\}", new[k]).group(0) for k in paired if b"freeze_data" in new[k])
print("freeze_data forms:", fz.most_common(4))
