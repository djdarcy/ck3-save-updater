"""Test a rule for when the game leaves `culture=` out: does it omit the culture exactly when it equals the culture
of the character's house head? For every character in our save with a culture and a house, cross whether the game's
re-save kept the line with whether it equals the head's culture (from our save), and also with the father's.
Usage: culture_omit_rule.py <our save> <the game's re-save>"""
import re
import sys
from collections import Counter

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402


def load(path):
    try:
        return sf.read_save(path).gamestate
    except sf.UnsupportedKindError:
        raw = open(path, "rb").read()
        return raw[raw.index(b"\n") + 1:]


ENTRY = re.compile(rb"(?m)^(\d+)=\{\n")


def characters(d):
    out = {}
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        for m in ENTRY.finditer(d, b.start, b.end):
            out[m.group(1).decode()] = (sec, d[m.end():d.find(b"\n}", m.end())])
    return out


def field(body, name):
    m = re.search(rb"(?m)^\t" + name + rb"=(\S+)", body)
    return m.group(1).decode() if m else None


ours_d = load(sys.argv[1])
ours, theirs = characters(ours_d), characters(load(sys.argv[2]))
houses = gs.locate(ours_d, "dynasties/dynasty_house")
head = {}
for e in gs.iter_entries(ours_d, *houses.body):
    m = re.search(rb"head_of_house=(\d+)", ours_d[e.body[0]:e.body[1]])
    if m:
        head[e.key.decode()] = m.group(1).decode()
fathers = {}                      # 1.20 writes children under the parent: child -> a parent with a culture
for cid, (_, b) in ours.items():
    for kid in re.findall(rb"child=\{([^}]*)\}", b):
        for k in kid.split():
            fathers.setdefault(k.decode(), cid)

n = Counter()
for cid, (sec, b) in ours.items():
    c, h = field(b, b"culture"), field(b, b"dynasty_house")
    if c is None or h is None or cid not in theirs:
        continue
    hc = field(ours.get(head.get(h, ""), ("", b""))[1], b"culture")
    emp = field(b, b"employer") or field(b, b"host")
    ec = field(ours.get(emp or "", ("", b""))[1], b"culture")
    kept = field(theirs[cid][1], b"culture") is not None
    court = "court" if emp else "no court"
    n[(sec, court, "equals head" if c == hc else ("no head culture" if hc is None else "differs from head"),
       "kept" if kept else "OMITTED")] += 1
    if emp:
        n[(sec, court, "employer: " + ("equals" if c == ec else ("none" if ec is None else "differs")),
           "kept" if kept else "OMITTED")] += 1
for k, v in sorted(n.items()):
    print(f"{v:8,}  {' / '.join(k)}")
