"""Print dynasty houses (dynasties/dynasty_house/<id>) from a save, the culture of each house's head, and the culture
of every listed character. Usage: house_of.py <save> <house id,...> [character id,...]"""
import re
import sys

sys.path.insert(0, r"C:\code\ck3-save-migrator")
from ck3_save_migrator import gamestate as gs  # noqa: E402
from ck3_save_migrator import savefile as sf  # noqa: E402

try:
    d = sf.read_save(sys.argv[1]).gamestate
except sf.UnsupportedKindError:
    raw = open(sys.argv[1], "rb").read()
    d = raw[raw.index(b"\n") + 1:]
houses = gs.locate(d, "dynasties/dynasty_house")


def character(cid):
    for sec in ("living", "dead_unprunable"):
        b = gs.find_section(d, sec)
        m = re.compile(rb"\n" + cid.encode() + rb"=\{").search(d, b.start, b.end)
        if m:
            return sec, d[m.end():d.find(b"\n}", m.end())]
    return None, b""


def culture(body):
    m = re.search(rb"(?m)^\tculture=(\S+)", body)
    return m.group(1).decode() if m else "-"


by_id = {e.key.decode(): e for e in gs.iter_entries(d, *houses.body)}   # entries sit at column 0
for hid in sys.argv[2].split(","):
    e = by_id.get(hid)
    if e is None:
        print(f"house {hid}: not found")
        continue
    body = d[e.body[0]:e.body[1]]
    print(f"== house {hid}\n{body.decode('utf-8', 'replace')[:600]}")
    head = re.search(rb"head_of_house=(\d+)", body)
    if head:
        sec, hb = character(head.group(1).decode())
        print(f"   head {head.group(1).decode()} ({sec}): culture {culture(hb)}")
for cid in (sys.argv[3].split(",") if len(sys.argv) > 3 else []):
    sec, b = character(cid)
    print(f"character {cid} ({sec}): culture {culture(b)}, house "
          f"{(re.search(rb'dynasty_house=(\d+)', b) or [None, b'-'])[1].decode()}")
