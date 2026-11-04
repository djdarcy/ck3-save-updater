"""Which field marks the characters that lose `culture` on load? Finds them by comparing our save with the game's
re-save of it, then compares the fields they carry with those of characters that keep their culture and carry an
`ethnicity` line (the transplanted ones, written from the 1.20 reference). Prints every field whose share differs by
more than 30 points, and the values of a few fields among the lost.
Usage: culture_loss_marker.py <our save> <the game's re-save>"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:              # a plain-text save (kind 00): drop the header line
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


ENTRY = re.compile(rb"(?m)^(\d+)=\{\n")
FIELD = re.compile(rb"(?m)^\t([a-z_]+)=")


def characters(d):
    out = {}
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        for m in ENTRY.finditer(d, b.start, b.end):
            e = d.find(b"\n}", m.end())
            out[m.group(1).decode()] = d[m.end():e]
    return out


ours, theirs = characters(load(sys.argv[1])), characters(load(sys.argv[2]))
has_c = lambda body: re.search(rb"(?m)^\tculture=", body) is not None  # noqa: E731
lost = [c for c, b in ours.items() if has_c(b) and c in theirs and not has_c(theirs[c])]
kept = [c for c, b in ours.items() if has_c(b) and b"\tethnicity=" in b and c in theirs and has_c(theirs[c])]
print(f"lost {len(lost)}: {sorted(lost, key=int)}")
print(f"kept, with ethnicity: {len(kept)}")
share = {}
for name, ids in (("lost", lost), ("kept", kept)):
    n = Counter()
    for c in ids:
        n.update(set(f.decode() for f in FIELD.findall(ours[c])))
    share[name] = {k: v / len(ids) for k, v in n.items()}
for f in sorted(set(share["lost"]) | set(share["kept"])):
    a, b = share["lost"].get(f, 0), share["kept"].get(f, 0)
    if abs(a - b) > 0.3:
        print(f"  {f:28s} lost {a:5.0%}  kept {b:5.0%}")
for f in (b"culture", b"dynasty_house", b"employer", b"host", b"was_playable"):
    vals = Counter((re.search(rb"(?m)^\t" + f + rb"=(\S+)", ours[c]) or [None, b"-"])[1].decode() for c in lost)
    print(f"  lost {f.decode()}: {dict(vals.most_common(8))}")
